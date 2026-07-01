"""WebSocket endpoints: live screen stream and streaming agent run."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from phone_agent.adb import get_screenshot

from phone_server.deps import check_ws_key, connected_ids, lock_for, settings
from phone_server.routers.agent import build_agent, serialize_step
from phone_server.schemas import RunBody

router = APIRouter()


@router.websocket("/ws/{device_id}/stream")
async def ws_stream(websocket: WebSocket, device_id: str, api_key: str | None = None, fps: float | None = None):
    if not check_ws_key(api_key):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    if device_id not in await run_in_threadpool(connected_ids):
        await websocket.send_json({"type": "error", "error": f"device '{device_id}' not connected"})
        await websocket.close()
        return

    interval = 1.0 / (fps or settings.default_stream_fps)
    try:
        while True:
            async with lock_for(device_id):
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


@router.websocket("/ws/{device_id}/run")
async def ws_run(websocket: WebSocket, device_id: str, api_key: str | None = None):
    if not check_ws_key(api_key):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    if device_id not in await run_in_threadpool(connected_ids):
        await websocket.send_json({"type": "error", "error": f"device '{device_id}' not connected"})
        await websocket.close()
        return

    try:
        init = await websocket.receive_json()
    except Exception:
        await websocket.close()
        return

    body = RunBody(**init)
    agent = build_agent(device_id, body)
    max_steps = body.max_steps or settings.default_max_steps
    try:
        async with lock_for(device_id):
            result = await run_in_threadpool(agent.step, body.task)
            await websocket.send_json({"type": "step", "index": agent.step_count, "step": serialize_step(result)})
            while not result.finished and agent.step_count < max_steps:
                result = await run_in_threadpool(agent.step)
                await websocket.send_json({"type": "step", "index": agent.step_count, "step": serialize_step(result)})
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
