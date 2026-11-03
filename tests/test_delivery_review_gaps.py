"""Mock-only regressions for independently reviewed delivery gaps."""

import time
from types import SimpleNamespace

import pytest
from flask import Flask

from phone_agent.api import create_api_blueprint


def _wait_for_event(events, name):
    until = time.monotonic() + 2
    while time.monotonic() < until:
        matches = [event for event in events if event.get("event") == name]
        if matches:
            return matches[-1]
        time.sleep(0.005)
    raise AssertionError(f"event not emitted: {name}; saw {events!r}")


def _discovery_client(discover):
    events = []
    socket = SimpleNamespace(
        emit=lambda _name, event, **_kwargs: events.append(dict(event))
    )
    automation = SimpleNamespace(discover_trending=discover)
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint({"automation": automation, "socketio": socket}),
        url_prefix="/api/v1",
    )
    return app.test_client(), events


def test_discovery_started_and_completed_events_match_pollable_outcome():
    item = SimpleNamespace(
        title="Example",
        url="https://example.test/",
        views=1,
        engagement=2,
        hashtags=[],
    )
    client, events = _discovery_client(lambda *_: [item])

    response = client.post(
        "/api/v1/pipeline/discover",
        json={"platform": "tiktok", "phone": "p", "limit": 1},
    )
    task_id = response.json["task_id"]
    started = _wait_for_event(events, "task_started")
    completed = _wait_for_event(events, "task_completed")
    outcome = client.get(f"/api/v1/tasks/{task_id}").json

    assert response.status_code == 202
    assert (started["task_id"], started["status"], started["outcome_verified"]) == (
        task_id,
        "running",
        False,
    )
    assert (
        completed["task_id"],
        completed["status"],
        completed["outcome_verified"],
    ) == (task_id, "completed", False)
    assert completed["status"] == outcome["status"]
    assert completed["outcome_verified"] == outcome["outcome_verified"]


def test_discovery_failed_event_matches_poll_and_bounds_honest_error():
    message = "mock discovery failure: " + "x" * 2000

    def fail(*_):
        raise RuntimeError(message)

    client, events = _discovery_client(fail)
    response = client.post(
        "/api/v1/pipeline/discover",
        json={"platform": "tiktok", "phone": "p", "limit": 1},
    )
    task_id = response.json["task_id"]
    failed = _wait_for_event(events, "task_failed")
    outcome = client.get(f"/api/v1/tasks/{task_id}").json

    assert (failed["task_id"], failed["status"], failed["outcome_verified"]) == (
        task_id,
        "failed",
        False,
    )
    assert failed["error"] == outcome["error"] == message[:1000]


def test_missing_typing_bridge_fails_closed_without_legacy_input(monkeypatch):
    import phone_agent.actions.handler as handler_module
    from phone_agent.actions.handler import ActionHandler, do

    monkeypatch.setattr(
        handler_module.bridge, "type_text_fast", lambda *_a, **_k: False
    )
    for name in (
        "detect_and_set_adb_keyboard",
        "clear_text",
        "type_text",
        "restore_keyboard",
    ):
        monkeypatch.setattr(
            handler_module,
            name,
            lambda *_a, _name=name, **_k: pytest.fail(f"legacy input called: {_name}"),
            raising=False,
        )

    result = ActionHandler(device_id="serial").execute(
        do(action="Type", text="do not type"), 100, 100
    )

    assert not result.success
    assert result.should_finish
    assert result.method is None
    assert "bridge" in result.message.lower()
    assert "unavailable" in result.message.lower()


def test_successful_bridge_typing_remains_nonterminal_execution(monkeypatch):
    from phone_agent.actions.handler import ActionHandler, do

    calls = []
    monkeypatch.setattr(
        "phone_agent.actions.handler.bridge.type_text_fast",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    result = ActionHandler(device_id="serial").execute(
        do(action="Type", text="example"), 100, 100
    )

    assert result.success and not result.should_finish
    assert result.method == "bridge"
    assert calls == [(("serial", "example"), {"clear": True})]


def test_event_transport_failure_cannot_stall_or_reverse_discovery():
    def broken_emit(*_a, **_k):
        raise RuntimeError("socket unavailable")

    automation = SimpleNamespace(discover_trending=lambda *_: [])
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint(
            {"automation": automation, "socketio": SimpleNamespace(emit=broken_emit)}
        ),
        url_prefix="/api/v1",
    )
    client = app.test_client()
    response = client.post(
        "/api/v1/pipeline/discover",
        json={"platform": "tiktok", "phone": "p", "limit": 1},
    )
    until = time.monotonic() + 2
    while time.monotonic() < until:
        outcome = client.get("/api/v1/tasks/" + response.json["task_id"]).json
        if outcome["status"] in ("completed", "failed"):
            break
    assert outcome["status"] == "completed" and outcome["result"] == []


def test_discovery_errors_redact_configured_and_labelled_credentials(monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_API_KEY", "CONFIGURED-SECRET")

    def fail(*_):
        raise RuntimeError(
            "Model refused CONFIGURED-SECRET Bearer OTHER-SECRET token=THIRD-SECRET https://user:PASS@host.test/path"
        )

    client, events = _discovery_client(fail)
    response = client.post(
        "/api/v1/pipeline/discover",
        json={"platform": "tiktok", "phone": "p", "limit": 1},
    )
    error = _wait_for_event(events, "task_failed")["error"]
    assert "Model refused" in error
    assert all(
        word not in error
        for word in ("CONFIGURED-SECRET", "OTHER-SECRET", "THIRD-SECRET", "PASS")
    )
    assert (
        error == client.get("/api/v1/tasks/" + response.json["task_id"]).json["error"]
    )
