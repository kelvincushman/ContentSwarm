"""Stop before acting on missing observations or non-unique UI targets."""

from types import SimpleNamespace

import pytest
from test_bridge import FakeBridge, element

import phone_agent.agent as agent_module
from phone_agent import bridge
from phone_agent.adb.screenshot import _create_fallback_screenshot
from phone_agent.agent import AgentConfig, PhoneAgent


def test_failed_capture_is_not_used_as_a_real_observation(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        "ModelClient",
        lambda _: SimpleNamespace(
            request=lambda _: pytest.fail("no model on black fallback")
        ),
    )
    monkeypatch.setattr(
        agent_module, "get_screenshot", lambda _: _create_fallback_screenshot(False)
    )
    monkeypatch.setattr(agent_module, "get_current_app", lambda _: "Settings")
    agent = PhoneAgent(agent_config=AgentConfig(verbose=False))
    with pytest.raises(RuntimeError, match="Screenshot unavailable"):
        agent.run("Open Settings")


@pytest.mark.parametrize(
    "nodes",
    [
        [element(text="Next"), element(text="Next")],
        [element(text="Next", enabled=False)],
    ],
)
def test_legacy_target_path_does_not_tap_ambiguous_or_disabled_control(
    monkeypatch, nodes
):
    fake = FakeBridge([nodes])
    fake.find = lambda **_: nodes[0]  # Old helper returned the first match.
    monkeypatch.setattr(bridge, "get_bridge", lambda _: fake)
    assert not bridge.tap_target("serial", text="Next")
    assert fake.calls == []


def test_uncertain_tap_is_terminal_and_not_repeated(monkeypatch):
    from phone_agent.actions.handler import ActionHandler, do

    fake = FakeBridge([[element(text="Next")]])
    calls = []

    def uncertain(_):
        calls.append("tap")
        raise TimeoutError("response lost")

    fake.tap = uncertain
    monkeypatch.setattr(bridge, "get_bridge", lambda _: fake)
    result = ActionHandler().execute(
        do(action="Tap", target_text="Next", element=[50, 50]), 100, 100
    )
    assert not result.success and result.should_finish
    assert calls == ["tap"]


def test_uncertain_typing_never_enters_legacy_fallback(monkeypatch):
    import phone_agent.actions.handler as handler_module
    from phone_agent.actions.handler import ActionHandler, do

    fake = FakeBridge()
    fake.text = lambda *_args, **_kw: (_ for _ in ()).throw(
        TimeoutError("typed but response lost")
    )
    monkeypatch.setattr(bridge, "get_bridge", lambda _: fake)
    monkeypatch.setattr(
        handler_module,
        "detect_and_set_adb_keyboard",
        lambda *_: pytest.fail("must not retry typing"),
        raising=False,
    )
    result = ActionHandler().execute(do(action="Type", text="example"), 100, 100)
    assert not result.success and result.should_finish


def test_failed_screencap_cannot_pull_an_older_frame(monkeypatch):
    import phone_agent.adb.screenshot as shots

    calls = []

    def run(command, **_):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(shots.subprocess, "run", run)
    shot = shots.get_screenshot("serial")
    assert getattr(shot, "capture_error", None)
    assert len(calls) == 1


def test_screenshot_api_returns_error_not_a_black_success(monkeypatch):
    from flask import Flask

    from phone_agent.api import create_api_blueprint

    monkeypatch.setattr(
        "phone_agent.adb.get_screenshot", lambda _: _create_fallback_screenshot(False)
    )
    manager = SimpleNamespace(phones={"p": SimpleNamespace(device_id="serial")})
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint({"phone_manager": manager}), url_prefix="/api/v1"
    )
    response = app.test_client().get("/api/v1/phones/p/screenshot")
    assert response.status_code == 503
    assert "Screenshot unavailable" in response.json["error"]


def test_recorded_sensitive_action_keeps_confirmation_marker():
    from phone_agent.flows import FlowRecorder

    recorder = FlowRecorder("sensitive", "stop at commit")
    recorder.on_event(
        {
            "event": "step_completed",
            "success": True,
            "action": {
                "_metadata": "do",
                "action": "Tap",
                "message": "Confirm publish?",
                "target_text": "Post",
            },
        }
    )
    assert recorder.flow.steps[0].action["message"] == "Confirm publish?"


@pytest.mark.parametrize("name", ["Double Tap", "Long Press"])
def test_unsupported_semantic_gesture_never_uses_old_coordinates(monkeypatch, name):
    import phone_agent.actions.handler as handler_module
    from phone_agent.actions.handler import ActionHandler, do

    monkeypatch.setattr(
        handler_module, "double_tap", lambda *_args, **_kw: pytest.fail("stale coords")
    )
    monkeypatch.setattr(
        handler_module, "long_press", lambda *_args, **_kw: pytest.fail("stale coords")
    )
    result = ActionHandler().execute(
        do(action=name, target_text="Next", element=[50, 50]), 100, 100
    )
    assert not result.success and result.should_finish
