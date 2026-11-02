from types import SimpleNamespace

import pytest

import phone_agent.actions.handler as handler_module
import phone_agent.agent as agent_module
import phone_agent.flows as flows_module
import phone_agent.model.client as client_module
from phone_agent.actions.handler import ActionHandler, ActionResult, parse_action
from phone_agent.agent import AgentConfig, PhoneAgent, StepResult
from phone_agent.flows import Flow, FlowReplayer, FlowStep
from phone_agent.model.client import ModelConfig, ModelResponse


class StopRequested(RuntimeError):
    pass


def _agent(monkeypatch, *, max_steps=2, events=None, stop_check=None):
    monkeypatch.setattr(agent_module, "ModelClient", lambda _config: SimpleNamespace())
    return PhoneAgent(
        agent_config=AgentConfig(max_steps=max_steps, verbose=False),
        event_callback=events.append if events is not None else None,
        stop_check=stop_check,
    )


def _mock_screen(monkeypatch):
    screenshot = SimpleNamespace(width=1080, height=1920, base64_data="image")
    monkeypatch.setattr(agent_module, "get_screenshot", lambda _device: screenshot)
    monkeypatch.setattr(agent_module, "get_current_app", lambda _device: "Settings")
    return screenshot


def test_run_raises_when_model_request_fails(monkeypatch):
    agent = _agent(monkeypatch)
    _mock_screen(monkeypatch)
    agent.model_client.request = lambda _messages: (_ for _ in ()).throw(
        TimeoutError("model timed out")
    )

    with pytest.raises(RuntimeError, match="Model error: model timed out"):
        agent.run("Open Settings")


def test_invalid_model_action_fails_without_finished_event(monkeypatch):
    events = []
    agent = _agent(monkeypatch, events=events)
    _mock_screen(monkeypatch)
    agent.model_client.request = lambda _messages: ModelResponse(
        thinking="not sure", action="this is not an action", raw_content=""
    )

    with pytest.raises(RuntimeError, match="Invalid model action"):
        agent.run("Open Settings")

    assert any(
        event["event"] == "step_completed" and event["success"] is False
        for event in events
    )
    assert all(event["event"] != "task_finished" for event in events)


def test_handler_exception_is_one_failed_attempt_not_a_synthetic_finish(monkeypatch):
    events = []
    agent = _agent(monkeypatch, events=events)
    _mock_screen(monkeypatch)
    agent.model_client.request = lambda _messages: ModelResponse(
        thinking="tap", action="do(action='Back')", raw_content=""
    )
    calls = []

    def execute(action, _width, _height):
        calls.append(action)
        if len(calls) == 1:
            raise ValueError("device disconnected")
        return ActionResult(True, True, "synthetic success")

    agent.action_handler.execute = execute

    with pytest.raises(RuntimeError, match="Action failed: device disconnected"):
        agent.run("Go back")

    assert len(calls) == 1
    assert all(event["event"] != "task_finished" for event in events)


def test_run_raises_at_max_steps(monkeypatch):
    agent = _agent(monkeypatch, max_steps=2)
    attempts = []

    def unfinished(*_args, **_kwargs):
        attempts.append(None)
        agent._step_count += 1
        return StepResult(True, False, {"_metadata": "do"}, "")

    monkeypatch.setattr(agent, "_execute_step", unfinished)

    with pytest.raises(RuntimeError, match="Max steps reached"):
        agent.run("Never finishes")

    assert len(attempts) == 2


@pytest.mark.parametrize(
    "response",
    [
        "doing(action='Tap')",
        "finish_later(message='done')",
        "do('Tap')",
        "finish('done')",
        "do(action='Tap', **{'element': [1, 2]})",
        "finish(message='done') trailing text",
    ],
)
def test_parse_action_requires_an_exact_call_name_and_keyword_arguments(response):
    with pytest.raises(ValueError):
        parse_action(response)


@pytest.mark.parametrize(
    "response",
    [
        "finish(message='')",
        "finish(message='   ')",
        "finish(message=42)",
        "finish()",
    ],
)
def test_parse_action_requires_a_nonempty_finish_message(response):
    with pytest.raises(ValueError, match="message"):
        parse_action(response)


def test_parse_action_keeps_the_existing_do_and_finish_schema():
    assert parse_action("do(action='Tap', element=[100, 200])") == {
        "_metadata": "do",
        "action": "Tap",
        "element": [100, 200],
    }
    assert parse_action('finish(message="Task complete")') == {
        "_metadata": "finish",
        "message": "Task complete",
    }


def test_semantic_tap_lookup_failure_never_falls_back_to_coordinates(monkeypatch):
    raw_taps = []
    monkeypatch.setattr(
        handler_module.bridge, "tap_target", lambda *_args, **_kwargs: False
    )
    monkeypatch.setattr(handler_module, "tap", lambda *args: raw_taps.append(args))
    handler = ActionHandler(device_id="serial")

    result = handler.execute(
        {
            "_metadata": "do",
            "action": "Tap",
            "element": [500, 500],
            "target_text": "Publish",
        },
        1080,
        1920,
    )

    assert result.success is False
    assert "not found" in result.message.lower()
    assert raw_taps == []


