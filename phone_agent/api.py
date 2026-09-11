"""ContentSwarm API layer for external orchestration.

Exposes phone management, device/app control, pipeline control, and analytics
as REST + WebSocket endpoints that an external agent harness (Orphus via the
`contentswarm` CLI) can invoke.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
import uuid
import json
from typing import Any, Dict, Optional

from flask import Blueprint, Response, jsonify, request, session, has_request_context


_PREPARED_TTL_SECONDS = 300


def create_api_blueprint(state: Dict[str, Any]) -> Blueprint:
    """
    Create the API Blueprint with access to shared application state.

    Args:
        state: Shared application state dict containing phone_manager,
               automation, etc.

    Returns:
        Flask Blueprint with all API routes.
    """
    api = Blueprint("contentswarm_api", __name__)

    # In-flight async tasks tracked by task_id
    _tasks: Dict[str, Dict[str, Any]] = {}
    _prepared_messages: Dict[str, Dict[str, Any]] = {}
    _prepared_lock = threading.Lock()
    from functools import lru_cache

    @lru_cache(maxsize=8)
    def cached_store(root, kind):
        from pathlib import Path
        from phone_agent.review_queue import ReviewQueue
        from phone_agent.social import SocialStore
        return (ReviewQueue if kind == "reviews" else SocialStore)(Path(root) / (kind + ".sqlite3"))

    # ── Auth ────────────────────────────────────────────────────────

    @api.before_request
    def _check_token():
        """Require a bearer token when CONTENTSWARM_API_TOKEN is set on the server."""
        token = os.environ.get("CONTENTSWARM_API_TOKEN")
        if not token:
            return None
        auth_header = request.headers.get("Authorization", "")
        if hmac.compare_digest(auth_header.encode("utf-8", "surrogatepass"), f"Bearer {token}".encode("utf-8", "surrogatepass")):
            return None
        # Browser sessions are authenticated and CSRF-checked by console.py.
        if session.get("console"):
            return None
        return jsonify({"error": "Unauthorized"}), 401

    def review_queue():
        from phone_agent.review_queue import ReviewQueue
        from pathlib import Path
        root = os.environ.get("CONTENTSWARM_STATE_DIR", str(Path.home() / ".local/state/contentswarm"))
        return cached_store(root, "reviews")

    def social_store():
        from phone_agent.social import SocialStore
        from pathlib import Path
        root = os.environ.get("CONTENTSWARM_STATE_DIR", str(Path.home() / ".local/state/contentswarm"))
        return cached_store(root, "social")

    def authorize_phone_operation(phone):
        review_queue().authorize_phone(phone, request.headers.get("X-ContentSwarm-Review") if has_request_context() else None,
                                       request.headers.get("X-ContentSwarm-Lease") if has_request_context() else None)

    if state.get("phone_manager"):
        state["phone_manager"].operation_authorizer = authorize_phone_operation

    def owner_required():
        if not session.get("console") or not hmac.compare_digest(request.headers.get("X-CSRF-Token", "").encode("utf-8", "surrogatepass"), session.get("csrf", "!").encode("utf-8", "surrogatepass")):
            return jsonify(error="This change requires the owner's console session"), 403
        return None

    @api.route("/social/<collection>", methods=["GET", "POST"])
    def social_collection(collection):
        if collection not in ("accounts", "schedules", "jobs"):
            return jsonify(error="Unknown collection"), 404
        store = social_store()
        if request.method == "GET":
            return jsonify({collection: store.list(collection)})
        error = owner_required()
        if error:
            return error
        data, error = _json_body()
        if error:
            return error
        try:
            if collection == "accounts":
                return jsonify(store.account(data)), 201
            if collection == "schedules":
                return jsonify(store.schedule(data)), 201
            return jsonify(store.enqueue(data.get("account_id"), data.get("prompt"), data)), 201
        except (ValueError, LookupError) as exc:
            return jsonify(error=str(exc)), 400

    @api.route("/social/accounts/<account_id>/memory", methods=["GET", "POST"])
    def social_memory(account_id):
        store = social_store()
        try:
            if request.method == "GET":
                context = store.context(account_id, request.args.get("q", ""), request.args.get("thread", ""))
                context["reviews"] = []
                remaining = 12000
                reviews = review_queue().list()
                thread = request.args.get("thread", "")
                if thread:
                    reviews.sort(key=lambda r: r.get("source_url") == thread, reverse=True)
                for r in reviews:
                    if r.get("account_id") != account_id:
                        continue
                    excerpt = {k: r[k] for k in ("id", "status", "source_url", "original", "reply", "updated_at") if k in r}
                    size = len(json.dumps(excerpt))
                    if size <= remaining:
                        context["reviews"].append(excerpt)
                        remaining -= size
                return jsonify(context)
            data, error = _json_body()
            if error:
                return error
            # Only the owner can mark knowledge trusted; captured speech/replies are data.
            trusted = bool(session.get("console") and not owner_required())
            return jsonify(store.remember(account_id, data, trusted)), 201
        except (ValueError, LookupError) as exc:
            return jsonify(error=str(exc)), 400

    @api.post("/social/schedules/<item_id>/pause")
    def social_pause(item_id):
        error = owner_required()
        if error:
            return error
        data, error = _json_body()
        if error:
            return error
        try:
            return jsonify(social_store().pause(item_id, data.get("revision")))
        except (ValueError, LookupError) as exc:
            return jsonify(error=str(exc)), 409

    @api.post("/social/tick")
    def social_tick():
        return jsonify(jobs=social_store().tick())

    @api.post("/social/claim")
    def social_claim():
        return jsonify(job=social_store().claim())

    @api.post("/social/jobs/<item_id>/finish")
    def social_finish(item_id):
        data, error = _json_body()
        if error:
            return error
        try:
            return jsonify(social_store().finish(item_id, data.get("result"), data.get("error")))
        except (ValueError, LookupError) as exc:
            return jsonify(error=str(exc)), 409

    @api.route("/reviews", methods=["GET", "POST"])
    def reviews():
        if request.method == "GET":
            return jsonify(reviews=review_queue().list())
        data, error = _json_body()
        if error:
            return error
        _, error = _phone_device(data.get("phone", "")) if isinstance(data.get("phone"), str) else (None, (jsonify(error="phone required"), 400))
        if error:
            return error
        if data.get("account_id"):
            try:
                account = social_store().get("accounts", data["account_id"])
                if data.get("platform") != account["platform"] or data.get("account") != account["handle"] or data.get("phone") not in account["phones"]:
                    return jsonify(error="Draft does not match its account profile and phone assignment"), 400
            except LookupError as exc:
                return jsonify(error=str(exc)), 400
        try:
            return jsonify(review_queue().create(data)), 201
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @api.post("/reviews/<item_id>/<action>")
    def review_action(item_id, action):
        if action in ("approve", "reject", "edit", "schedule", "cancel", "recover"):
            if not session.get("console") or not hmac.compare_digest(request.headers.get("X-CSRF-Token", "").encode("utf-8", "surrogatepass"), session.get("csrf", "!").encode("utf-8", "surrogatepass")):
                return jsonify(error="Review decisions require the owner's console session and CSRF token"), 403
        data, error = _json_body()
        if error:
            return error
        if action in ("complete", "uncertain"):
            data["lease_token"] = request.headers.get("X-ContentSwarm-Lease", "")
        try:
            if action == "recover" and hasattr(state.get("phone_manager"), "_get_phone_lock"):
                item = next((r for r in review_queue().list() if r["id"] == item_id), None)
                if not item:
                    raise LookupError("review not found")
                lock = state["phone_manager"]._get_phone_lock(item["phone"])
                if not lock.acquire(blocking=False):
                    raise RuntimeError("Phone still performing an operation; wait before recovering")
                try:
                    return jsonify(review_queue().update(item_id, action, data))
                finally:
                    lock.release()
            if action in ("claim", "complete", "uncertain") and hasattr(state.get("phone_manager"), "phone_operation"):
                item = next((r for r in review_queue().list() if r["id"] == item_id), None)
                if not item:
                    raise LookupError("review not found")
                if action != "claim" and request.headers.get("X-ContentSwarm-Review") != item_id:
                    return jsonify(error="Delivery result requires its X-ContentSwarm-Review header"), 409
                with state["phone_manager"].phone_operation(item["phone"]):
                    return jsonify(review_queue().update(item_id, action, data))
            return jsonify(review_queue().update(item_id, action, data))
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 409

    def _get_phone_manager():
        return state.get("phone_manager")

    def _get_automation():
        return state.get("automation")

    def _get_socketio():
        return state.get("socketio")

    def _phone_device(phone_name: str):
        pm = _get_phone_manager()
        if not pm:
            return None, (jsonify({"error": "Phone manager not initialized"}), 503)
        if phone_name not in pm.phones:
            return None, (jsonify({"error": f"Phone '{phone_name}' not found"}), 404)
        return pm.phones[phone_name].device_id, None

    def _json_body():
        if not request.is_json:
            return None, (jsonify({"error": "Content-Type must be application/json"}), 415)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return None, (jsonify({"error": "JSON body must be an object"}), 400)
        return data, None

    def _bridge_error(error: Exception):
        if isinstance(error, ValueError):
            status = 400
        elif isinstance(error, LookupError):
            status = 404
        elif any(word in str(error).lower() for word in ("ambiguous", "busy")):
            status = 409
        else:
            status = 502
        return jsonify({"error": str(error)}), status

    def _emit_event(event: Dict[str, Any]):
        """Emit event via SocketIO to /ws/events namespace."""
        sio = _get_socketio()
        if sio:
            sio.emit("contentswarm_event", event, namespace="/ws/events")

    # ── Phone Management ────────────────────────────────────────────

    @api.route("/phones", methods=["GET"])
    def list_phones():
        """List all phones and their connection status."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        connections = {}
        try:
            connections = pm.check_connections()
        except Exception:
            pass

        phones = []
        for name, info in pm.phones.items():
            phones.append({
                "name": name,
                "device_id": info.device_id,
                "description": info.description,
                "tags": info.tags,
                "connected": connections.get(name, False),
                "is_current": name == pm.current_phone
            })

        return jsonify({"phones": phones, "total": len(phones)})

    @api.route("/phones/<phone_name>", methods=["GET"])
    def get_phone(phone_name: str):
        """Get details of a specific phone."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        info = pm.phones[phone_name]
        connected = False
        try:
            from phone_agent.adb import ADBConnection
            connected = ADBConnection().is_connected(info.device_id)
        except Exception:
            pass

        return jsonify({
            "name": info.name,
            "device_id": info.device_id,
            "description": info.description,
            "tags": info.tags,
            "connected": connected,
            "is_current": phone_name == pm.current_phone
        })

    @api.route("/phones/discover", methods=["POST"])
    def discover_phones():
        """Scan authorized ADB devices, add new ones, and persist the registry."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503
        try:
            added = pm.scan_and_add_devices()
            connections = pm.check_connections()
        except Exception as exc:
            return jsonify({"error": f"ADB discovery failed: {exc}"}), 502
        phones = [
            {
                "name": name,
                "device_id": info.device_id,
                "connected": connections.get(name, False),
            }
            for name, info in pm.phones.items()
        ]
        return jsonify({"added": added, "phones": phones, "total": len(phones)})

    @api.route("/phones/<phone_name>/task", methods=["POST"])
    def run_phone_task(phone_name: str):
        """
        Run a task on a specific phone (async).

        Request body: {"task": "Open TikTok and scroll"}
        Returns: {"task_id": "abc123", "status": "pending"}
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        data = request.json or {}
        task = data.get("task")
        if not task:
            return jsonify({"error": "task is required"}), 400

        task_id = pm.async_run(phone_name, task)

        _emit_event({
            "event": "task_submitted",
            "task_id": task_id,
            "phone": phone_name,
            "task": task,
            "timestamp": time.time()
        })

        return jsonify({"task_id": task_id, "status": "pending", "phone": phone_name}), 202

    @api.route("/phones/batch", methods=["POST"])
    def batch_run():
        """
        Run tasks on multiple phones in parallel.

        Request body: {"tasks": {"phone_01": "Open TikTok", "phone_02": "Open Instagram"}}
        Returns: {"task_ids": {"phone_01": "abc", "phone_02": "def"}}
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        data = request.json or {}
        tasks = data.get("tasks", {})
        if not tasks:
            return jsonify({"error": "tasks dict is required"}), 400

        # Validate all phones exist
        missing = [p for p in tasks if p not in pm.phones]
        if missing:
            return jsonify({"error": f"Phones not found: {missing}"}), 404

        task_ids = pm.batch_run_parallel(tasks)

        _emit_event({
            "event": "batch_submitted",
            "task_ids": task_ids,
            "phone_count": len(task_ids),
            "timestamp": time.time()
        })

        return jsonify({"task_ids": task_ids}), 202

    # ── Device / App Control (deterministic, no LLM) ────────────────

    @api.route("/apps", methods=["GET"])
    def list_apps():
        """List apps the agent can launch by name."""
        from phone_agent.config.apps import list_supported_apps

        return jsonify({"apps": sorted(list_supported_apps())})

    @api.route("/phones/<phone_name>/app", methods=["POST"])
    def launch_phone_app(phone_name: str):
        """
        Launch an app on a phone directly via ADB (no model call).

        Request body: {"app": "TikTok"}
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        data = request.json or {}
        app_name = data.get("app")
        if not app_name:
            return jsonify({"error": "app is required"}), 400

        from phone_agent.adb import launch_app

        device_id = pm.phones[phone_name].device_id
        try:
            with pm.phone_operation(phone_name):
                success = launch_app(app_name, device_id)
        except Exception as exc:
            return _bridge_error(exc)

        if not success:
            return jsonify({"error": f"App not found or failed to launch: {app_name}"}), 400

        _emit_event({
            "event": "app_launched",
            "phone": phone_name,
            "app": app_name,
            "timestamp": time.time()
        })

        return jsonify({"success": True, "phone": phone_name, "app": app_name})

    @api.route("/phones/<phone_name>/screenshot", methods=["GET"])
    def phone_screenshot(phone_name: str):
        """Capture and return the phone's current screen as a PNG image."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        from phone_agent.adb import get_screenshot

        device_id = pm.phones[phone_name].device_id
        try:
            shot = get_screenshot(device_id)
        except Exception as e:
            return jsonify({"error": f"Screenshot failed: {e}"}), 500

        png_bytes = base64.b64decode(shot.base64_data)
        return Response(
            png_bytes,
            mimetype="image/png",
            headers={
                "X-Screen-Width": str(shot.width),
                "X-Screen-Height": str(shot.height),
                "X-Sensitive": str(shot.is_sensitive).lower(),
            },
        )

    @api.route("/phones/<phone_name>/clock", methods=["GET"])
    def phone_clock(phone_name: str):
        """Read the device clock with its UTC offset, without changing it."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503
        if phone_name not in pm.phones:
            return jsonify({"error": "Phone not found"}), 404
        from phone_agent.bridge import device_clock
        try:
            return jsonify(device_clock(pm.phones[phone_name].device_id))
        except Exception:
            return jsonify({"error": "Phone clock unavailable"}), 503

    @api.route("/phones/<phone_name>/ui", methods=["GET"])
    def phone_ui(phone_name: str):
        """Dump the phone's current UI element tree (semantic addressing).

        Every element with its text, resource-id, content-desc, bounds, and
        center - the agent can pick a target without a vision model.
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        from phone_agent.bridge import ui_elements

        device_id = pm.phones[phone_name].device_id
        try:
            elements = ui_elements(device_id)
        except Exception as e:
            return jsonify({"error": f"UI dump failed: {e}"}), 500

        return jsonify({
            "phone": phone_name,
            "elements": elements,
            "count": len(elements),
        })

    @api.route("/phones/<phone_name>/action", methods=["POST"])
    def phone_action(phone_name: str):
        """Run one allowlisted semantic action with no model or raw ADB shell."""
        device_id, error = _phone_device(phone_name)
        if error:
            return error
        data, error = _json_body()
        if error:
            return error
        action = data.get("action")
        if not isinstance(action, str):
            return jsonify({"error": "action is required"}), 400
        if action.casefold() in ("tap", "key") and data.get("confirm") is not True:
            return jsonify({"error": "confirm must be true for every tap or key event"}), 409

        from phone_agent.bridge import semantic_action
        try:
            with _get_phone_manager().phone_operation(phone_name):
                result = semantic_action(
                    device_id,
                    action,
                    **{key: value for key, value in data.items() if key not in ("action", "confirm")},
                )
        except Exception as exc:
            return _bridge_error(exc)
        result["phone"] = phone_name
        _emit_event({
            "event": "device_action",
            "phone": phone_name,
            "action": action,
            "timestamp": time.time(),
        })
        return jsonify(result)

    @api.route("/phones/<phone_name>/communications/<channel>", methods=["GET"])
    def inspect_phone_messages(phone_name: str, channel: str):
        """Open SMS or WhatsApp and return its semantic UI tree."""
        device_id, error = _phone_device(phone_name)
        if error:
            return error
        from phone_agent.bridge import inspect_messages
        try:
            with _get_phone_manager().phone_operation(phone_name):
                elements = inspect_messages(device_id, channel)
        except Exception as exc:
            return _bridge_error(exc)
        return jsonify({
            "phone": phone_name,
            "channel": channel.casefold(),
            "elements": elements,
            "count": len(elements),
        })

    @api.route("/phones/<phone_name>/communications/compose", methods=["POST"])
    def compose_phone_message(phone_name: str):
        """Prepare an SMS or WhatsApp message without sending it."""
        device_id, error = _phone_device(phone_name)
        if error:
            return error
        data, error = _json_body()
        if error:
            return error
        channel = data.get("channel")
        recipient = data.get("recipient")
        body = data.get("body")
        label = data.get("recipient_label")
        from phone_agent.bridge import compose_message
        try:
            with _get_phone_manager().phone_operation(phone_name):
                with _prepared_lock:
                    for key in [
                        key for key, record in _prepared_messages.items()
                        if record["device_id"] == device_id
                    ]:
                        del _prepared_messages[key]
                result = compose_message(
                    device_id, channel, recipient, body, label,
                )
                prepared_token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(prepared_token.encode()).hexdigest()
                record = {
                    "device_id": device_id,
                    "channel": result["channel"],
                    "recipient": re.sub(r"[^0-9]", "", recipient),
                    "recipient_label": label,
                    "body_hash": hashlib.sha256(body.encode()).hexdigest(),
                    "expires_at": time.time() + _PREPARED_TTL_SECONDS,
                }
                with _prepared_lock:
                    for key in [
                        key for key, previous in _prepared_messages.items()
                        if previous["device_id"] == device_id
                    ]:
                        del _prepared_messages[key]
                    _prepared_messages[token_hash] = record
        except Exception as exc:
            return _bridge_error(exc)
        result["prepared_token"] = prepared_token
        result["expires_in"] = _PREPARED_TTL_SECONDS
        result["phone"] = phone_name
        _emit_event({
            "event": "message_composed",
            "phone": phone_name,
            "channel": result["channel"],
            "timestamp": time.time(),
        })
        return jsonify(result)

    @api.route("/phones/<phone_name>/communications/send", methods=["POST"])
    def send_phone_message(phone_name: str):
        """Send one prepared message after an explicit caller confirmation."""
        device_id, error = _phone_device(phone_name)
        if error:
            return error
        data, error = _json_body()
        if error:
            return error
        if data.get("confirm") is not True:
            return jsonify({"error": "confirm must be true for a send"}), 409

        token = data.get("prepared_token")
        channel = data.get("channel")
        recipient = data.get("recipient")
        body = data.get("expected_body")
        if not all(isinstance(value, str) and value for value in (token, channel, recipient, body)):
            return jsonify({"error": "prepared_token, channel, recipient, and expected_body are required"}), 400
        from phone_agent.bridge import send_composed_message
        try:
            with _get_phone_manager().phone_operation(phone_name):
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                with _prepared_lock:
                    record = _prepared_messages.pop(token_hash, None)
                if record is None:
                    return jsonify({"error": "prepared token is invalid or already used"}), 409
                matches = (
                    record["expires_at"] >= time.time()
                    and record["device_id"] == device_id
                    and record["channel"] == channel.casefold()
                    and record["recipient"] == re.sub(r"[^0-9]", "", recipient)
                    and record["body_hash"] == hashlib.sha256(body.encode()).hexdigest()
                )
                if not matches:
                    return jsonify({"error": "prepared message expired or no longer matches"}), 409
                result = send_composed_message(
                    device_id, channel, recipient, body, record["recipient_label"]
                )
        except Exception as exc:
            return _bridge_error(exc)
        result["phone"] = phone_name
        _emit_event({
            "event": "message_sent" if result["verified"] else "message_unverified",
            "phone": phone_name,
            "channel": result["channel"],
            "verified": result["verified"],
            "timestamp": time.time(),
        })
        return jsonify(result), (200 if result["verified"] else 502)

    @api.route("/phones/<phone_name>/current_app", methods=["GET"])
    def phone_current_app(phone_name: str):
        """Get the app currently in the foreground on a phone."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        from phone_agent.adb.device import get_foreground

        device_id = pm.phones[phone_name].device_id
        try:
            current = get_foreground(device_id)
        except Exception as e:
            return jsonify({"error": f"Failed to read current app: {e}"}), 500

        return jsonify({"phone": phone_name, **current})

    @api.route("/phones/<phone_name>/installed", methods=["GET"])
    def phone_installed_apps(phone_name: str):
        """Discover third-party apps installed on a phone via ADB."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        from phone_agent.flows import list_installed_apps

        device_id = pm.phones[phone_name].device_id
        try:
            apps = list_installed_apps(device_id)
        except Exception as e:
            return jsonify({"error": f"App discovery failed: {e}"}), 500

        return jsonify({"phone": phone_name, "installed": apps, "count": len(apps)})

    # ── Flow Learning & Replay ──────────────────────────────────────

    def _flows_dir() -> str:
        return os.environ.get("CONTENTSWARM_FLOWS_DIR", "flows")

    @api.route("/phones/<phone_name>/learn", methods=["POST"])
    def learn_flow(phone_name: str):
        """
        Learn a flow: the vision model drives the task once while every
        replayable action is recorded with its exact press points.

        Request body: {"task": "Open TikTok and post ...", "flow_name": "tiktok-post"}
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        data = request.json or {}
        task = data.get("task")
        flow_name = data.get("flow_name")
        if not task or not flow_name:
            return jsonify({"error": "task and flow_name are required"}), 400

        from phone_agent.flows import flow_path
        try:
            flow_path(flow_name, _flows_dir())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        task_id = pm.async_learn(phone_name, task, flow_name, flows_dir=_flows_dir())

        _emit_event({
            "event": "learn_submitted",
            "task_id": task_id,
            "phone": phone_name,
            "flow": flow_name,
            "timestamp": time.time()
        })
        return jsonify({"task_id": task_id, "status": "pending", "flow": flow_name}), 202

    @api.route("/phones/<phone_name>/replay", methods=["POST"])
    def replay_flow(phone_name: str):
        """
        Replay a learned flow deterministically - exact presses at the
        recorded points via ADB, no model calls.

        Request body: {"flow_name": "tiktok-post", "speed": 1.0}
        """
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        data = request.json or {}
        flow_name = data.get("flow_name")
        if not flow_name:
            return jsonify({"error": "flow_name is required"}), 400
        try:
            speed = float(data.get("speed", 1.0))
        except (TypeError, ValueError):
            return jsonify({"error": "speed must be a number"}), 400

        from phone_agent.flows import flow_path
        try:
            if not flow_path(flow_name, _flows_dir()).exists():
                return jsonify({"error": f"Flow '{flow_name}' not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        task_id = pm.async_replay(phone_name, flow_name, flows_dir=_flows_dir(), speed=speed)
        return jsonify({"task_id": task_id, "status": "pending", "flow": flow_name}), 202

    @api.route("/flows", methods=["GET"])
    def get_flows():
        """List all learned flows."""
        from phone_agent.flows import list_flows
        return jsonify({"flows": list_flows(_flows_dir())})

    @api.route("/flows/<flow_name>", methods=["GET"])
    def get_flow_detail(flow_name: str):
        """Get the full recorded steps of one flow."""
        from phone_agent.flows import load_flow
        try:
            flow = load_flow(flow_name, _flows_dir())
        except FileNotFoundError:
            return jsonify({"error": f"Flow '{flow_name}' not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(flow.to_dict())

    @api.route("/flows/<flow_name>/runs", methods=["GET"])
    def get_flow_runs(flow_name: str):
        """Replay run reports for a flow, newest first.

        Each report is the expected-vs-actual ledger of one replay: per step,
        whether it succeeded and how it landed ("element" = the recorded
        semantic target was found and tapped, i.e. verified; "coords" =
        coordinate fallback, unverified).
        """
        from phone_agent.flows import list_run_reports
        try:
            reports = list_run_reports(flow_name, _flows_dir())
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"flow": flow_name, "runs": reports, "count": len(reports)})

    def _parse_days():
        """Positive int from ?days= (default 30), or None when invalid."""
        try:
            days = int(request.args.get("days", 30))
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

    _ZERO_HEALTH = {"runs": 0, "executed": 0, "failed": 0, "verified": 0,
                    "verified_rate": 0.0, "last_run": None}

    @api.route("/flows/health", methods=["GET"])
    def flows_health():
        """Verified-rate health per flow, aggregated from the run-report index.

        Flows with no indexed runs in the window appear zero-filled, so a
        never-replayed flow is visible rather than silently absent.
        """
        days = _parse_days()
        if days is None:
            return jsonify({"error": "days must be a positive number"}), 400

        from phone_agent.flows import list_flows
        from phone_agent.runs_index import health

        rows = health(days=days, flows_dir=_flows_dir())
        seen = {r["flow"] for r in rows}
        rows += [
            {"flow": f["name"], **_ZERO_HEALTH}
            for f in list_flows(_flows_dir()) if f["name"] not in seen
        ]
        return jsonify({"days": days, "flows": rows})

    @api.route("/flows/<flow_name>/health", methods=["GET"])
    def flow_health(flow_name: str):
        """Verified-rate health for one flow, aggregated from the run-report index."""
        days = _parse_days()
        if days is None:
            return jsonify({"error": "days must be a positive number"}), 400

        from phone_agent.runs_index import health
        rows = health(flow_name=flow_name, days=days, flows_dir=_flows_dir())
        if rows:  # indexed history wins, even if the flow file was deleted
            return jsonify({"days": days, **rows[0]})

        from phone_agent.flows import flow_path
        try:
            known = flow_path(flow_name, _flows_dir()).exists()
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not known:  # a typo must not look like a healthy unreplayed flow
            return jsonify({"error": f"Flow '{flow_name}' not found"}), 404
        return jsonify({"days": days, "flow": flow_name, **_ZERO_HEALTH})

    # ── Task Status ─────────────────────────────────────────────────

    @api.route("/tasks/<task_id>", methods=["GET"])
    def get_task(task_id: str):
        """Check the status of an async task."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        status = pm.get_task_status(task_id)
        if not status:
            return jsonify({"error": f"Task '{task_id}' not found"}), 404

        return jsonify(status)

    @api.route("/tasks", methods=["GET"])
    def list_tasks():
        """List all tracked tasks."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        return jsonify({"tasks": pm.get_all_tasks()})

    # ── Pipeline Control ────────────────────────────────────────────

    @api.route("/pipeline/discover", methods=["POST"])
    def pipeline_discover():
        """
        Discover trending content on a platform.

        Request body: {"platform": "tiktok", "phone": "phone_01", "limit": 10}
        """
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        data = request.json or {}
        platform_str = data.get("platform", "tiktok")
        phone = data.get("phone")
        limit = data.get("limit", 10)

        from phone_agent.social_automation import Platform
        try:
            platform = Platform(platform_str)
        except ValueError:
            return jsonify({"error": f"Invalid platform: {platform_str}"}), 400

        if not phone:
            phones = automation.platform_phones.get(platform, [])
            if not phones:
                return jsonify({"error": "No phone assigned to this platform"}), 400
            phone = phones[0]

        # Run discovery in background
        result_holder = {"result": None, "error": None}
        task_id = str(uuid.uuid4())[:8]

        def _discover():
            try:
                trending = automation.discover_trending(platform, phone, limit)
                result_holder["result"] = [
                    {"title": t.title, "url": t.url, "views": t.views,
                     "engagement": t.engagement, "hashtags": t.hashtags}
                    for t in trending
                ]
            except Exception as e:
                result_holder["error"] = str(e)

        thread = threading.Thread(target=_discover, daemon=True)
        thread.start()

        return jsonify({
            "message": f"Discovery started on {platform_str} via {phone}",
            "limit": limit
        }), 202

    @api.route("/pipeline/run", methods=["POST"])
    def pipeline_run():
        """
        Run the full viral content pipeline.

        Request body: {"discovery_limit": 10, "content_to_generate": 3}
        """
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        data = request.json or {}
        discovery_limit = data.get("discovery_limit", 10)
        content_to_generate = data.get("content_to_generate", 3)

        def _run_pipeline():
            try:
                automation.run_viral_pipeline(
                    discovery_limit=discovery_limit,
                    content_to_generate=content_to_generate
                )
            except Exception as e:
                _emit_event({
                    "event": "pipeline_error",
                    "error": str(e),
                    "timestamp": time.time()
                })

        thread = threading.Thread(target=_run_pipeline, daemon=True)
        thread.start()

        _emit_event({
            "event": "pipeline_run_requested",
            "discovery_limit": discovery_limit,
            "content_to_generate": content_to_generate,
            "timestamp": time.time()
        })

        return jsonify({
            "message": "Pipeline started",
            "discovery_limit": discovery_limit,
            "content_to_generate": content_to_generate
        }), 202

    @api.route("/pipeline/status", methods=["GET"])
    def pipeline_status():
        """Get current pipeline status."""
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        return jsonify(automation.get_pipeline_status())

    @api.route("/pipeline/trending", methods=["GET"])
    def pipeline_trending():
        """Get the trending content queue."""
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        return jsonify({"trending": automation.get_trending_queue()})

    @api.route("/pipeline/content", methods=["GET"])
    def pipeline_content():
        """Get the generated content queue."""
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        return jsonify({"content": automation.get_content_queue()})

    # ── Assignments ─────────────────────────────────────────────────

    @api.route("/assignments", methods=["GET"])
    def get_assignments():
        """Get current phone-to-platform assignments."""
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        assignments = {
            platform.value: phones
            for platform, phones in automation.platform_phones.items()
        }
        return jsonify({"assignments": assignments})

    @api.route("/assignments", methods=["POST"])
    def set_assignments():
        """
        Set phone-to-platform assignments.

        Request body: {"tiktok": ["phone_01", "phone_02"], "instagram_reels": ["phone_03"]}
        """
        automation = _get_automation()
        if not automation:
            return jsonify({"error": "Automation not initialized"}), 503

        data = request.json or {}

        from phone_agent.social_automation import Platform
        assignments = {}
        for platform_str, phones in data.items():
            try:
                platform = Platform(platform_str)
                assignments[platform] = phones
            except ValueError:
                return jsonify({"error": f"Invalid platform: {platform_str}"}), 400

        automation.assign_phones(assignments)

        _emit_event({
            "event": "assignments_updated",
            "assignments": data,
            "timestamp": time.time()
        })

        return jsonify({"message": "Assignments updated", "assignments": data})

    # ── Status & Analytics ──────────────────────────────────────────

    @api.route("/status", methods=["GET"])
    def system_status():
        """Get overall system status."""
        pm = _get_phone_manager()
        automation = _get_automation()

        from phone_agent.bridge import installed as bridge_installed

        status = {
            "phones": {
                "total": len(pm.phones) if pm else 0,
                "connected": 0,
                "current": pm.current_phone if pm else None
            },
            "bridge": {"installed": bridge_installed()},
            "pipeline": automation.get_pipeline_status() if automation else None,
            "timestamp": time.time()
        }

        if pm:
            try:
                connections = pm.check_connections()
                status["phones"]["connected"] = sum(1 for v in connections.values() if v)
            except Exception:
                pass

        return jsonify(status)

    @api.route("/analytics", methods=["GET"])
    def get_analytics():
        """Get analytics data."""
        return jsonify(state.get("analytics", {}))

    return api
