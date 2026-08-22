"""ContentSwarm API layer for external orchestration.

Exposes phone management, device/app control, pipeline control, and analytics
as REST + WebSocket endpoints that an external agent harness (Orphus via the
`contentswarm` CLI) can invoke.
"""

import base64
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from flask import Blueprint, Response, jsonify, request


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

    # ── Auth ────────────────────────────────────────────────────────

    @api.before_request
    def _check_token():
        """Require a bearer token when CONTENTSWARM_API_TOKEN is set on the server."""
        token = os.environ.get("CONTENTSWARM_API_TOKEN")
        if not token:
            return None
        auth_header = request.headers.get("Authorization", "")
        if auth_header == f"Bearer {token}":
            return None
        return jsonify({"error": "Unauthorized"}), 401

    def _get_phone_manager():
        return state.get("phone_manager")

    def _get_automation():
        return state.get("automation")

    def _get_socketio():
        return state.get("socketio")

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
        success = launch_app(app_name, device_id)

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

    @api.route("/phones/<phone_name>/current_app", methods=["GET"])
    def phone_current_app(phone_name: str):
        """Get the app currently in the foreground on a phone."""
        pm = _get_phone_manager()
        if not pm:
            return jsonify({"error": "Phone manager not initialized"}), 503

        if phone_name not in pm.phones:
            return jsonify({"error": f"Phone '{phone_name}' not found"}), 404

        from phone_agent.adb import get_current_app

        device_id = pm.phones[phone_name].device_id
        try:
            current = get_current_app(device_id)
        except Exception as e:
            return jsonify({"error": f"Failed to read current app: {e}"}), 500

        return jsonify({"phone": phone_name, "current_app": current})

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

    @api.route("/flows/health", methods=["GET"])
    def flows_health():
        """Verified-rate health per flow, aggregated from the run-report index."""
        try:
            days = int(request.args.get("days", 30))
        except (TypeError, ValueError):
            return jsonify({"error": "days must be a number"}), 400

        from phone_agent.runs_index import health
        return jsonify({"days": days, "flows": health(days=days, flows_dir=_flows_dir())})

    @api.route("/flows/<flow_name>/health", methods=["GET"])
    def flow_health(flow_name: str):
        """Verified-rate health for one flow, aggregated from the run-report index."""
        try:
            days = int(request.args.get("days", 30))
        except (TypeError, ValueError):
            return jsonify({"error": "days must be a number"}), 400

        from phone_agent.runs_index import health
        rows = health(flow_name=flow_name, days=days, flows_dir=_flows_dir())
        stats = rows[0] if rows else {
            "flow": flow_name,
            "runs": 0,
            "executed": 0,
            "failed": 0,
            "verified": 0,
            "verified_rate": 0.0,
            "last_run": None,
        }
        return jsonify({"days": days, **stats})

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
