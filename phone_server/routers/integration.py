"""Agent hookup-kit endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from phone_server import integration
from phone_server.deps import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)], prefix="/integration")


@router.get("")
async def get_kit(request: Request, redact: bool = False) -> dict[str, Any]:
    """Full hookup kit (all formats) generated from live server state."""
    return integration.build_kit(str(request.base_url), redact=redact)


@router.get("/{fmt}", response_class=PlainTextResponse)
async def get_kit_part(fmt: str, request: Request, redact: bool = False) -> str:
    """A single format as copyable text: system_prompt | tools | tools_anthropic | mcp | rest_cheatsheet."""
    kit = integration.build_kit(str(request.base_url), redact=redact)
    if fmt not in kit:
        raise HTTPException(status_code=404, detail=f"Unknown format '{fmt}'. Try: system_prompt, tools, mcp, rest_cheatsheet")
    value = kit[fmt]
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False)
