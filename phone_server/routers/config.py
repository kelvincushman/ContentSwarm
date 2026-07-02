"""Server configuration + model discovery."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from phone_server.config import get_settings
from phone_server.deps import require_api_key
from phone_server.registry import REGISTRY

router = APIRouter(dependencies=[Depends(require_api_key)], prefix="/config")
settings = get_settings()


@router.get("")
async def get_config() -> dict[str, Any]:
    return {
        "editable": REGISTRY.config.model_dump(),
        "static": {
            "host": settings.host,
            "port": settings.port,
            "auth_required": bool(settings.api_key),
            "profiles_dir": settings.profiles_dir,
            "registry_path": REGISTRY.path,
        },
    }


@router.put("")
async def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    cfg = REGISTRY.update_config(patch)
    return {"ok": True, "editable": cfg.model_dump()}


def _fetch_models(base_url: str, api_key: str) -> list[str]:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
    except Exception:
        return []


def _discover() -> list[dict[str, Any]]:
    out = []
    for host in REGISTRY.config.model_hosts:
        models = _fetch_models(host.base_url, host.api_key)
        out.append(
            {
                "name": host.name,
                "base_url": host.base_url,
                "kind": host.kind,
                "reachable": bool(models),
                "models": models,
            }
        )
    return out


@router.get("/models")
async def discover_models() -> dict[str, Any]:
    """Query every configured model host and list available models."""
    hosts = await run_in_threadpool(_discover)
    return {"hosts": hosts}
