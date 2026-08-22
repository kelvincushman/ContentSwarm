"""Semantic UI bridge — adb-agent-bridge integration.

Element-addressed control via the accessibility tree that `uiautomator dump`
exposes over plain ADB (https://github.com/kelvincushman/adb-agent-bridge):
taps land on element centers instead of model-guessed pixels, and text commits
in ~100ms with no IME dance. Every helper degrades cleanly — callers treat a
False/None result as "use the legacy vision/ADB path".
"""

import threading
from typing import Any, Dict, List, Optional

try:
    from adb_agent_bridge import Bridge
except ImportError:  # optional until the fleet rollout completes
    Bridge = None

_bridges: Dict[Optional[str], Any] = {}
_locks: Dict[Optional[str], threading.Lock] = {}
_prefetched: Dict[Optional[str], Any] = {}
_registry_lock = threading.Lock()


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
        _prefetched[device_id] = (thread, box)
    thread.start()


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
