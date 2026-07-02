"""Device management, raw input primitives, and UI-hierarchy capture."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from phone_agent.adb import (
    back,
    double_tap,
    get_current_app,
    get_screenshot,
    home,
    launch_app,
    long_press,
    swipe,
    tap,
)
from phone_agent.actions.handler import ActionHandler

from phone_server import adb_ext
from phone_server.deps import (
    adb,
    do_type_text,
    get_screen_size,
    lock_for,
    require_api_key,
    require_device,
    resolve_xy,
)
from phone_server.schemas import (
    ActionBody,
    ConnectBody,
    KeyboardResetBody,
    KeyboardSetBody,
    LaunchBody,
    SwipeBody,
    TapBody,
    TypeBody,
    UnlockBody,
)

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/devices")
async def list_devices() -> dict[str, Any]:
    devices = await run_in_threadpool(adb.list_devices)
    return {
        "devices": [
            {
                "device_id": d.device_id,
                "status": d.status,
                "connection_type": d.connection_type.value,
                "model": d.model,
            }
            for d in devices
        ],
        "count": len(devices),
    }


@router.post("/devices/connect")
async def connect_device(body: ConnectBody) -> dict[str, Any]:
    ok, msg = await run_in_threadpool(adb.connect, body.address)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@router.post("/devices/disconnect")
async def disconnect_device(body: ConnectBody) -> dict[str, Any]:
    ok, msg = await run_in_threadpool(adb.disconnect, body.address)
    return {"ok": ok, "message": msg}


@router.post("/devices/{device_id}/tcpip")
async def enable_tcpip(device_id: str, port: int = 5555) -> dict[str, Any]:
    await require_device(device_id)
    ok, msg = await run_in_threadpool(adb.enable_tcpip, port, device_id)
    ip = await run_in_threadpool(adb.get_device_ip, device_id)
    return {"ok": ok, "message": msg, "device_ip": ip, "wifi_address": f"{ip}:{port}" if ip else None}


@router.get("/devices/{device_id}/screen_size")
async def screen_size(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    w, h = await run_in_threadpool(get_screen_size, device_id)
    return {"width": w, "height": h}


@router.get("/devices/{device_id}/current_app")
async def current_app(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    name = await run_in_threadpool(get_current_app, device_id)
    activity = await run_in_threadpool(adb_ext.get_current_activity, device_id)
    locked = await run_in_threadpool(adb_ext.keyguard_showing, device_id)
    return {"current_app": name, "activity": activity, "locked": locked}


@router.post("/devices/{device_id}/wake")
async def wake_device(device_id: str) -> dict[str, Any]:
    """Turn the screen on. Does NOT unlock a secure keyguard (enter the PIN on the device)."""
    await require_device(device_id)
    async with lock_for(device_id):
        await run_in_threadpool(adb_ext.wake, device_id)
        locked = await run_in_threadpool(adb_ext.keyguard_showing, device_id)
    return {"ok": True, "locked": locked}


@router.post("/devices/{device_id}/unlock")
async def unlock_device(device_id: str, body: UnlockBody) -> dict[str, Any]:
    """Unlock the phone by entering a KNOWN numeric PIN over ADB (not a bypass)."""
    await require_device(device_id)
    async with lock_for(device_id):
        ok = await run_in_threadpool(adb_ext.unlock, device_id, body.pin)
    return {"ok": ok, "locked": not ok}


@router.get("/devices/{device_id}/ui")
async def ui_hierarchy(device_id: str, interactable_only: bool = True) -> dict[str, Any]:
    """Return the parsed live UI hierarchy — the basis for selector-based control."""
    await require_device(device_id)
    async with lock_for(device_id):
        nodes = await run_in_threadpool(adb_ext.get_ui_elements, device_id)
    if interactable_only:
        nodes = [n for n in nodes if n["clickable"] or n["text"] or n["content_desc"]]
    return {"count": len(nodes), "nodes": nodes}


@router.get("/devices/{device_id}/packages")
async def packages(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    pkgs = await run_in_threadpool(adb_ext.list_third_party_packages, device_id)
    return {"count": len(pkgs), "packages": pkgs}


@router.get("/devices/{device_id}/screenshot")
async def screenshot(device_id: str, format: str = Query("png", pattern="^(png|base64)$")):
    await require_device(device_id)
    async with lock_for(device_id):
        shot = await run_in_threadpool(get_screenshot, device_id)
    if format == "base64":
        return {
            "width": shot.width,
            "height": shot.height,
            "is_sensitive": shot.is_sensitive,
            "image_base64": shot.base64_data,
        }
    return Response(
        content=base64.b64decode(shot.base64_data),
        media_type="image/png",
        headers={
            "X-Screen-Width": str(shot.width),
            "X-Screen-Height": str(shot.height),
            "X-Is-Sensitive": str(shot.is_sensitive).lower(),
        },
    )


# --- raw input -------------------------------------------------------------


@router.post("/devices/{device_id}/tap")
async def do_tap(device_id: str, body: TapBody) -> dict[str, Any]:
    await require_device(device_id)
    x, y = resolve_xy(device_id, body.x, body.y, body.normalized)
    async with lock_for(device_id):
        await run_in_threadpool(tap, x, y, device_id)
    return {"ok": True, "x": x, "y": y}


@router.post("/devices/{device_id}/double_tap")
async def do_double_tap(device_id: str, body: TapBody) -> dict[str, Any]:
    await require_device(device_id)
    x, y = resolve_xy(device_id, body.x, body.y, body.normalized)
    async with lock_for(device_id):
        await run_in_threadpool(double_tap, x, y, device_id)
    return {"ok": True, "x": x, "y": y}


@router.post("/devices/{device_id}/long_press")
async def do_long_press(device_id: str, body: TapBody) -> dict[str, Any]:
    await require_device(device_id)
    x, y = resolve_xy(device_id, body.x, body.y, body.normalized)
    async with lock_for(device_id):
        await run_in_threadpool(long_press, x, y, device_id=device_id)
    return {"ok": True, "x": x, "y": y}


@router.post("/devices/{device_id}/swipe")
async def do_swipe(device_id: str, body: SwipeBody) -> dict[str, Any]:
    await require_device(device_id)
    sx, sy = resolve_xy(device_id, body.start_x, body.start_y, body.normalized)
    ex, ey = resolve_xy(device_id, body.end_x, body.end_y, body.normalized)
    async with lock_for(device_id):
        await run_in_threadpool(swipe, sx, sy, ex, ey, body.duration_ms, device_id)
    return {"ok": True, "start": [sx, sy], "end": [ex, ey]}


@router.post("/devices/{device_id}/type")
async def do_type(device_id: str, body: TypeBody) -> dict[str, Any]:
    await require_device(device_id)
    async with lock_for(device_id):
        await run_in_threadpool(do_type_text, device_id, body.text, body.clear, body.restore)
    return {"ok": True, "typed": len(body.text), "restored": body.restore}


@router.get("/devices/{device_id}/keyboard")
async def keyboard_status(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    current = await run_in_threadpool(adb_ext.get_current_ime, device_id)
    enabled = await run_in_threadpool(adb_ext.list_imes, device_id, True)
    installed = await run_in_threadpool(adb_ext.list_imes, device_id, False)
    return {
        "current": current,
        "adb_keyboard_active": current == adb_ext.ADB_KEYBOARD_IME,
        "adb_keyboard_installed": adb_ext.ADB_KEYBOARD_IME in installed,
        "enabled": enabled,
        "installed": installed,
    }


@router.post("/devices/{device_id}/keyboard/set")
async def keyboard_set(device_id: str, body: KeyboardSetBody) -> dict[str, Any]:
    await require_device(device_id)
    ok = await run_in_threadpool(adb_ext.set_ime, body.ime, device_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Could not set IME '{body.ime}'")
    return {"ok": True, "ime": body.ime}


@router.post("/devices/{device_id}/keyboard/reset")
async def keyboard_reset(device_id: str, body: KeyboardResetBody | None = None) -> dict[str, Any]:
    """Switch off AdbIME back to a human keyboard (call after bulk restore=false typing)."""
    await require_device(device_id)
    prefer = body.prefer if body else None
    ime = await run_in_threadpool(adb_ext.reset_ime, device_id, prefer)
    if not ime:
        raise HTTPException(status_code=400, detail="No non-ADB keyboard available to switch to")
    return {"ok": True, "ime": ime}


@router.post("/devices/{device_id}/back")
async def do_back(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    async with lock_for(device_id):
        await run_in_threadpool(back, device_id)
    return {"ok": True}


@router.post("/devices/{device_id}/home")
async def do_home(device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    async with lock_for(device_id):
        await run_in_threadpool(home, device_id)
    return {"ok": True}


@router.post("/devices/{device_id}/launch")
async def do_launch(device_id: str, body: LaunchBody) -> dict[str, Any]:
    await require_device(device_id)
    async with lock_for(device_id):
        ok = await run_in_threadpool(launch_app, body.app, device_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown app '{body.app}'")
    return {"ok": True, "app": body.app}


@router.post("/devices/{device_id}/action")
async def do_action(device_id: str, body: ActionBody) -> dict[str, Any]:
    await require_device(device_id)
    w, h = await run_in_threadpool(get_screen_size, device_id)
    handler = ActionHandler(device_id=device_id)
    payload = {"_metadata": "do", "action": body.action, **body.params}
    async with lock_for(device_id):
        result = await run_in_threadpool(handler.execute, payload, w, h)
    return {"ok": result.success, "should_finish": result.should_finish, "message": result.message}
