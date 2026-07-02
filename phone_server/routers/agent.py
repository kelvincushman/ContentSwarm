"""High-level VLM-driven agent endpoints (natural-language tasks)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.config import get_system_prompt
from phone_agent.model import ModelConfig

from phone_server.deps import ensure_unlocked, lock_for, require_api_key, require_device, settings
from phone_server.registry import REGISTRY
from phone_server.schemas import RunBody

router = APIRouter(dependencies=[Depends(require_api_key)])

# In-memory async job registry (cleared on restart).
JOBS: dict[str, dict[str, Any]] = {}


def build_agent(device_id: str, body: RunBody) -> PhoneAgent:
    lang = body.lang or settings.default_lang
    # Resolve the model for this phone: request override > per-device > default > env.
    resolved = REGISTRY.effective_model(device_id)
    model_config = ModelConfig(
        base_url=body.model_base_url or resolved["base_url"],
        api_key=resolved["api_key"],
        model_name=body.model_name or resolved["model_name"],
    )
    agent_config = AgentConfig(
        max_steps=body.max_steps or settings.default_max_steps,
        device_id=device_id,
        lang=lang,
        system_prompt=get_system_prompt(lang),
        verbose=False,
    )
    return PhoneAgent(model_config=model_config, agent_config=agent_config)


def serialize_step(step) -> dict[str, Any]:
    return {
        "success": step.success,
        "finished": step.finished,
        "thinking": step.thinking,
        "action": step.action,
        "message": step.message,
    }


def run_collect(agent: PhoneAgent, task: str, max_steps: int) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    result = agent.step(task)
    steps.append(serialize_step(result))
    while not result.finished and agent.step_count < max_steps:
        result = agent.step()
        steps.append(serialize_step(result))
    return {
        "finished": result.finished,
        "final_message": result.message,
        "steps": steps,
        "step_count": agent.step_count,
    }


@router.post("/devices/{device_id}/run")
async def run_task(device_id: str, body: RunBody) -> dict[str, Any]:
    await require_device(device_id)
    agent = build_agent(device_id, body)
    max_steps = body.max_steps or settings.default_max_steps
    async with lock_for(device_id):
        await run_in_threadpool(ensure_unlocked, device_id)
        out = await run_in_threadpool(run_collect, agent, body.task, max_steps)
    return {"ok": True, "device_id": device_id, "task": body.task, **out}


@router.post("/devices/{device_id}/run/async")
async def run_task_async(device_id: str, body: RunBody) -> dict[str, Any]:
    await require_device(device_id)
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"job_id": job_id, "device_id": device_id, "task": body.task, "status": "running", "result": None}

    async def _worker() -> None:
        agent = build_agent(device_id, body)
        max_steps = body.max_steps or settings.default_max_steps
        try:
            async with lock_for(device_id):
                await run_in_threadpool(ensure_unlocked, device_id)
                out = await run_in_threadpool(run_collect, agent, body.task, max_steps)
            JOBS[job_id].update(status="done", result=out)
        except Exception as e:  # noqa: BLE001
            JOBS[job_id].update(status="error", result={"error": str(e)})

    asyncio.create_task(_worker())
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
