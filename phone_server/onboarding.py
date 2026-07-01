"""Onboarding / training sessions.

An onboarding session is a scratch space where an operator (agent or human)
teaches the server a new app: capture screens, label robust selectors for the
UI elements that matter, and record reusable flows. When done, the session is
saved as an :class:`AppProfile` that any agent can then drive.

The value-add during onboarding is :func:`suggest_selector_at`: give it a tap
point and it derives a robust selector (resource-id > content-desc > text) from
the live view hierarchy, plus a normalized-coordinate fallback — so operators
teach by pointing, not by hand-writing selectors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from phone_server import adb_ext
from phone_server.appstore import STORE, slugify
from phone_server.deps import get_screen_size, norm_from_abs
from phone_server.models import AppProfile, Element, Flow, FlowStep, Screen


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _area(node: dict[str, Any]) -> int:
    x1, y1, x2, y2 = node["bounds"]
    return max(0, (x2 - x1)) * max(0, (y2 - y1))


def suggest_selector_at(nodes: list[dict[str, Any]], x: int, y: int) -> Optional[dict[str, Any]]:
    """Find the smallest node containing (x, y) and derive a robust selector.

    Returns {"selector": {...}, "node": {...}} or None. Prefers a clickable
    ancestor when the hit node itself has no usable identity.
    """
    hits = [
        n
        for n in nodes
        if n["bounds"][0] <= x <= n["bounds"][2] and n["bounds"][1] <= y <= n["bounds"][3]
    ]
    if not hits:
        return None
    hits.sort(key=_area)  # smallest first (most specific)

    def identity(n: dict[str, Any]) -> Optional[dict[str, Any]]:
        if n["resource_id"]:
            return {"resource_id": n["resource_id"]}
        if n["content_desc"]:
            return {"content_desc": n["content_desc"]}
        if n["text"]:
            return {"text": n["text"]}
        return None

    # Prefer the smallest node that has an identity; else smallest hit.
    for n in hits:
        sel = identity(n)
        if sel:
            return {"selector": sel, "node": n}
    n = hits[0]
    return {"selector": None, "node": n}


@dataclass
class Session:
    id: str
    device_id: str
    profile: AppProfile
    created_at: str = field(default_factory=_now)
    last_nodes: list[dict[str, Any]] = field(default_factory=list)


class OnboardingManager:
    """In-memory registry of active onboarding sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    # --- lifecycle ---------------------------------------------------------

    def start(
        self,
        device_id: str,
        app: str,
        package: str,
        display_name: str = "",
        launch_activity: Optional[str] = None,
        load_existing: bool = True,
    ) -> Session:
        app = slugify(app)
        profile: Optional[AppProfile] = STORE.load(app) if load_existing else None
        if profile is None:
            profile = AppProfile(
                app=app,
                package=package,
                display_name=display_name or app,
                launch_activity=launch_activity
                or adb_ext.resolve_launch_activity(package, device_id),
                onboarded_at=_now(),
            )
        else:
            # allow updating package/launch info on re-onboard
            profile.package = package or profile.package
            if launch_activity:
                profile.launch_activity = launch_activity
        sid = uuid.uuid4().hex[:12]
        sess = Session(id=sid, device_id=device_id, profile=profile)
        self._sessions[sid] = sess
        return sess

    def get(self, session_id: str) -> Session:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(session_id)
        return sess

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            {"id": s.id, "app": s.profile.app, "device_id": s.device_id, "created_at": s.created_at}
            for s in self._sessions.values()
        ]

    def discard(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    # --- capture -----------------------------------------------------------

    def capture(self, session_id: str) -> dict[str, Any]:
        """Snapshot the live UI: activity, parsed nodes, detected screen."""
        sess = self.get(session_id)
        nodes = adb_ext.get_ui_elements(sess.device_id)
        sess.last_nodes = nodes
        activity = adb_ext.get_current_activity(sess.device_id)
        # interactable nodes are the useful ones for labeling
        interactable = [
            {
                "resource_id": n["resource_id"],
                "text": n["text"],
                "content_desc": n["content_desc"],
                "class_name": n["class_name"],
                "clickable": n["clickable"],
                "center": n["center"],
                "bounds": n["bounds"],
            }
            for n in nodes
            if n["clickable"] or n["text"] or n["content_desc"]
        ]
        return {
            "activity": activity,
            "node_count": len(nodes),
            "interactable": interactable,
            "detected_screen": self._detect_screen(sess, nodes, activity),
        }

    def suggest_at(self, session_id: str, x: int, y: int, normalized: bool) -> dict[str, Any]:
        sess = self.get(session_id)
        nodes = sess.last_nodes or adb_ext.get_ui_elements(sess.device_id)
        if normalized:
            w, h = get_screen_size(sess.device_id)
            x, y = int(x / 1000 * w), int(y / 1000 * h)
        found = suggest_selector_at(nodes, x, y)
        if not found:
            return {"found": False}
        return {
            "found": True,
            "selector": found["selector"],
            "node": found["node"],
            "fallback_norm": norm_from_abs(sess.device_id, *found["node"]["center"]),
        }

    # --- authoring ---------------------------------------------------------

    def add_element(
        self,
        session_id: str,
        name: str,
        selector: Optional[dict[str, Any]] = None,
        from_point: Optional[tuple[int, int, bool]] = None,
        screen: Optional[str] = None,
        description: str = "",
    ) -> Element:
        sess = self.get(session_id)
        selectors = []
        fallback = None
        if from_point is not None:
            sug = self.suggest_at(session_id, *from_point)
            if sug.get("found"):
                if sug.get("selector"):
                    selectors.append(sug["selector"])
                fallback = sug.get("fallback_norm")
        if selector:
            selectors.insert(0, selector)
        el = Element(
            name=name,
            selectors=[s for s in selectors if s],
            fallback_norm=fallback,
            screen=screen,
            description=description,
        )
        sess.profile.elements[name] = el
        return el

    def add_screen(
        self,
        session_id: str,
        name: str,
        signature_resource_ids: Optional[list[str]] = None,
        signature_text: Optional[list[str]] = None,
        description: str = "",
        screenshot: Optional[str] = None,
    ) -> Screen:
        sess = self.get(session_id)
        activity = adb_ext.get_current_activity(sess.device_id)
        screen = Screen(
            name=name,
            activity=activity,
            signature_resource_ids=signature_resource_ids or [],
            signature_text=signature_text or [],
            description=description,
            screenshot=screenshot,
        )
        sess.profile.screens[name] = screen
        return screen

    def add_flow(self, session_id: str, flow: Flow) -> Flow:
        sess = self.get(session_id)
        sess.profile.flows[flow.name] = flow
        return flow

    def record_step(self, session_id: str, flow_name: str, step: FlowStep, description: str = "") -> Flow:
        """Append a step to a (possibly new) draft flow — for capture-by-doing."""
        sess = self.get(session_id)
        flow = sess.profile.flows.get(flow_name) or Flow(name=flow_name, description=description)
        flow.steps.append(step)
        sess.profile.flows[flow_name] = flow
        return flow

    # --- save --------------------------------------------------------------

    def save(self, session_id: str) -> dict[str, Any]:
        sess = self.get(session_id)
        sess.profile.updated_at = _now()
        path = STORE.save(sess.profile)
        return {"saved": path, "summary": sess.profile.summary()}

    # --- internal ----------------------------------------------------------

    def _detect_screen(self, sess: Session, nodes, activity) -> Optional[str]:
        rids = {n["resource_id"] for n in nodes}
        texts = {n["text"] for n in nodes}
        for name, screen in sess.profile.screens.items():
            if screen.signature_resource_ids and not all(r in rids for r in screen.signature_resource_ids):
                continue
            if screen.signature_text and not all(t in texts for t in screen.signature_text):
                continue
            if screen.activity and activity and screen.activity != activity:
                continue
            if screen.signature_resource_ids or screen.signature_text or screen.activity:
                return name
        return None


# Module-level singleton shared by routers.
MANAGER = OnboardingManager()
