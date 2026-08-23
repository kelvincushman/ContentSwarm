"""Flow learning and deterministic replay.

A *flow* is a recorded sequence of device actions. The vision-language model
is used ONCE to learn how to drive an app (the teacher); the recorded flow is
then replayed deterministically through the existing ActionHandler - raw
presses at the exact recorded points, no LLM in the loop.

Coordinates are stored in the model's relative 0-1000 space, so a flow
recorded on one phone replays correctly on any screen size.
"""

import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from phone_agent import bridge
from phone_agent.actions.handler import ActionHandler
from phone_agent.adb import get_current_app, get_screenshot

DEFAULT_FLOWS_DIR = "flows"

# Actions that are pure device input and replay deterministically.
REPLAYABLE_ACTIONS = {
    "Launch", "Tap", "Double Tap", "Long Press", "Swipe",
    "Type", "Type_Name", "Back", "Home", "Wait",
}


@dataclass
class FlowStep:
    """One recorded action with its timing."""

    action: Dict[str, Any]
    delay_before: float = 1.0  # seconds waited before this step at record time
    app: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "delay_before": round(self.delay_before, 2), "app": self.app}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FlowStep":
        return FlowStep(action=d["action"], delay_before=d.get("delay_before", 1.0), app=d.get("app", ""))


@dataclass
class Flow:
    """A named, replayable sequence of device actions."""

    name: str
    task: str
    app: str = ""
    created_at: str = ""
    steps: List[FlowStep] = field(default_factory=list)
    manual_steps: int = 0  # Take_over etc. seen while learning (not replayable)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "task": self.task,
            "app": self.app,
            "created_at": self.created_at,
            "version": self.version,
            "manual_steps": self.manual_steps,
            "steps": [s.to_dict() for s in self.steps],
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Flow":
        return Flow(
            name=d["name"],
            task=d.get("task", ""),
            app=d.get("app", ""),
            created_at=d.get("created_at", ""),
            version=d.get("version", 1),
            manual_steps=d.get("manual_steps", 0),
            steps=[FlowStep.from_dict(s) for s in d.get("steps", [])],
        )


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", name).strip("-.")
    if not cleaned:
        raise ValueError(f"Invalid flow name: {name!r}")
    return cleaned


def flow_path(name: str, flows_dir: str = DEFAULT_FLOWS_DIR) -> Path:
    return Path(flows_dir) / f"{_safe_name(name)}.json"


