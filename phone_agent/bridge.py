"""Semantic UI bridge — adb-agent-bridge integration.

Element-addressed control via the accessibility tree that `uiautomator dump`
exposes over plain ADB (https://github.com/kelvincushman/adb-agent-bridge):
taps land on element centers instead of model-guessed pixels, and text commits
in ~100ms with no IME dance. Every helper degrades cleanly — callers treat a
False/None result as "use the legacy vision/ADB path".
"""

from typing import Any, Dict, List, Optional

try:
    from adb_agent_bridge import Bridge
except ImportError:  # optional until the fleet rollout completes
    Bridge = None

_bridges: Dict[Optional[str], Any] = {}


def installed() -> bool:
    """True if the adb-agent-bridge library is importable."""
    return Bridge is not None


def get_bridge(device_id: str | None = None):
    """Session-cached Bridge for a device, or None if the library is missing."""
    if Bridge is None:
        return None
    if device_id not in _bridges:
        _bridges[device_id] = Bridge(device_id)
    return _bridges[device_id]


def is_available(device_id: str | None = None) -> bool:
    """True if the UI tree can actually be dumped on this device."""
    bridge = get_bridge(device_id)
    if bridge is None:
        return False
    try:
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
        }
        for e in bridge.ui()
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
        element = bridge.find(text=text, id=id, desc=desc)
        if element is None:
            return False
        bridge.tap(element)
        return True
    except Exception:
        return False


def type_text_fast(device_id: str | None, text: str, clear: bool = True) -> bool:
    """Type via the bridge (~100ms, IME switched once per session). True on success."""
    bridge = get_bridge(device_id)
    if bridge is None:
        return False
    try:
        bridge.text(text, clear=clear)
        return True
    except Exception:
        return False
