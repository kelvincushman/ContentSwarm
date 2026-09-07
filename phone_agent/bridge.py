"""Semantic UI bridge — adb-agent-bridge integration.

Element-addressed control via the accessibility tree that `uiautomator dump`
exposes over plain ADB (https://github.com/kelvincushman/adb-agent-bridge):
taps land on element centers instead of model-guessed pixels, and text commits
in ~100ms with no IME dance. Every helper degrades cleanly — callers treat a
False/None result as "use the legacy vision/ADB path".
"""

import re
import threading
import time
from typing import Any, Dict, List, Optional

try:
    from adb_agent_bridge import Bridge
except ImportError:  # optional until the fleet rollout completes
    Bridge = None

_bridges: Dict[Optional[str], Any] = {}
_locks: Dict[Optional[str], threading.Lock] = {}
_prefetched: Dict[Optional[str], Any] = {}
_registry_lock = threading.Lock()

SUPPORTED_CHANNELS = ("sms", "whatsapp")
ALLOWED_KEYS = {
    "BACK", "HOME", "ENTER", "TAB", "ESCAPE", "DPAD_UP", "DPAD_DOWN",
    "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER", "DEL", "FORWARD_DEL",
    "PAGE_UP", "PAGE_DOWN",
}
_MAX_TEXT = 4000
_MAX_COORD = 10000
_SEND_IDS = {
    "sms": ("send_message", "send_button", "send"),
    "whatsapp": ("send",),
}
_SEND_WORDS = ("send",)


def installed() -> bool:
    """True if the adb-agent-bridge library is importable."""
    return Bridge is not None


def device_lock(device_id: str | None) -> threading.Lock:
    """One lock per device: serializes bridge operations (API /ui vs handler
    taps/typing) so concurrent callers never interleave device commands."""
    with _registry_lock:
        if device_id not in _locks:
            _locks[device_id] = threading.Lock()
        return _locks[device_id]


def get_bridge(device_id: str | None = None):
    """Session-cached Bridge for a device, or None if the library is missing."""
    if Bridge is None:
        return None
    with _registry_lock:
        if device_id not in _bridges:
            _bridges[device_id] = Bridge(device_id)
        return _bridges[device_id]


def is_available(device_id: str | None = None) -> bool:
    """True if the UI tree can actually be dumped on this device."""
    bridge = get_bridge(device_id)
    if bridge is None:
        return False
    try:
        with device_lock(device_id):
            bridge.ui()
        return True
    except Exception:
        return False


def ui_elements(device_id: str | None = None) -> List[Dict[str, Any]]:
    """Current screen elements as JSON-able dicts (for the API and CLI)."""
    bridge = get_bridge(device_id)
    if bridge is None:
        raise RuntimeError(
            "adb-agent-bridge is not installed (pip install -r requirements.txt)"
        )
    with device_lock(device_id):
        elements = bridge.ui()
    return [
        {
            "text": e.text,
            "id": e.id,
            "desc": e.desc,
            "class": e.cls,
            "bounds": list(e.bounds),
            "center": list(e.center),
            "clickable": e.clickable,
            "scrollable": e.scrollable,
            "enabled": e.enabled,
        }
        for e in elements
    ]


def tap_target(
    device_id: str | None = None,
    text: str | None = None,
    id: str | None = None,
    desc: str | None = None,
) -> bool:
    """Tap an element found by semantic target. True only if found and tapped."""
    bridge = get_bridge(device_id)
    if bridge is None:
        return False
    try:
        with device_lock(device_id):
            element = bridge.find(text=text, id=id, desc=desc)
            if element is None:
                return False
            bridge.tap(element)
        return True
    except Exception:
        return False


