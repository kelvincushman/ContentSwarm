"""FastAPI phone control server.

Run:
    python run_phone_server.py
or:
    uvicorn phone_server.server:app --host 0.0.0.0 --port 8770

Auth:
    REST      -> header  X-API-Key: <key>
    WebSocket -> query    ?api_key=<key>
    (only enforced when PHONE_API_KEY is set)
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from phone_agent.actions.handler import ActionHandler
from phone_agent.adb import (
    ADBConnection,
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
from phone_agent.adb.input import clear_text, detect_and_set_adb_keyboard, restore_keyboard, type_text
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.config import get_system_prompt
from phone_agent.model import ModelConfig

from phone_server.config import get_settings

settings = get_settings()
app = FastAPI(
    title="ContentSwarm Phone Control Server",
    version="0.1.0",
    description="LAN-accessible REST + WebSocket control of connected Android phones.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_adb = ADBConnection()

# One lock per device so concurrent requests don't interleave ADB actions on the
# same phone. Different phones run fully in parallel.
_device_locks: dict[str, asyncio.Lock] = {}

# Cached physical screen size per device (used for normalized coordinates).
_screen_sizes: dict[str, tuple[int, int]] = {}

# In-memory registry for async agent jobs.
_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """REST auth dependency. No-op when PHONE_API_KEY is unset."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def check_ws_key(api_key: str | None) -> bool:
    """WebSocket auth check (key passed as a query param)."""
    if not settings.api_key:
        return True
    return api_key == settings.api_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lock_for(device_id: str) -> asyncio.Lock:
    lock = _device_locks.get(device_id)
    if lock is None:
        lock = asyncio.Lock()
        _device_locks[device_id] = lock
    return lock


def _connected_ids() -> set[str]:
    return {d.device_id for d in _adb.list_devices() if d.status == "device"}


async def _require_device(device_id: str) -> None:
    ids = await run_in_threadpool(_connected_ids)
    if device_id not in ids:
        raise HTTPException(
            status_code=404,
            detail=f"Device '{device_id}' is not connected (state != 'device'). Connected: {sorted(ids)}",
        )


def _get_screen_size(device_id: str) -> tuple[int, int]:
    """Return (width, height) of the *screenshot* framebuffer, cached.

    We deliberately use the screenshot dimensions (not `wm size`) because the
    vision model and ActionHandler express coordinates relative to the captured
    image. On some devices `wm size` differs from the framebuffer (e.g. the
    Note 10 reports 1080x2280 but screencap is 1080x2400), which would skew
    normalized taps. Matching the screenshot keeps 0-1000 coords exact.
    """
    if device_id in _screen_sizes:
        return _screen_sizes[device_id]
    shot = get_screenshot(device_id)
    size = (shot.width, shot.height)
    _screen_sizes[device_id] = size
    return size


def _resolve_xy(device_id: str, x: int, y: int, normalized: bool) -> tuple[int, int]:
    """Convert coordinates to absolute pixels. If normalized, x/y are 0-1000."""
    if not normalized:
        return int(x), int(y)
    w, h = _get_screen_size(device_id)
    return int(x / 1000 * w), int(y / 1000 * h)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ConnectBody(BaseModel):
    address: str = Field(..., description="host or host:port, e.g. 192.168.1.50:5555")


class TapBody(BaseModel):
    x: int
    y: int
    normalized: bool = Field(False, description="If true, x/y are 0-1000 relative coords")


class SwipeBody(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int | None = None
    normalized: bool = False


class TypeBody(BaseModel):
    text: str
    clear: bool = Field(True, description="Clear the field before typing")


class LaunchBody(BaseModel):
    app: str = Field(..., description="App name known to phone_agent (see config/apps.py)")


class ActionBody(BaseModel):
    """Generic action routed through the full ActionHandler vocabulary."""

    action: str = Field(..., description="Launch|Tap|Type|Swipe|Back|Home|Double Tap|Long Press|Wait|...")
    params: dict[str, Any] = Field(default_factory=dict)


class RunBody(BaseModel):
    task: str
    max_steps: int | None = None
    lang: str | None = None
    model_base_url: str | None = None
    model_name: str | None = None


# ---------------------------------------------------------------------------
# Meta / device management
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "phone-control", "version": "0.1.0", "auth": bool(settings.api_key)}