def test_model_client_disables_retries_and_uses_configured_timeout(monkeypatch):
    kwargs = {}

    def fake_openai(**supplied):
        kwargs.update(supplied)
        return SimpleNamespace()

    monkeypatch.setattr(client_module, "OpenAI", fake_openai)
    ModelConfig(request_timeout=12.5)
    client_module.ModelClient(ModelConfig(request_timeout=12.5))

    assert kwargs["timeout"] == 12.5
    assert kwargs["max_retries"] == 0


def test_empty_flow_is_a_failed_replay(tmp_path):
    outcome = FlowReplayer(flows_dir=str(tmp_path)).replay(Flow("empty", "nothing"))

    assert outcome["executed"] == 0
    assert outcome["failed"] == 1
    assert "no steps" in outcome["message"].lower()


def _mock_replay_device(monkeypatch):
    monkeypatch.setattr(
        flows_module,
        "get_screenshot",
        lambda _device: SimpleNamespace(width=1080, height=1920),
    )
    monkeypatch.setattr(flows_module, "get_current_app", lambda _device: "Settings")
    monkeypatch.setattr(flows_module.time, "sleep", lambda _seconds: None)


def test_replay_stops_after_its_first_failed_step(tmp_path, monkeypatch):
    _mock_replay_device(monkeypatch)
    replayer = FlowReplayer(flows_dir=str(tmp_path))
    actions = []

    def execute(action, _width, _height):
        actions.append(action["action"])
        if len(actions) > 1:
            raise AssertionError("replay continued after a failure")
        return ActionResult(False, False, "first step failed")

    replayer.action_handler.execute = execute
    flow = Flow(
        "two-steps",
        "stop early",
        steps=[
            FlowStep({"_metadata": "do", "action": "Back"}, delay_before=0),
            FlowStep({"_metadata": "do", "action": "Home"}, delay_before=0),
        ],
    )

    outcome = replayer.replay(flow)

    assert actions == ["Back"]
    assert outcome["executed"] == 1
    assert outcome["failed"] == 1


@pytest.mark.parametrize(
    "action",
    [
        {
            "_metadata": "do",
            "action": "Tap",
            "element": [500, 500],
            "message": "Publish this post?",
        },
        {
            "_metadata": "do",
            "action": "Take_over",
            "message": "Complete login",
        },
    ],
)
def test_replay_denies_confirmation_and_takeover(action, tmp_path, monkeypatch):
    _mock_replay_device(monkeypatch)
    raw_taps = []
    monkeypatch.setattr(handler_module, "tap", lambda *args: raw_taps.append(args))
    flow = Flow(
        "sensitive", "must not approve", steps=[FlowStep(action, delay_before=0)]
    )

    outcome = FlowReplayer(flows_dir=str(tmp_path)).replay(flow)

    assert outcome["failed"] == 1
    assert raw_taps == []


def test_agent_stop_check_runs_before_screen_observation(monkeypatch):
    observations = []

    def stop():
        raise StopRequested("cancelled")

    agent = _agent(monkeypatch, stop_check=stop)
    monkeypatch.setattr(
        agent_module, "get_screenshot", lambda _device: observations.append("screen")
    )

    with pytest.raises(StopRequested, match="cancelled"):
        agent.run("Do nothing")

    assert observations == []


def test_agent_stop_check_runs_before_model_and_after_model_before_action(monkeypatch):
    checks = []
    model_calls = []
    action_calls = []

    def stop():
        checks.append(len(checks) + 1)
        if len(checks) == 3:
            raise StopRequested("cancelled after model")

    agent = _agent(monkeypatch, stop_check=stop)
    _mock_screen(monkeypatch)
    agent.model_client.request = lambda _messages: (
        model_calls.append(None) or ModelResponse("done", "finish(message='done')", "")
    )
    agent.action_handler.execute = lambda *_args: action_calls.append(None)

    with pytest.raises(StopRequested, match="after model"):
        agent.run("Do nothing")

    assert checks == [1, 2, 3]
    assert len(model_calls) == 1
    assert action_calls == []


def test_replay_stop_check_runs_before_delays_and_actions(tmp_path, monkeypatch):
    _mock_replay_device(monkeypatch)
    checks = []
    delays = []
    actions = []

    def stop():
        checks.append(len(checks) + 1)
        if len(checks) == 3:
            raise StopRequested("cancelled before action")

    monkeypatch.setattr(
        flows_module.time, "sleep", lambda seconds: delays.append(seconds)
    )
    replayer = FlowReplayer(flows_dir=str(tmp_path))
    replayer.action_handler.execute = lambda *_args: actions.append(None)
    flow = Flow(
        "stoppable",
        "stop",
        steps=[FlowStep({"_metadata": "do", "action": "Back"}, delay_before=1)],
    )

    with pytest.raises(StopRequested, match="before action"):
        replayer.replay(flow, stop_check=stop)

    assert checks == [1, 2, 3]
    assert delays == [1]
    assert actions == []