def prefetch_ui(device_id: str | None = None) -> None:
    """Start the next UI dump in a background thread.

    The thread holds the per-device lock for the dump's full duration, so a
    prefetch can never interleave with taps, typing, or another dump. No-op
    when the library is missing; errors surface as a None prefetch result.
    """
    bridge = get_bridge(device_id)
    if bridge is None:
        return
    box: Dict[str, Any] = {}

    def _run():
        with device_lock(device_id):
            try:
                box["elements"] = bridge.ui()
            except Exception:
                pass

    thread = threading.Thread(target=_run, daemon=True)
    with _registry_lock:
        pending = _prefetched.get(device_id)
        if pending is not None and pending[0].is_alive():
            return  # an in-flight prefetch must not be overwritten and lost
        # a completed-but-unconsumed entry IS replaced on purpose: the consumer
        # wants the newest pre-action screen, and a leftover from an earlier
        # step (e.g. after a non-Tap step, which never consumes) is stale
        _prefetched[device_id] = (thread, box)
        thread.start()  # under the lock: an entry is never observably unstarted


def prefetched_ui(device_id: str | None = None):
    """Join and consume the last prefetch_ui() result: elements, or None."""
    with _registry_lock:
        entry = _prefetched.pop(device_id, None)
    if entry is None:
        return None
    thread, box = entry
    thread.join()
    return box.get("elements")


def type_text_fast(device_id: str | None, text: str, clear: bool = True) -> bool:
    """Type via the bridge (~100ms, IME switched once per session). True on success."""
    bridge = get_bridge(device_id)
    if bridge is None:
        return False
    try:
        with device_lock(device_id):
            bridge.text(text, clear=clear)
        return True
    except Exception:
        return False


def _require_bridge(device_id: str | None):
    bridge = get_bridge(device_id)
    if bridge is None:
        raise RuntimeError(
            "adb-agent-bridge is not installed (pip install -r requirements.txt)"
        )
    return bridge


def _validate_text(text: Any, *, required: bool = True) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if required and not text.strip():
        raise ValueError("text must not be empty")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text must be at most {_MAX_TEXT} characters")
    return text


def _matches(element: Any, text: str | None, id: str | None, desc: str | None) -> bool:
    if text is not None and text.casefold() not in element.text.casefold():
        return False
    if id is not None and element.id != id and not element.id.endswith("/" + id):
        return False
    if desc is not None and desc.casefold() not in element.desc.casefold():
        return False
    return True


def semantic_action(device_id: str | None, action: str, **params: Any) -> Dict[str, Any]:
    """Perform one allowlisted Android action with no model or raw shell access."""
    bridge = _require_bridge(device_id)
    with device_lock(device_id):
        if action == "tap":
            selectors = {key: params.get(key) for key in ("text", "id", "desc")}
            selectors = {key: value for key, value in selectors.items() if value is not None}
            if not selectors:
                raise ValueError("tap requires text, id, or desc")
            if any(not isinstance(value, str) or not value.strip() for value in selectors.values()):
                raise ValueError("tap selectors must be non-empty strings")
            matches = [
                element for element in bridge.ui()
                if _matches(element, selectors.get("text"), selectors.get("id"), selectors.get("desc"))
                and element.clickable and element.enabled
            ]
            if not matches:
                raise LookupError("no enabled clickable element matched")
            if len(matches) > 1:
                raise RuntimeError("selector is ambiguous; provide another selector")
            bridge.tap(matches[0])
            return {"success": True, "action": action, "target": list(matches[0].center)}

        if action == "type":
            value = _validate_text(params.get("text"), required=False)
            clear = params.get("clear", True)
            if not isinstance(clear, bool):
                raise ValueError("clear must be a boolean")
            bridge.text(value, clear=clear)
            return {"success": True, "action": action, "characters": len(value)}

        if action == "key":
            key = params.get("key")
            if not isinstance(key, str) or key.upper() not in ALLOWED_KEYS:
                raise ValueError("key is not allowlisted")
            bridge.key(key.upper())
            return {"success": True, "action": action, "key": key.upper()}

        if action == "swipe":
            values = []
            for name in ("x1", "y1", "x2", "y2"):
                value = params.get(name)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_COORD:
                    raise ValueError(f"{name} must be an integer from 0 to {_MAX_COORD}")
                values.append(value)
            duration = params.get("duration_ms", 300)
            if isinstance(duration, bool) or not isinstance(duration, int) or not 50 <= duration <= 5000:
                raise ValueError("duration_ms must be an integer from 50 to 5000")
            bridge.swipe(*values, ms=duration)
            return {"success": True, "action": action, "duration_ms": duration}

    raise ValueError("action must be tap, type, key, or swipe")