@app.get("/devices", dependencies=[Depends(require_api_key)])
async def list_devices_endpoint() -> dict[str, Any]:
    devices = await run_in_threadpool(_adb.list_devices)
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


@app.post("/devices/connect", dependencies=[Depends(require_api_key)])
async def connect_device(body: ConnectBody) -> dict[str, Any]:
    ok, msg = await run_in_threadpool(_adb.connect, body.address)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


@app.post("/devices/disconnect", dependencies=[Depends(require_api_key)])
async def disconnect_device(body: ConnectBody) -> dict[str, Any]:
    ok, msg = await run_in_threadpool(_adb.disconnect, body.address)
    return {"ok": ok, "message": msg}


@app.post("/devices/{device_id}/tcpip", dependencies=[Depends(require_api_key)])
async def enable_tcpip(device_id: str, port: int = 5555) -> dict[str, Any]:
    """Flip a USB-attached device into wireless mode so it can be reached over WiFi."""
    await _require_device(device_id)
    ok, msg = await run_in_threadpool(_adb.enable_tcpip, port, device_id)
    ip = await run_in_threadpool(_adb.get_device_ip, device_id)
    return {"ok": ok, "message": msg, "device_ip": ip, "wifi_address": f"{ip}:{port}" if ip else None}


@app.get("/devices/{device_id}/screen_size", dependencies=[Depends(require_api_key)])
async def screen_size(device_id: str) -> dict[str, Any]:
    await _require_device(device_id)
    w, h = await run_in_threadpool(_get_screen_size, device_id)
    return {"width": w, "height": h}


@app.get("/devices/{device_id}/current_app", dependencies=[Depends(require_api_key)])
async def current_app(device_id: str) -> dict[str, Any]:
    await _require_device(device_id)
    name = await run_in_threadpool(get_current_app, device_id)
    return {"current_app": name}


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------


@app.get("/devices/{device_id}/screenshot", dependencies=[Depends(require_api_key)])
async def screenshot(device_id: str, format: str = Query("png", pattern="^(png|base64)$")):
    await _require_device(device_id)
    async with _lock_for(device_id):
        shot = await run_in_threadpool(get_screenshot, device_id)
    if format == "base64":
        return {
            "width": shot.width,
            "height": shot.height,
            "is_sensitive": shot.is_sensitive,
            "image_base64": shot.base64_data,
        }
    png_bytes = base64.b64decode(shot.base64_data)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Screen-Width": str(shot.width),
            "X-Screen-Height": str(shot.height),
            "X-Is-Sensitive": str(shot.is_sensitive).lower(),
        },
    )


# ---------------------------------------------------------------------------
# Raw input primitives
# ---------------------------------------------------------------------------


@app.post("/devices/{device_id}/tap", dependencies=[Depends(require_api_key)])
async def do_tap(device_id: str, body: TapBody) -> dict[str, Any]:
    await _require_device(device_id)
    x, y = _resolve_xy(device_id, body.x, body.y, body.normalized)
    async with _lock_for(device_id):
        await run_in_threadpool(tap, x, y, device_id)
    return {"ok": True, "x": x, "y": y}


@app.post("/devices/{device_id}/double_tap", dependencies=[Depends(require_api_key)])
async def do_double_tap(device_id: str, body: TapBody) -> dict[str, Any]:
    await _require_device(device_id)
    x, y = _resolve_xy(device_id, body.x, body.y, body.normalized)
    async with _lock_for(device_id):
        await run_in_threadpool(double_tap, x, y, device_id)
    return {"ok": True, "x": x, "y": y}


@app.post("/devices/{device_id}/long_press", dependencies=[Depends(require_api_key)])
async def do_long_press(device_id: str, body: TapBody) -> dict[str, Any]:
    await _require_device(device_id)
    x, y = _resolve_xy(device_id, body.x, body.y, body.normalized)
    async with _lock_for(device_id):
        await run_in_threadpool(long_press, x, y, device_id=device_id)
    return {"ok": True, "x": x, "y": y}


