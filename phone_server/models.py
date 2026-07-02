"""Pydantic data models for app onboarding & control.

An **AppProfile** is the saved knowledge produced by an onboarding/training
session. It captures how to recognise an app's screens, how to locate its UI
elements robustly (by Android view selectors, with a coordinate fallback), and
named **flows** (reusable, parameterised action sequences) that agents replay.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class Selector(BaseModel):
    """A robust way to locate a UI node in the live view hierarchy.

    Fields are ANDed together; empty fields are ignored. `text`/`content_desc`
    match exactly; `text_contains` is a case-insensitive substring match. When
    several nodes match, `index` (0-based) disambiguates.
    """

    resource_id: Optional[str] = None
    text: Optional[str] = None
    text_contains: Optional[str] = None
    content_desc: Optional[str] = None
    class_name: Optional[str] = None
    clickable: Optional[bool] = None
    index: Optional[int] = None

    def is_empty(self) -> bool:
        return not any(
            v is not None
            for v in (
                self.resource_id,
                self.text,
                self.text_contains,
                self.content_desc,
                self.class_name,
                self.clickable,
            )
        )


class Element(BaseModel):
    """A named UI target within an app.

    Resolution order at run time: try each selector against the live hierarchy;
    if none match, fall back to `fallback_norm` (normalised 0-1000 tap point
    recorded during onboarding).
    """

    name: str
    selectors: list[Selector] = Field(default_factory=list)
    fallback_norm: Optional[list[int]] = None  # [x, y] in 0-1000 space
    screen: Optional[str] = None
    description: str = ""


class Screen(BaseModel):
    """A recognisable app state.

    A screen is considered "current" when the resumed activity matches
    `activity` (if set) AND all `signature_resource_ids` / `signature_text`
    are present in the live hierarchy.
    """

    name: str
    activity: Optional[str] = None
    signature_resource_ids: list[str] = Field(default_factory=list)
    signature_text: list[str] = Field(default_factory=list)
    screenshot: Optional[str] = None  # filename under the app's screens/ dir
    description: str = ""


class FlowStep(BaseModel):
    """A single step in a flow. `action` selects which fields are used.

    Supported actions:
      open_app                     — launch the profile's package
      tap_element   {element|selector}
      tap           {x, y, normalized}
      long_press    {x, y, normalized}
      double_tap    {x, y, normalized}
      type          {text, clear, restore, element?}  — tap `element` first if given;
                                                          restore=false leaves AdbIME set (bulk)
      swipe         {start[x,y], end[x,y], normalized}
      swipe_dir     {direction: up|down|left|right}
      back | home
      press_key     {keycode}
      wait          {seconds}
      wait_for      {element|selector, timeout}  — poll until present
      assert_screen {screen, timeout?}
      capture       {name}                        — save a screenshot artifact

    Any string field supports {{param}} substitution from the flow's params.
    Set `optional: true` so a failing step is logged but does not abort the flow.
    """

    action: str
    element: Optional[str] = None
    selector: Optional[Selector] = None
    x: Optional[int] = None
    y: Optional[int] = None
    normalized: bool = True
    start: Optional[list[int]] = None
    end: Optional[list[int]] = None
    direction: Optional[str] = None
    text: Optional[str] = None
    clear: bool = True
    restore: bool = True
    seconds: Optional[float] = None
    keycode: Optional[str] = None
    screen: Optional[str] = None
    timeout: Optional[float] = None
    name: Optional[str] = None
    optional: bool = False


class Flow(BaseModel):
    """A named, parameterised sequence of steps agents can replay."""

    name: str
    description: str = ""
    params: list[str] = Field(default_factory=list)
    steps: list[FlowStep] = Field(default_factory=list)


class AppProfile(BaseModel):
    """Everything the server knows about one onboarded app."""

    app: str  # slug / key, e.g. "twitter"
    package: str  # android package, e.g. "com.twitter.android"
    display_name: str = ""
    launch_activity: Optional[str] = None
    onboarded_at: Optional[str] = None
    updated_at: Optional[str] = None
    screens: dict[str, Screen] = Field(default_factory=dict)
    elements: dict[str, Element] = Field(default_factory=dict)
    flows: dict[str, Flow] = Field(default_factory=dict)
    notes: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "package": self.package,
            "display_name": self.display_name,
            "screens": sorted(self.screens),
            "elements": sorted(self.elements),
            "flows": {k: v.params for k, v in self.flows.items()},
            "onboarded_at": self.onboarded_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Registry: device configs, accounts, and editable server config
# ---------------------------------------------------------------------------


class Account(BaseModel):
    """A social account bound to a phone + app, targetable by agents.

    e.g. {platform: facebook, kind: business, app: facebook, handle: "Acme Ltd"}.
    """

    id: str = ""
    name: str
    platform: str  # facebook | instagram | linkedin | x | tiktok | ...
    kind: str = "personal"  # personal | business | creator | page
    app: Optional[str] = None  # onboarded app slug this account uses
    handle: str = ""  # @handle / page name / profile url
    notes: str = ""


class DeviceConfig(BaseModel):
    """User-facing config + accounts for one phone."""

    device_id: str
    label: str = ""
    model_provider: Optional[str] = None  # e.g. "ollama@192.168.55.231"
    model_name: Optional[str] = None
    model_base_url: Optional[str] = None
    accounts: dict[str, Account] = Field(default_factory=dict)
    pin: Optional[str] = None  # numeric unlock PIN; NEVER returned by the API
    notes: str = ""

    def public_dict(self) -> dict:
        """model_dump with the PIN stripped and replaced by a has_pin flag."""
        d = self.model_dump()
        d.pop("pin", None)
        d["has_pin"] = bool(self.pin)
        return d


class ModelHost(BaseModel):
    """An OpenAI-compatible model endpoint the console can pick models from."""

    name: str
    base_url: str
    api_key: str = "EMPTY"
    kind: str = "openai-compatible"  # openai-compatible | ollama


class EditableConfig(BaseModel):
    """Runtime-editable server settings (persisted; some override env)."""

    default_model_base_url: Optional[str] = None
    default_model_name: Optional[str] = None
    default_lang: Optional[str] = None
    stream_fps: Optional[float] = None
    public_url: Optional[str] = None  # advertised base URL for the hookup kit
    model_hosts: list[ModelHost] = Field(default_factory=list)
