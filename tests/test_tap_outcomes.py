from types import SimpleNamespace

import pytest

import phone_agent.actions.handler as handler_module
from phone_agent import bridge
from phone_agent.actions.handler import ActionHandler


def element(text="Send"):
    return SimpleNamespace(
        text=text,
        id="",
        desc="",
        bounds=(0, 0, 100, 100),
        center=(50, 50),
        clickable=True,
        enabled=True,
        parent_index=None,
    )


class FakeBridge:
    def __init__(self, elements=None, *, ui_error=None, tap_error=None):
        self.elements = list(elements or [])
        self.ui_error = ui_error
        self.tap_error = tap_error
        self.ui_calls = 0
        self.tap_calls = []

    def ui(self):
        self.ui_calls += 1
        if self.ui_error is not None:
            raise self.ui_error
        return self.elements

    def tap(self, target):
        self.tap_calls.append(target)
        if self.tap_error is not None:
            raise self.tap_error


@pytest.fixture
def use_bridge(monkeypatch):
    def install(fake):
        monkeypatch.setattr(bridge, "get_bridge", lambda _device=None: fake)
        return fake

    return install


def test_missing_bridge_error_remains_a_pre_tap_runtime_error(monkeypatch):
    monkeypatch.setattr(bridge, "get_bridge", lambda _device=None: None)

    with pytest.raises(
        RuntimeError, match="adb-agent-bridge is not installed"
    ) as caught:
        bridge.tap_target("serial", text="Send")

    assert type(caught.value) is RuntimeError
    assert caught.value.__cause__ is None


def test_ui_error_remains_a_pre_tap_runtime_error(use_bridge):
    fake = use_bridge(FakeBridge(ui_error=RuntimeError("UI unavailable before tap")))

    with pytest.raises(RuntimeError, match="UI unavailable before tap") as caught:
        bridge.tap_target("serial", text="Send")

    assert type(caught.value) is RuntimeError
    assert caught.value.__cause__ is None
    assert fake.tap_calls == []


@pytest.mark.parametrize("selector", [{}, {"text": ""}, {"text": "Missing"}])
def test_tap_target_returns_false_for_known_invalid_or_missing_selectors(
    use_bridge, selector
):
    fake = use_bridge(FakeBridge([element()]))

    assert bridge.tap_target("serial", **selector) is False
    assert fake.tap_calls == []


def test_semantic_action_raises_typed_ambiguity_before_dispatch(use_bridge):
    fake = use_bridge(FakeBridge([element(), element()]))

    with pytest.raises(bridge.AmbiguousSelector, match="ambiguous"):
        bridge.semantic_action("serial", "tap", text="Send")

    assert fake.tap_calls == []


def test_tap_target_uses_ambiguity_type_not_exception_text(monkeypatch):
    def ambiguous(*_args, **_kwargs):
        raise bridge.AmbiguousSelector("wording deliberately changed")

    monkeypatch.setattr(bridge, "semantic_action", ambiguous)

    assert bridge.tap_target("serial", text="Send") is False


@pytest.mark.parametrize(
    "error_type,message",
    [
        (RuntimeError, "lost response"),
        (ValueError, "invalid bridge response"),
        (LookupError, "bridge response missing"),
        (TimeoutError, "bridge timed out"),
    ],
)
def test_semantic_action_types_every_tap_dispatch_error_as_uncertain(
    use_bridge, error_type, message
):
    error = error_type(message)
    target = element()
    fake = use_bridge(FakeBridge([target], tap_error=error))

    with pytest.raises(bridge.TapOutcomeUncertain, match="inspect the phone") as caught:
        bridge.semantic_action("serial", "tap", text="Send")

    assert caught.value.__cause__ is error
    assert fake.ui_calls == 1
    assert fake.tap_calls == [target]


@pytest.mark.parametrize(
    "error_type",
    [RuntimeError, ValueError, LookupError, TimeoutError],
)
def test_action_handler_does_not_swallow_or_fall_through_after_tap_dispatch(
    use_bridge, monkeypatch, error_type
):
    target = element()
    fake = use_bridge(FakeBridge([target], tap_error=error_type("lost response")))
    coordinate_taps = []
    monkeypatch.setattr(
        handler_module,
        "tap",
        lambda *args, **kwargs: coordinate_taps.append((args, kwargs)),
    )
    handler = ActionHandler(device_id="serial")

    result = handler.execute(
        {
            "_metadata": "do",
            "action": "Tap",
            "element": [500, 500],
            "target_text": "Send",
        },
        1080,
        1920,
    )

    assert result.success is False
    assert result.should_finish is True
    assert result.message == (
        "Action failed: Tap outcome uncertain; inspect the phone before retrying"
    )
    assert fake.tap_calls == [target]
    assert coordinate_taps == []
