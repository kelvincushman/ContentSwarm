"""Nova REST API for ContentSwarm — standalone Flask server on port 8771.

Endpoints:
    GET  /status   — list all phones + connection status + persona
    POST /post     — queue and execute a post {persona, platform, text, media_path}
    POST /discover — run device discovery, update config
    GET  /queue    — show pending posts per persona

Run:
    python nova_api.py
"""

import threading

from flask import Flask, jsonify, request

from phone_agent.content_queue import get_all, get_pending, mark_failed, mark_sent, queue_post
from phone_agent.device_discovery import (
    discover_devices,
    get_device_for_persona,
    get_persona_platforms,
    load_config,
    map_devices_to_personas,
)
from phone_agent.posting.tiktok import post_to_tiktok
from phone_agent.posting.twitter import post_to_twitter

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLATFORM_POSTERS = {
    "twitter": lambda dev, text, media: post_to_twitter(dev, text),
    "x": lambda dev, text, media: post_to_twitter(dev, text),
    "tiktok": lambda dev, text, media: post_to_tiktok(dev, text, media),
}


def _execute_post(persona: str, platform: str, text: str, media_path: str | None, post_id: str):
    """Background worker that executes a post and updates queue state."""
    device_id = get_device_for_persona(persona)
    if not device_id:
        print(f"[nova] No device mapped for persona '{persona}'")
        mark_failed(post_id)
        return

    poster = PLATFORM_POSTERS.get(platform.lower())
    if not poster:
        print(f"[nova] No posting workflow for platform '{platform}'")
        mark_failed(post_id)
        return

    try:
        success = poster(device_id, text, media_path)
        if success:
            mark_sent(post_id)
        else:
            mark_failed(post_id)
    except Exception as e:
        print(f"[nova] Post execution error: {e}")
        mark_failed(post_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/status", methods=["GET"])
def status():
    """List all phones, connection status, and current persona."""
    config = load_config()
    from phone_agent.adb.connection import ADBConnection

    conn = ADBConnection()
    connected_devices = {d.device_id for d in conn.list_devices() if d.status == "device"}

    phones = []
    for phone in config.get("phones", []):
        dev_id = phone.get("device_id", "auto")
        phones.append(
            {
                "name": phone["name"],
                "persona": phone.get("persona", phone["name"]),
                "device_id": dev_id,
                "platforms": phone.get("platforms", []),
                "connected": dev_id in connected_devices if dev_id != "auto" else False,
                "description": phone.get("description", ""),
            }
        )

    return jsonify({"phones": phones, "total": len(phones)})


@app.route("/post", methods=["POST"])
def post():
    """Queue and execute a post.

    Body JSON: {persona, platform, text, media_path (optional)}
    """
    data = request.get_json(force=True)
    persona = data.get("persona", "").lower()
    platform = data.get("platform", "").lower()
    text = data.get("text", "")
    media_path = data.get("media_path")

    if not persona or not platform or not text:
        return jsonify({"error": "persona, platform, and text are required"}), 400

    # Validate persona has this platform
    allowed = get_persona_platforms(persona)
    if allowed and platform not in allowed:
        return (
            jsonify(
                {
                    "error": f"'{persona}' is not configured for '{platform}'",
                    "allowed_platforms": allowed,
                }
            ),
            400,
        )

    post_id = queue_post(persona, platform, text, media_path)

    # Execute in background thread so API returns immediately
    thread = threading.Thread(
        target=_execute_post,
        args=(persona, platform, text, media_path, post_id),
        daemon=True,
    )
    thread.start()

    return jsonify({"post_id": post_id, "status": "queued", "persona": persona, "platform": platform})


@app.route("/discover", methods=["POST"])
def discover():
    """Run device discovery and update config."""
    devices = discover_devices()
    config = map_devices_to_personas(devices)

    phones_summary = []
    for phone in config.get("phones", []):
        phones_summary.append(
            {
                "name": phone["name"],
                "device_id": phone.get("device_id", "auto"),
            }
        )

    return jsonify(
        {
            "discovered_devices": devices,
            "mapped_phones": phones_summary,
        }
    )


@app.route("/queue", methods=["GET"])
def queue():
    """Show pending posts per persona."""
    persona_filter = request.args.get("persona")

    if persona_filter:
        pending = get_pending(persona_filter)
    else:
        pending = get_pending()

    # Group by persona
    by_persona: dict[str, list] = {}
    for post in pending:
        p = post["persona"]
        by_persona.setdefault(p, []).append(post)

    return jsonify({"pending_count": len(pending), "by_persona": by_persona})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("[nova_api] Starting ContentSwarm Nova API on port 8771...")
    app.run(host="0.0.0.0", port=8771, debug=False)
