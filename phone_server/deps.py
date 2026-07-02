"""Shared server dependencies: auth, per-device locks, ADB helpers.

Imported by the routers and the flow engine so behaviour (auth, locking,
coordinate handling, text entry) is identical everywhere.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import Header, HTTPException
from starlette.concurrency import run_in_threadpool

from phone_agent.adb import ADBConnection, get_screenshot
from phone_agent.adb.input import clear_text, detect_and_set_adb_keyboard, restore_keyboard, type_text

from phone_server.config import get_settings

settings = get_settings()
adb = ADBConnection()

# One lock per device: actions on the same phone serialize; different phones run
# in parallel.
_device_locks: dict[str, asyncio.Lock] = {}

# Cached screenshot-framebuffer size per device (for normalized coord scaling).
_screen_sizes: dict[str, tuple[int, int]] = {}


def lock_for(device_id: str) -> asyncio.Lock:
    lock = _device_locks.get(device_id)
    if lock is None:
        lock = asyncio.Lock()
        _device_locks[device_id] = lock
    return lock


# --- auth ------------------------------------------------------------------


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def check_ws_key(api_key: Optional[str]) -> bool:
    if not settings.api_key:
        return True
    return api_key == settings.api_key


# --- device helpers --------------------------------------------------------


def connected_ids() -> set[str]:
    return {d.device_id for d in adb.list_devices() if d.status == "device"}


async def require_device(device_id: str) -> None:
    ids = await run_in_threadpool(connected_ids)
    if device_id not in ids:
        raise HTTPException(
            status_code=404,
            detail=f"Device '{device_id}' not connected. Connected: {sorted(ids)}",
        )


def get_screen_size(device_id: str) -> tuple[int, int]:
    """(width, height) of the screenshot framebuffer, cached.

    Uses the screenshot — not `wm size` — so normalized 0-1000 coordinates line
    up exactly with what the model/agent sees (some devices report a different
    `wm size` than the actual capture).
    """
    if device_id in _screen_sizes:
        return _screen_sizes[device_id]
    shot = get_screenshot(device_id)
    size = (shot.width, shot.height)
    _screen_sizes[device_id] = size
    return size


def resolve_xy(device_id: str, x: int, y: int, normalized: bool) -> tuple[int, int]:
    """Absolute pixels from either absolute or 0-1000 normalized coords."""
    if not normalized:
        return int(x), int(y)
    w, h = get_screen_size(device_id)
    return int(x / 1000 * w), int(y / 1000 * h)


def norm_from_abs(device_id: str, x: int, y: int) -> list[int]:
    """Convert absolute pixels to 0-1000 normalized (for storing fallbacks)."""
    w, h = get_screen_size(device_id)
    return [int(x / w * 1000), int(y / h * 1000)]


def ensure_unlocked(device_id: str) -> bool:
    """If the phone is on the keyguard and has a stored PIN, unlock it.

    Returns True if the device is usable (already unlocked, or unlocked now).
    Called transparently before flows / app opens / agent runs so agents never
    handle the PIN themselves. Imports are local to avoid an import cycle.
    """
    from phone_server import adb_ext
    from phone_server.registry import REGISTRY

    if not adb_ext.keyguard_showing(device_id):
        return True
    pin = REGISTRY.get_pin(device_id)
    if not pin:
        return False
    return adb_ext.unlock(device_id, pin)


def do_type_text(device_id: str, text: str, clear: bool = True, restore: bool = True) -> None:
    """Type via the ADB Keyboard IME (Unicode/emoji-safe, base64 broadcast).

    restore=True  — switch to AdbIME, type, then switch the human keyboard back
                    (safe default for a shared phone).
    restore=False — leave AdbIME active ("set once, stay set"). Faster for bulk
                    posting; call POST /devices/{id}/keyboard/reset when done to
                    restore a normal keyboard.
    """
    original = detect_and_set_adb_keyboard(device_id)
    time.sleep(1.0)
    if clear:
        clear_text(device_id)
        time.sleep(0.5)
    type_text(text, device_id)
    time.sleep(0.5)
    if restore:
        restore_keyboard(original, device_id)
