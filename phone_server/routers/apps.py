"""Control of onboarded apps: open, detect screen, tap named elements, run flows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from phone_agent.adb import tap

from phone_server import adb_ext
from phone_server.appstore import STORE
from phone_server.deps import ensure_unlocked, lock_for, require_api_key, require_device
from phone_server.flows import FlowRunner
from phone_server.schemas import ElementTapBody, FindBody, FlowRunBody

router = APIRouter(dependencies=[Depends(require_api_key)])


def _load(app: str):
    profile = STORE.load(app)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"No onboarded app '{app}'. See GET /apps.")
    return profile


@router.get("/apps")
async def list_apps() -> dict[str, Any]:
    apps = STORE.list_apps()
    summaries = []
    for a in apps:
        p = STORE.load(a)
        if p:
            summaries.append(p.summary())
    return {"count": len(apps), "apps": summaries}


@router.get("/apps/{app}")
async def get_app(app: str) -> dict[str, Any]:
    return _load(app).model_dump()


@router.delete("/apps/{app}")
async def delete_app(app: str) -> dict[str, Any]:
    if not STORE.delete(app):
        raise HTTPException(status_code=404, detail=f"No onboarded app '{app}'")
    return {"ok": True, "deleted": app}


@router.post("/apps/{app}/devices/{device_id}/open")
async def open_app(app: str, device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    profile = _load(app)
    runner = FlowRunner(profile, device_id)
    async with lock_for(device_id):
        await run_in_threadpool(ensure_unlocked, device_id)
        detail = await run_in_threadpool(runner._exec_step, _open_step(), {})
    return {"ok": True, "detail": detail}


def _open_step():
    from phone_server.models import FlowStep

    return FlowStep(action="open_app")


@router.get("/apps/{app}/devices/{device_id}/screen")
async def detect_screen(app: str, device_id: str) -> dict[str, Any]:
    await require_device(device_id)
    profile = _load(app)
    runner = FlowRunner(profile, device_id)
    async with lock_for(device_id):
        screen = await run_in_threadpool(runner.current_screen)
    return {"screen": screen, "known_screens": sorted(profile.screens)}


@router.post("/apps/{app}/devices/{device_id}/find")
async def find_element(app: str, device_id: str, body: FindBody) -> dict[str, Any]:
    """Resolve a selector against the live hierarchy without tapping."""
    await require_device(device_id)
    async with lock_for(device_id):
        nodes = await run_in_threadpool(adb_ext.get_ui_elements, device_id)
    node = adb_ext.resolve_selector(nodes, body.selector.model_dump(exclude_none=True))
    if not node:
        return {"found": False}
    return {"found": True, "node": node}


@router.post("/apps/{app}/devices/{device_id}/element/tap")
async def tap_element(app: str, device_id: str, body: ElementTapBody) -> dict[str, Any]:
    await require_device(device_id)
    profile = _load(app)
    runner = FlowRunner(profile, device_id)

    element = None
    if body.element:
        element = profile.elements.get(body.element)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Unknown element '{body.element}' in '{app}'")
    if element is None and body.selector is None:
        raise HTTPException(status_code=400, detail="Provide 'element' or 'selector'")

    async with lock_for(device_id):
        xy = await run_in_threadpool(runner.resolve_element, element, body.selector)
        if xy is None:
            raise HTTPException(status_code=404, detail="Target not found on current screen")
        await run_in_threadpool(tap, xy[0], xy[1], device_id)
    return {"ok": True, "x": xy[0], "y": xy[1]}


@router.post("/apps/{app}/devices/{device_id}/flows/{flow}/run")
async def run_flow(app: str, device_id: str, flow: str, body: FlowRunBody) -> dict[str, Any]:
    await require_device(device_id)
    profile = _load(app)
    flow_obj = profile.flows.get(flow)
    if flow_obj is None:
        raise HTTPException(status_code=404, detail=f"Unknown flow '{flow}' in '{app}'")

    missing = [p for p in flow_obj.params if p not in body.params]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing params: {missing}")

    runner = FlowRunner(profile, device_id)
    async with lock_for(device_id):
        await run_in_threadpool(ensure_unlocked, device_id)
        result = await run_in_threadpool(runner.run, flow_obj, body.params)
    return {
        "ok": result.ok,
        "error": result.error,
        "steps": [{"index": s.index, "action": s.action, "ok": s.ok, "detail": s.detail} for s in result.steps],
    }
