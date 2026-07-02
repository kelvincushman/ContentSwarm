"""Device registry + accounts: labels, per-phone model, and social accounts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from phone_server.appstore import STORE
from phone_server.deps import adb, require_api_key
from phone_server.models import Account
from phone_server.registry import REGISTRY
from phone_server.schemas import AccountBody, DeviceConfigPatch

router = APIRouter(dependencies=[Depends(require_api_key)], prefix="/registry")


@router.get("/devices")
async def devices_merged() -> dict[str, Any]:
    """Live connected devices merged with their saved config + accounts."""
    live = await run_in_threadpool(adb.list_devices)
    live_map = {d.device_id: d for d in live}
    ids = set(live_map) | set(REGISTRY.devices)

    out = []
    for did in sorted(ids):
        d = live_map.get(did)
        cfg = REGISTRY.get_device(did)
        eff = REGISTRY.effective_model(did)
        out.append(
            {
                "device_id": did,
                "connected": bool(d and d.status == "device"),
                "status": d.status if d else "offline",
                "model": d.model if d else None,
                "label": cfg.label,
                "agent_model": {"base_url": eff["base_url"], "model_name": eff["model_name"]},
                "accounts": [a.model_dump() for a in cfg.accounts.values()],
                "notes": cfg.notes,
            }
        )
    return {"count": len(out), "devices": out}


@router.get("/devices/{device_id}")
async def get_device(device_id: str) -> dict[str, Any]:
    return REGISTRY.get_device(device_id).model_dump()


@router.put("/devices/{device_id}")
async def update_device(device_id: str, patch: DeviceConfigPatch) -> dict[str, Any]:
    dc = REGISTRY.upsert_device(device_id, patch.model_dump(exclude_none=True))
    return {"ok": True, "device": dc.model_dump()}


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str) -> dict[str, Any]:
    ok = REGISTRY.delete_device(device_id)
    return {"ok": ok}


@router.post("/devices/{device_id}/accounts")
async def add_account(device_id: str, body: AccountBody) -> dict[str, Any]:
    acc = REGISTRY.add_account(device_id, Account(**body.model_dump(exclude_none=True)))
    return {"ok": True, "account": acc.model_dump()}


@router.delete("/devices/{device_id}/accounts/{account_id}")
async def delete_account(device_id: str, account_id: str) -> dict[str, Any]:
    ok = REGISTRY.delete_account(device_id, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"ok": True}


@router.get("/accounts")
async def all_accounts() -> dict[str, Any]:
    """Every account across all phones, enriched with the app's available flows."""
    accounts = REGISTRY.all_accounts()
    for a in accounts:
        if a.get("app"):
            profile = STORE.load(a["app"])
            a["flows"] = sorted(profile.flows) if profile else []
    return {"count": len(accounts), "accounts": accounts}
