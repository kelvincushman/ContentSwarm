"""Onboarding / training endpoints — teach the server a new app."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from phone_agent.adb import get_screenshot

from phone_server.appstore import STORE
from phone_server.deps import lock_for, require_api_key, require_device
from phone_server.onboarding import MANAGER
from phone_server.schemas import (
    AddElementBody,
    AddFlowBody,
    AddScreenBody,
    RecordStepBody,
    StartOnboardBody,
    SuggestBody,
)

router = APIRouter(dependencies=[Depends(require_api_key)], prefix="/onboard")


def _session_or_404(session_id: str):
    try:
        return MANAGER.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session '{session_id}'")


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    return {"sessions": MANAGER.list_sessions()}


@router.post("/start")
async def start(body: StartOnboardBody) -> dict[str, Any]:
    await require_device(body.device_id)
    sess = MANAGER.start(
        device_id=body.device_id,
        app=body.app,
        package=body.package,
        display_name=body.display_name,
        launch_activity=body.launch_activity,
        load_existing=body.load_existing,
    )
    return {
        "session_id": sess.id,
        "app": sess.profile.app,
        "package": sess.profile.package,
        "launch_activity": sess.profile.launch_activity,
        "existing": STORE.exists(sess.profile.app),
    }


@router.post("/{session_id}/capture")
async def capture(session_id: str) -> dict[str, Any]:
    sess = _session_or_404(session_id)
    await require_device(sess.device_id)
    async with lock_for(sess.device_id):
        data = await run_in_threadpool(MANAGER.capture, session_id)
    return data


@router.post("/{session_id}/suggest")
async def suggest(session_id: str, body: SuggestBody) -> dict[str, Any]:
    sess = _session_or_404(session_id)
    async with lock_for(sess.device_id):
        return await run_in_threadpool(MANAGER.suggest_at, session_id, body.x, body.y, body.normalized)


@router.post("/{session_id}/element")
async def add_element(session_id: str, body: AddElementBody) -> dict[str, Any]:
    sess = _session_or_404(session_id)
    from_point = None
    if body.from_x is not None and body.from_y is not None:
        from_point = (body.from_x, body.from_y, body.normalized)
    selector = body.selector.model_dump(exclude_none=True) if body.selector else None
    async with lock_for(sess.device_id):
        el = await run_in_threadpool(
            MANAGER.add_element, session_id, body.name, selector, from_point, body.screen, body.description
        )
    return {"ok": True, "element": el.model_dump()}


@router.post("/{session_id}/screen")
async def add_screen(session_id: str, body: AddScreenBody) -> dict[str, Any]:
    sess = _session_or_404(session_id)
    await require_device(sess.device_id)
    shot_name = None
    if body.save_screenshot:
        async with lock_for(sess.device_id):
            shot = await run_in_threadpool(get_screenshot, sess.device_id)
        shot_name = STORE.save_screenshot(sess.profile.app, body.name, base64.b64decode(shot.base64_data))
    screen = await run_in_threadpool(
        MANAGER.add_screen,
        session_id,
        body.name,
        body.signature_resource_ids,
        body.signature_text,
        body.description,
        shot_name,
    )
    return {"ok": True, "screen": screen.model_dump()}


@router.post("/{session_id}/flow")
async def add_flow(session_id: str, body: AddFlowBody) -> dict[str, Any]:
    _session_or_404(session_id)
    flow = MANAGER.add_flow(session_id, body.flow)
    return {"ok": True, "flow": flow.model_dump()}


@router.post("/{session_id}/record")
async def record_step(session_id: str, body: RecordStepBody) -> dict[str, Any]:
    _session_or_404(session_id)
    flow = MANAGER.record_step(session_id, body.flow, body.step, body.description)
    return {"ok": True, "flow": body.flow, "steps": len(flow.steps)}


@router.get("/{session_id}/draft")
async def draft(session_id: str) -> dict[str, Any]:
    sess = _session_or_404(session_id)
    return sess.profile.model_dump()


@router.post("/{session_id}/save")
async def save(session_id: str) -> dict[str, Any]:
    _session_or_404(session_id)
    out = MANAGER.save(session_id)
    return {"ok": True, **out}


@router.delete("/{session_id}")
async def discard(session_id: str) -> dict[str, Any]:
    _session_or_404(session_id)
    MANAGER.discard(session_id)
    return {"ok": True, "discarded": session_id}