def _channel(channel: Any) -> str:
    if not isinstance(channel, str) or channel.casefold() not in SUPPORTED_CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(SUPPORTED_CHANNELS)}")
    return channel.casefold()


def inspect_messages(device_id: str | None, channel: str) -> List[Dict[str, Any]]:
    """Open a messaging surface and return its semantic UI tree."""
    channel = _channel(channel)
    bridge = _require_bridge(device_id)
    with device_lock(device_id):
        if channel == "sms":
            bridge.open_uri("sms:")
        else:
            from phone_agent.adb import launch_app
            if not launch_app("WhatsApp", device_id):
                raise RuntimeError("WhatsApp is not installed or failed to launch")
        time.sleep(1)
        elements = bridge.ui()
    return [
        {
            "text": e.text, "id": e.id, "desc": e.desc, "class": e.cls,
            "bounds": list(e.bounds), "center": list(e.center),
            "clickable": e.clickable, "scrollable": e.scrollable, "enabled": e.enabled,
        }
        for e in elements
    ]


def compose_message(
    device_id: str | None, channel: str, recipient: str, body: str
) -> Dict[str, Any]:
    """Open a prepared SMS or WhatsApp composer. This never taps Send."""
    channel = _channel(channel)
    body = _validate_text(body)
    if not isinstance(recipient, str) or not re.fullmatch(r"\+?[0-9][0-9 ()-]{2,30}", recipient):
        raise ValueError("recipient must be a phone number")
    bridge = _require_bridge(device_id)
    with device_lock(device_id):
        if channel == "sms":
            bridge.compose_sms(recipient, body)
        else:
            bridge.compose_whatsapp(recipient, body)
    return {
        "success": True,
        "channel": channel,
        "recipient": recipient,
        "characters": len(body),
        "sent": False,
    }


def _is_editor(element: Any) -> bool:
    return element.enabled and element.cls.endswith("EditText")


def _is_send(element: Any, channel: str) -> bool:
    element_id = element.id.rsplit("/", 1)[-1].casefold()
    text = element.text.strip().casefold()
    desc = element.desc.strip().casefold()
    return (
        element.enabled
        and element.clickable
        and (
            element_id in _SEND_IDS[channel]
            or text in _SEND_WORDS
            or desc in _SEND_WORDS
        )
    )


def send_composed_message(
    device_id: str | None, channel: str, expected_body: str
) -> Dict[str, Any]:
    """Send one prepared message and verify that the composer cleared.

    The caller supplies the exact expected body and a separate confirmation at
    the API boundary. A state-changing tap is attempted once and never retried.
    """
    channel = _channel(channel)
    expected_body = _validate_text(expected_body)
    bridge = _require_bridge(device_id)
    with device_lock(device_id):
        before = bridge.ui()
        editors = [e for e in before if _is_editor(e) and expected_body in e.text]
        if not editors:
            raise LookupError("expected body is not present in an enabled message editor")
        sends = [e for e in before if _is_send(e, channel)]
        if not sends:
            raise LookupError("no enabled Send control found")
        if len(sends) > 1:
            raise RuntimeError("Send control is ambiguous; no action taken")
        bridge.tap(sends[0])
        time.sleep(1)
        after = bridge.ui()
    still_present = any(_is_editor(e) and expected_body in e.text for e in after)
    return {
        "success": not still_present,
        "channel": channel,
        "sent": not still_present,
        "verified": not still_present,
        "verification": "composer-cleared" if not still_present else "expected-body-still-present",
    }
