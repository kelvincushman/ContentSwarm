"""FastAPI phone control + app-onboarding server.

Assembles the routers into one app. Layers:
  * devices  — raw ADB primitives, screenshot, UI hierarchy, packages
  * agent    — high-level VLM-driven natural-language tasks (/run)
  * apps     — control onboarded apps (open, detect screen, tap element, run flow)
  * onboard  — training sessions that produce saved app profiles
  * streaming— WebSocket live screen + streaming agent run

Run:
    python run_phone_server.py
or:
    uvicorn phone_server.server:app --host 0.0.0.0 --port 8770

Auth: REST -> header X-API-Key; WebSocket -> ?api_key= (enforced when
PHONE_API_KEY is set).
"""

from __future__ import annotations

from typing import Any

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from phone_server.config import get_settings
from phone_server.routers import agent, apps, config, devices, integration, onboard, registry, streaming

settings = get_settings()
_UI_DIST = os.path.join(os.path.dirname(__file__), "ui", "dist")

app = FastAPI(
    title="ContentSwarm Phone Control & App Onboarding Server",
    version="0.3.0",
    description="LAN REST + WebSocket control of Android phones, with an app "
    "onboarding/training system that lets agents learn and reuse apps.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "phone-control",
        "version": "0.3.0",
        "auth": bool(settings.api_key),
        "profiles_dir": settings.profiles_dir,
    }


app.include_router(devices.router, tags=["devices"])
app.include_router(agent.router, tags=["agent"])
app.include_router(apps.router, tags=["apps"])
app.include_router(onboard.router, tags=["onboard"])
app.include_router(streaming.router, tags=["streaming"])
app.include_router(config.router, tags=["config"])
app.include_router(registry.router, tags=["registry"])
app.include_router(integration.router, tags=["integration"])

# Serve the built React console at / (if built). API routes are matched first.
if os.path.isdir(_UI_DIST):
    app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")