@app.post("/devices/{device_id}/swipe", dependencies=[Depends(require_api_key)])
async def do_swipe(device_id: str, body: SwipeBody) -> dict[str, Any]:
    await _require_device(device_id)
    sx, sy = _resolve_xy(device_id, body.start_x, body.start_y, body.normalized)
    ex, ey = _resolve_xy(device_id, body.end_x, body.end_y, body.normalized)
    async with _lock_for(device_id):
        await run_in_threadpool(swipe, sx, sy, ex, ey, body.duration_ms, device_id)
    return {"ok": True, "start": [sx, sy], "end": [ex, ey]}


@app.post("/devices/{device_id}/type", dependencies=[Depends(require_api_key)])
async def do_type(device_id: str, body: TypeBody) -> dict[str, Any]:
    """Type text via the ADB Keyboard IME (must be installed on the device)."""
    await _require_device(device_id)

    def _type() -> None:
        original = detect_and_set_adb_keyboard(device_id)
        time.sleep(1.0)
        if body.clear:
            clear_text(device_id)
            time.sleep(0.5)
        type_text(body.text, device_id)
        time.sleep(0.5)
        restore_keyboard(original, device_id)

    async with _lock_for(device_id):
        await run_in_threadpool(_type)
    return {"ok": True, "typed": len(body.text)}


@app.post("/devices/{device_id}/back", dependencies=[Depends(require_api_key)])
async def do_back(device_id: str) -> dict[str, Any]:
    await _require_device(device_id)
    async with _lock_for(device_id):
        await run_in_threadpool(back, device_id)
    return {"ok": True}


@app.post("/devices/{device_id}/home", dependencies=[Depends(require_api_key)])
async def do_home(device_id: str) -> dict[str, Any]:
    await _require_device(device_id)
    async with _lock_for(device_id):
        await run_in_threadpool(home, device_id)
    return {"ok": True}


@app.post("/devices/{device_id}/launch", dependencies=[Depends(require_api_key)])
async def do_launch(device_id: str, body: LaunchBody) -> dict[str, Any]:
    await _require_device(device_id)
    async with _lock_for(device_id):
        ok = await run_in_threadpool(launch_app, body.app, device_id)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Unknown app '{body.app}' (not in APP_PACKAGES)")
    return {"ok": True, "app": body.app}


@app.post("/devices/{device_id}/action", dependencies=[Depends(require_api_key)])
async def do_action(device_id: str, body: ActionBody) -> dict[str, Any]:
    """Escape hatch: route any action through the full ActionHandler vocabulary.

    Uses relative 0-1000 coordinates in `element`/`start`/`end`, matching the
    convention the vision model uses (see actions/handler.py).
    """
    await _require_device(device_id)
    w, h = await run_in_threadpool(_get_screen_size, device_id)
    handler = ActionHandler(device_id=device_id)
    payload = {"_metadata": "do", "action": body.action, **body.params}

    async with _lock_for(device_id):
        result = await run_in_threadpool(handler.execute, payload, w, h)
    return {
        "ok": result.success,
        "should_finish": result.should_finish,
        "message": result.message,
    }


# ---------------------------------------------------------------------------
# High-level agentic run (VLM-driven)
# ---------------------------------------------------------------------------


def _build_agent(device_id: str, body: RunBody) -> PhoneAgent:
    lang = body.lang or settings.default_lang
    model_config = ModelConfig(
        base_url=body.model_base_url or settings.vlm_base_url,
        api_key=settings.vlm_api_key,
        model_name=body.model_name or settings.vlm_model,
    )
    agent_config = AgentConfig(
        max_steps=body.max_steps or settings.default_max_steps,
        device_id=device_id,
        lang=lang,
        system_prompt=get_system_prompt(lang),
        verbose=False,
    )
    return PhoneAgent(model_config=model_config, agent_config=agent_config)


def _serialize_step(step) -> dict[str, Any]:
    return {
        "success": step.success,
        "finished": step.finished,
        "thinking": step.thinking,
        "action": step.action,
        "message": step.message,
    }


def _run_task_collect(agent: PhoneAgent, task: str, max_steps: int) -> dict[str, Any]:
    """Drive the agent step-by-step and collect the full transcript (blocking)."""
    steps: list[dict[str, Any]] = []
    result = agent.step(task)
    steps.append(_serialize_step(result))
    while not result.finished and agent.step_count < max_steps:
        result = agent.step()
        steps.append(_serialize_step(result))
    return {
        "finished": result.finished,
        "final_message": result.message,
        "steps": steps,
        "step_count": agent.step_count,
    }


