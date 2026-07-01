"""Flow execution engine.

Runs an :class:`~phone_server.models.Flow` against a device. Steps locate UI
targets by live selector (robust) with a normalized-coordinate fallback, so a
flow recorded during onboarding keeps working across app updates and screen
sizes. Runs synchronously — call it via ``run_in_threadpool`` from async code.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from phone_agent.adb import back, double_tap, home, long_press, swipe, tap
from phone_agent.adb.device import _get_adb_prefix  # keyevent by name
import subprocess

from phone_server import adb_ext
from phone_server.deps import do_type_text, get_screen_size, resolve_xy
from phone_server.models import AppProfile, Element, FlowStep, Selector

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class FlowError(Exception):
    """Raised when a required step cannot complete."""


@dataclass
class StepResult:
    index: int
    action: str
    ok: bool
    detail: str = ""


@dataclass
class FlowResult:
    ok: bool
    steps: list[StepResult] = field(default_factory=list)
    error: Optional[str] = None


def _subst(value: Any, params: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: str(params.get(m.group(1), m.group(0))), value)
    return value


def _press_keyevent(device_id: str, keycode: str) -> None:
    subprocess.run(
        _get_adb_prefix(device_id) + ["shell", "input", "keyevent", str(keycode)],
        capture_output=True,
    )


class FlowRunner:
    """Executes flows and resolves elements for a single app profile."""

    def __init__(self, profile: AppProfile, device_id: str):
        self.profile = profile
        self.device_id = device_id

    # --- element resolution -------------------------------------------------

    def resolve_element(
        self, element: Optional[Element], selector: Optional[Selector], nodes=None
    ) -> Optional[tuple[int, int]]:
        """Return absolute (x, y) for an element or ad-hoc selector, or None."""
        selectors: list[Selector] = []
        fallback: Optional[list[int]] = None
        if element is not None:
            selectors = list(element.selectors)
            fallback = element.fallback_norm
        if selector is not None and not selector.is_empty():
            selectors = [selector, *selectors]

        if selectors:
            if nodes is None:
                nodes = adb_ext.get_ui_elements(self.device_id)
            for sel in selectors:
                node = adb_ext.resolve_selector(nodes, sel.model_dump(exclude_none=True))
                if node:
                    return tuple(node["center"])  # type: ignore[return-value]

        if fallback:
            return resolve_xy(self.device_id, fallback[0], fallback[1], normalized=True)
        return None

    def _element_by_name(self, name: str) -> Element:
        el = self.profile.elements.get(name)
        if el is None:
            raise FlowError(f"unknown element '{name}' in app '{self.profile.app}'")
        return el

    # --- screen detection ---------------------------------------------------

    def current_screen(self, nodes=None) -> Optional[str]:
        """Return the name of the best-matching known screen, or None."""
        activity = adb_ext.get_current_activity(self.device_id)
        if nodes is None:
            nodes = adb_ext.get_ui_elements(self.device_id)
        rids = {n["resource_id"] for n in nodes}
        texts = {n["text"] for n in nodes}

        best: Optional[str] = None
        best_score = 0
        for name, screen in self.profile.screens.items():
            score = 0
            if screen.activity and activity and screen.activity == activity:
                score += 2
            if screen.signature_resource_ids:
                if all(r in rids for r in screen.signature_resource_ids):
                    score += len(screen.signature_resource_ids)
                else:
                    continue  # required signature missing → not this screen
            if screen.signature_text:
                if all(t in texts for t in screen.signature_text):
                    score += len(screen.signature_text)
                else:
                    continue
            if score > best_score:
                best, best_score = name, score
        return best

    def matches_screen(self, screen_name: str) -> bool:
        return self.current_screen() == screen_name

    # --- step execution -----------------------------------------------------

    def run(self, flow, params: dict[str, str]) -> FlowResult:
        result = FlowResult(ok=True)
        for i, step in enumerate(flow.steps):
            try:
                detail = self._exec_step(step, params)
                result.steps.append(StepResult(i, step.action, True, detail))
            except Exception as e:  # noqa: BLE001
                result.steps.append(StepResult(i, step.action, False, str(e)))
                if not step.optional:
                    result.ok = False
                    result.error = f"step {i} ({step.action}) failed: {e}"
                    break
        return result

    def _tap_point(self, step: FlowStep) -> str:
        if step.element:
            xy = self.resolve_element(self._element_by_name(step.element), step.selector)
        elif step.selector:
            xy = self.resolve_element(None, step.selector)
        elif step.x is not None and step.y is not None:
            xy = resolve_xy(self.device_id, step.x, step.y, step.normalized)
        else:
            raise FlowError("tap step needs element, selector, or x/y")
        if xy is None:
            raise FlowError("target not found on screen")
        return f"{xy[0]},{xy[1]}", xy  # type: ignore[return-value]

    def _exec_step(self, step: FlowStep, params: dict[str, str]) -> str:
        a = step.action
        text = _subst(step.text, params) if step.text is not None else None

        if a == "open_app":
            pkg = self.profile.package
            act = self.profile.launch_activity
            p = _get_adb_prefix(self.device_id)
            if act:
                subprocess.run(p + ["shell", "am", "start", "-n", act], capture_output=True)
            else:
                subprocess.run(
                    p + ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
                    capture_output=True,
                )
            time.sleep(2.0)
            return f"launched {pkg}"

        if a in ("tap_element", "tap"):
            desc, xy = self._tap_point(step)
            tap(xy[0], xy[1], self.device_id)
            return f"tapped {desc}"

        if a == "double_tap":
            _, xy = self._tap_point(step)
            double_tap(xy[0], xy[1], self.device_id)
            return f"double-tapped {xy[0]},{xy[1]}"

        if a == "long_press":
            _, xy = self._tap_point(step)
            long_press(xy[0], xy[1], device_id=self.device_id)
            return f"long-pressed {xy[0]},{xy[1]}"

        if a == "type":
            if step.element:
                _, xy = self._tap_point(step)
                tap(xy[0], xy[1], self.device_id)
                time.sleep(0.5)
            do_type_text(self.device_id, text or "", step.clear)
            return f"typed {len(text or '')} chars"

        if a == "swipe":
            if not step.start or not step.end:
                raise FlowError("swipe needs start and end")
            sx, sy = resolve_xy(self.device_id, step.start[0], step.start[1], step.normalized)
            ex, ey = resolve_xy(self.device_id, step.end[0], step.end[1], step.normalized)
            swipe(sx, sy, ex, ey, device_id=self.device_id)
            return f"swiped {sx},{sy}->{ex},{ey}"

        if a == "swipe_dir":
            w, h = get_screen_size(self.device_id)
            cx = w // 2
            mapping = {
                "up": (cx, int(h * 0.7), cx, int(h * 0.3)),
                "down": (cx, int(h * 0.3), cx, int(h * 0.7)),
                "left": (int(w * 0.8), h // 2, int(w * 0.2), h // 2),
                "right": (int(w * 0.2), h // 2, int(w * 0.8), h // 2),
            }
            coords = mapping.get((step.direction or "").lower())
            if not coords:
                raise FlowError(f"bad direction '{step.direction}'")
            swipe(*coords, device_id=self.device_id)
            return f"swiped {step.direction}"

        if a == "back":
            back(self.device_id)
            return "back"

        if a == "home":
            home(self.device_id)
            return "home"

        if a == "press_key":
            if not step.keycode:
                raise FlowError("press_key needs keycode")
            _press_keyevent(self.device_id, step.keycode)
            return f"key {step.keycode}"

        if a == "wait":
            time.sleep(step.seconds or 1.0)
            return f"waited {step.seconds or 1.0}s"

        if a == "wait_for":
            timeout = step.timeout or 10.0
            deadline = time.time() + timeout
            sel = step.selector
            el = self._element_by_name(step.element) if step.element else None
            while time.time() < deadline:
                if self.resolve_element(el, sel) is not None:
                    return "element appeared"
                time.sleep(0.6)
            raise FlowError(f"element not found within {timeout}s")

        if a == "assert_screen":
            timeout = step.timeout or 6.0
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self.current_screen() == step.screen:
                    return f"on screen '{step.screen}'"
                time.sleep(0.6)
            raise FlowError(f"not on screen '{step.screen}' (got '{self.current_screen()}')")

        if a == "capture":
            # Artifact capture is handled by the caller (needs the AppStore); the
            # step is a no-op marker here so flows remain runnable standalone.
            return f"capture:{step.name or 'snapshot'}"

        raise FlowError(f"unknown action '{a}'")