def save_flow(flow: Flow, flows_dir: str = DEFAULT_FLOWS_DIR) -> Path:
    path = flow_path(flow.name, flows_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(flow.to_dict(), f, indent=2, ensure_ascii=False)
    return path


def load_flow(name: str, flows_dir: str = DEFAULT_FLOWS_DIR) -> Flow:
    path = flow_path(name, flows_dir)
    if not path.exists():
        raise FileNotFoundError(f"Flow not found: {name}")
    with open(path) as f:
        return Flow.from_dict(json.load(f))


def list_flows(flows_dir: str = DEFAULT_FLOWS_DIR) -> List[Dict[str, Any]]:
    """List saved flows with summary info."""
    result = []
    directory = Path(flows_dir)
    if not directory.exists():
        return result
    for path in sorted(directory.glob("*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
            result.append({
                "name": d.get("name", path.stem),
                "task": d.get("task", ""),
                "app": d.get("app", ""),
                "steps": len(d.get("steps", [])),
                "manual_steps": d.get("manual_steps", 0),
                "created_at": d.get("created_at", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


class FlowRecorder:
    """Records PhoneAgent events into a Flow while the model learns a task.

    Attach via PhoneAgent(event_callback=recorder.on_event). Only replayable
    device actions are kept; model-side actions (Take_over, Interact, Note,
    Call_API) are counted as manual steps.
    """

    TARGETED_ACTIONS = {"Tap", "Double Tap", "Long Press"}

    def __init__(self, name: str, task: str):
        self.flow = Flow(
            name=name,
            task=task,
            created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._last_time: Optional[float] = None
        self._current_app = ""
        self._device_id: Optional[str] = None

    def on_event(self, event: Dict[str, Any]) -> None:
        kind = event.get("event")
        if kind == "step_started":
            self._current_app = event.get("app", "") or self._current_app
            if not self.flow.app and self._current_app:
                self.flow.app = self._current_app
            # Dump the pre-action UI tree in the background: it completes while
            # the model is thinking, so enrichment adds no learning latency.
            # bridge.prefetch_ui holds the per-device lock for the dump's
            # duration, so it cannot interleave with other device operations.
            self._device_id = event.get("device_id")
            bridge.prefetch_ui(self._device_id)
            return
        if kind != "step_completed":
            return

        action = event.get("action") or {}
        if action.get("_metadata") != "do":
            return
        if not event.get("success", False):
            return  # do not record actions that failed on the device

        name = action.get("action")
        now = event.get("timestamp", time.time())
        if name not in REPLAYABLE_ACTIONS:
            self.flow.manual_steps += 1
            self._last_time = now
            return

        delay = 1.0 if self._last_time is None else max(0.5, min(now - self._last_time, 10.0))
        self._last_time = now

        clean = {k: v for k, v in action.items() if k != "message"}
        if name in self.TARGETED_ACTIONS:
            target = self._element_target(clean.get("element"))
            if target:
                clean.update(target)
        self.flow.steps.append(FlowStep(action=clean, delay_before=delay, app=self._current_app))

    def _element_target(self, element: Optional[List[int]]) -> Optional[Dict[str, str]]:
        """Semantic identity (text/id/desc) of the element under a recorded tap.

        Replays try this target first and only fall back to the recorded
        coordinates, so flows survive layout shifts, A/B moves, and different
        screen sizes.
        """
        if not element:
            return None
        els = bridge.prefetched_ui(self._device_id)  # the pre-action dump
        if not els:
            return None
        width = max((e.bounds[2] for e in els), default=0)
        height = max((e.bounds[3] for e in els), default=0)
        if not width or not height:
            return None
        x = int(element[0] / 1000 * width)
        y = int(element[1] / 1000 * height)
        hits = [
            e for e in els
            if e.bounds[0] <= x < e.bounds[2] and e.bounds[1] <= y < e.bounds[3]
            and (e.text or e.id or e.desc)
        ]
        if not hits:
            return None
        # smallest element under the point is the most specific target
        best = min(hits, key=lambda e: (e.bounds[2] - e.bounds[0]) * (e.bounds[3] - e.bounds[1]))
        target = {}
        if best.text:
            target["target_text"] = best.text
        if best.id:
            target["target_id"] = best.id
        if best.desc:
            target["target_desc"] = best.desc
        return target or None


class FlowReplayer:
    """Deterministic replay - drives recorded actions through ActionHandler.

    No model calls: exact presses at the recorded (relative) points, converted
    to this device's resolution at replay time.
    """

    def __init__(self, device_id: Optional[str] = None, flows_dir: str = DEFAULT_FLOWS_DIR):
        self.device_id = device_id
        self.flows_dir = flows_dir
        self.action_handler = ActionHandler(
            device_id=device_id,
            confirmation_callback=lambda _msg: True,
            takeover_callback=lambda _msg: None,
        )

    def replay(
        self,
        flow: Flow,
        speed: float = 1.0,
        step_callback: Optional[Callable[[int, Dict[str, Any], bool], None]] = None,
    ) -> Dict[str, Any]:
        """Replay a flow on the device.

        Args:
            flow: The Flow to replay.
            speed: Time multiplier for recorded delays (2.0 = twice as fast).
            step_callback: Optional callback(step_index, action, success).

        Returns:
            Summary dict with executed/failed step counts.
        """
        if not flow.steps:
            return self._finalize({
                "flow": flow.name,
                "device_id": self.device_id,
                "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "executed": 0,
                "failed": 0,
                "verified": 0,
                "final_app": "",
                "steps": [],
                "message": "Flow has no steps",
            })

        screenshot = get_screenshot(self.device_id)
        width, height = screenshot.width, screenshot.height

        executed = 0
        failed = 0
        verified = 0
        step_reports = []
        speed = max(speed, 0.1)
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")

        for i, step in enumerate(flow.steps):
            time.sleep(step.delay_before / speed)
            result = self.action_handler.execute(step.action, width, height)
            success = result.success
            executed += 1
            if not success:
                failed += 1
            # "element" means the recorded semantic target was found on screen
            # and tapped - the step verifiably did what the flow intended.
            if result.method == "element":
                verified += 1
            step_reports.append({
                "step": i,
                "action": step.action.get("action"),
                "target": {
                    k: step.action[k]
                    for k in ("target_text", "target_id", "target_desc")
                    if step.action.get(k)
                } or None,
                "success": success,
                "method": result.method,
                "message": result.message,
            })
            if step_callback:
                step_callback(i, step.action, success)

        final_app = ""
        try:
            final_app = get_current_app(self.device_id)
        except Exception:
            pass

        return self._finalize({
            "flow": flow.name,
            "device_id": self.device_id,
            "started_at": started_at,
            "executed": executed,
            "failed": failed,
            "verified": verified,
            "final_app": final_app,
            "steps": step_reports,
            "message": "Replay complete" if failed == 0 else f"Replay finished with {failed} failed step(s)",
        })

    def _finalize(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """Best-effort report persistence - storage failure never fails a replay."""
        try:
            summary["report_path"] = str(save_run_report(summary, flows_dir=self.flows_dir))
        except OSError:
            pass
        return summary


def runs_dir(flows_dir: str = DEFAULT_FLOWS_DIR) -> Path:
    return Path(flows_dir) / "runs"


def save_run_report(summary: Dict[str, Any], flows_dir: str = DEFAULT_FLOWS_DIR) -> Path:
    """Persist one replay's expected-vs-actual ledger."""
    directory = runs_dir(flows_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # timestamp orders reports; the uuid suffix keeps same-second replays
    # (same flow on several phones) from overwriting each other
    path = directory / (
        f"{_safe_name(summary['flow'])}-{int(time.time())}-{uuid.uuid4().hex[:8]}.json"
    )
    with open(path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path


def list_run_reports(
    flow_name: Optional[str] = None,
    flows_dir: str = DEFAULT_FLOWS_DIR,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Saved replay reports, newest first - what each run actually did."""
    directory = runs_dir(flows_dir)
    if not directory.exists():
        return []
    pattern = f"{_safe_name(flow_name)}-*.json" if flow_name else "*.json"
    reports = []
    for path in sorted(directory.glob(pattern), reverse=True)[:limit]:
        try:
            with open(path) as f:
                reports.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return reports


def list_installed_apps(device_id: Optional[str] = None) -> List[Dict[str, str]]:
    """Discover apps installed on a device via ADB, mapped to known names."""
    from phone_agent.config.apps import APP_PACKAGES

    cmd = ["adb"]
    if device_id:
        cmd += ["-s", device_id]
    cmd += ["shell", "pm", "list", "packages", "-3"]  # third-party apps

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"adb package query failed ({result.returncode}): {result.stderr.strip()}"
        )
    packages = [
        line.replace("package:", "").strip()
        for line in result.stdout.splitlines()
        if line.startswith("package:")
    ]

    reverse = {pkg: name for name, pkg in APP_PACKAGES.items()}
    return [
        {"package": pkg, "name": reverse.get(pkg, "")}
        for pkg in sorted(packages)
    ]