@app.post("/devices/{device_id}/run", dependencies=[Depends(require_api_key)])
async def run_task(device_id: str, body: RunBody) -> dict[str, Any]:
    """Synchronously run a natural-language task on a phone via the vision model.

    Returns the full step transcript. Long tasks block until done — for those,
    prefer POST /devices/{id}/run/async (poll) or the WS /ws/{id}/run stream.
    """
    await _require_device(device_id)
    agent = _build_agent(device_id, body)
    max_steps = body.max_steps or settings.default_max_steps
    async with _lock_for(device_id):
        out = await run_in_threadpool(_run_task_collect, agent, body.task, max_steps)
    return {"ok": True, "device_id": device_id, "task": body.task, **out}


@app.post("/devices/{device_id}/run/async", dependencies=[Depends(require_api_key)])
async def run_task_async(device_id: str, body: RunBody) -> dict[str, Any]:
    """Kick off a task in the background and return a job_id to poll via GET /jobs/{id}."""
    await _require_device(device_id)
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"job_id": job_id, "device_id": device_id, "task": body.task, "status": "running", "result": None}

    async def _worker() -> None:
        agent = _build_agent(device_id, body)
        max_steps = body.max_steps or settings.default_max_steps
        try:
            async with _lock_for(device_id):
                out = await run_in_threadpool(_run_task_collect, agent, body.task, max_steps)
            _jobs[job_id].update(status="done", result=out)
        except Exception as e:  # noqa: BLE001 - surface any failure to the poller
            _jobs[job_id].update(status="error", result={"error": str(e)})

    asyncio.create_task(_worker())
    return {"job_id": job_id, "status": "running"}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_api_key)])
async def get_job(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


# ---------------------------------------------------------------------------
# WebSocket: live screen stream
# ---------------------------------------------------------------------------


@app.websocket("/ws/{device_id}/stream")
async def ws_stream(websocket: WebSocket, device_id: str, api_key: str | None = None, fps: float | None = None):
    """Push a live stream of base64 PNG frames: {type:'frame', width, height, data, ts}."""
    if not check_ws_key(api_key):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    if device_id not in await run_in_threadpool(_connected_ids):
        await websocket.send_json({"type": "error", "error": f"device '{device_id}' not connected"})
        await websocket.close()
        return

    interval = 1.0 / (fps or settings.default_stream_fps)
    try:
        while True:
            async with _lock_for(device_id):
                shot = await run_in_threadpool(get_screenshot, device_id)
            await websocket.send_json(
                {
                    "type": "frame",
                    "width": shot.width,
                    "height": shot.height,
                    "is_sensitive": shot.is_sensitive,
                    "data": shot.base64_data,
                    "ts": time.time(),
                }
            )
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        finally:
            await websocket.close()


# ---------------------------------------------------------------------------
# WebSocket: agentic run with step-by-step streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws/{device_id}/run")
async def ws_run(websocket: WebSocket, device_id: str, api_key: str | None = None):
    """Run a task and stream each step. Client sends one JSON: {task, max_steps?, lang?}.

    Server emits: {type:'step', index, step} per step, then {type:'done', final_message}.
    """
    if not check_ws_key(api_key):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    if device_id not in await run_in_threadpool(_connected_ids):
        await websocket.send_json({"type": "error", "error": f"device '{device_id}' not connected"})
        await websocket.close()
        return

    try:
        init = await websocket.receive_json()
    except Exception:
        await websocket.close()
        return

    body = RunBody(**init)
    agent = _build_agent(device_id, body)
    max_steps = body.max_steps or settings.default_max_steps

    try:
        async with _lock_for(device_id):
            result = await run_in_threadpool(agent.step, body.task)
            await websocket.send_json({"type": "step", "index": agent.step_count, "step": _serialize_step(result)})
            while not result.finished and agent.step_count < max_steps:
                result = await run_in_threadpool(agent.step)
                await websocket.send_json(
                    {"type": "step", "index": agent.step_count, "step": _serialize_step(result)}
                )
        await websocket.send_json(
            {"type": "done", "finished": result.finished, "final_message": result.message, "step_count": agent.step_count}
        )
        await websocket.close()
    except WebSocketDisconnect:
        return
    except Exception as e:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        finally:
            await websocket.close()
