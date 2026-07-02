"""Request bodies for the REST API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from phone_server.models import Flow, FlowStep, Selector


# --- devices / raw input ---------------------------------------------------


class ConnectBody(BaseModel):
    address: str = Field(..., description="host or host:port, e.g. 192.168.1.50:5555")


class TapBody(BaseModel):
    x: int
    y: int
    normalized: bool = Field(False, description="If true, x/y are 0-1000 relative")


class SwipeBody(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: Optional[int] = None
    normalized: bool = False


class TypeBody(BaseModel):
    text: str
    clear: bool = True
    restore: bool = Field(True, description="Restore the human keyboard after typing. Set false for bulk 'set once' typing.")


class KeyboardSetBody(BaseModel):
    ime: str = Field(..., description="Full IME id, e.g. com.android.adbkeyboard/.AdbIME")


class KeyboardResetBody(BaseModel):
    prefer: Optional[str] = Field(None, description="Substring of a preferred IME to switch back to")


class LaunchBody(BaseModel):
    app: str = Field(..., description="App name known to phone_agent config/apps.py")


class ActionBody(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class RunBody(BaseModel):
    task: str
    max_steps: Optional[int] = None
    lang: Optional[str] = None
    model_base_url: Optional[str] = None
    model_name: Optional[str] = None


# --- app control -----------------------------------------------------------


class ElementTapBody(BaseModel):
    element: Optional[str] = Field(None, description="Named element in the app profile")
    selector: Optional[Selector] = Field(None, description="Ad-hoc selector instead of a named element")


class FindBody(BaseModel):
    selector: Selector


class FlowRunBody(BaseModel):
    params: dict[str, str] = Field(default_factory=dict)


# --- onboarding ------------------------------------------------------------


class StartOnboardBody(BaseModel):
    app: str
    package: str
    device_id: str
    display_name: str = ""
    launch_activity: Optional[str] = None
    load_existing: bool = True


class SuggestBody(BaseModel):
    x: int
    y: int
    normalized: bool = True


class AddElementBody(BaseModel):
    name: str
    selector: Optional[Selector] = None
    from_x: Optional[int] = None
    from_y: Optional[int] = None
    normalized: bool = True
    screen: Optional[str] = None
    description: str = ""


class AddScreenBody(BaseModel):
    name: str
    signature_resource_ids: list[str] = Field(default_factory=list)
    signature_text: list[str] = Field(default_factory=list)
    description: str = ""
    save_screenshot: bool = True


class AddFlowBody(BaseModel):
    flow: Flow


class RecordStepBody(BaseModel):
    flow: str
    step: FlowStep
    description: str = ""
