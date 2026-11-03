"""Mock-only task lifecycle regressions: no phone, model or network calls."""

import threading
import time
from types import SimpleNamespace

import pytest
from flask import Flask

import phone_agent.phone_pool as pool_module
from contentswarm_cli import wait_for_task
from phone_agent.api import create_api_blueprint
from phone_agent.phone_pool import PhonePoolManager


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTENTSWARM_STATE_DIR", str(tmp_path))


def terminal(manager, task_id):
    until = time.monotonic() + 3
    while time.monotonic() < until:
        status = manager.get_task_status(task_id)
        if status["status"] not in ("pending", "running"):
            return status
        time.sleep(0.005)
    raise AssertionError(manager.get_task_status(task_id))


def manager_with_agent(monkeypatch, run, **kwargs):
    class Agent:
        def __init__(self, **options):
            self.options = options

        def run(self, task):
            return run(self, task)

    monkeypatch.setattr(pool_module, "PhoneAgent", Agent)
    manager = PhonePoolManager(**kwargs)
    manager.add_phone("p", "serial")
    return manager


def test_agent_failure_reaches_failed_queue(monkeypatch):
    def fail(*_):
        raise RuntimeError("Model error: mock timeout")

    manager = manager_with_agent(monkeypatch, fail)
    try:
        status = terminal(manager, manager.async_run("p", "Open Settings"))
        assert status["status"] == "failed"
        assert "mock timeout" in status["error"]
    finally:
        manager.shutdown()


def test_failed_learning_never_saves_empty_flow(monkeypatch, tmp_path):
    manager = manager_with_agent(monkeypatch, lambda *_: "done")
    try:
        status = terminal(
            manager, manager.async_learn("p", "Open Settings", "empty", str(tmp_path))
        )
        assert status["status"] == "failed"
        assert not (tmp_path / "empty.json").exists()
    finally:
        manager.shutdown()


def test_shutdown_cancels_queued_work(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    seen = []

    def run(agent, task):
        seen.append(task)
        entered.set()
        release.wait(2)
        return "done"

    manager = manager_with_agent(monkeypatch, run, max_parallel=1)
    first = manager.async_run("p", "first")
    assert entered.wait(2)
    second = manager.async_run("p", "second")
    try:
        manager.shutdown()
    finally:
        release.set()
    assert terminal(manager, second)["status"] == "cancelled"
    terminal(manager, first)
    assert seen == ["first"]


def test_running_cancel_keeps_phone_locked_until_agent_stops(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def run(agent, task):
        entered.set()
        release.wait(2)
        agent.options["stop_check"]()
        raise AssertionError("cancel must stop the next action")

    events = []
    manager = manager_with_agent(monkeypatch, run, event_callback=events.append)
    task_id = manager.async_run("p", "Open Settings")
    try:
        assert entered.wait(2)
        response = manager.cancel_task(task_id)
        assert response["status"] == "running" and response["cancel_requested"]
        with pytest.raises(RuntimeError, match="busy"):
            with manager.phone_operation("p"):
                pass
        release.set()
        assert terminal(manager, task_id)["status"] == "cancelled"
        assert any(e.get("status") == "cancelled" for e in events)
        with manager.phone_operation("p"):
            pass
    finally:
        release.set()
        manager.shutdown()


def test_deadline_stops_before_followup_action(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def run(agent, task):
        entered.set()
        release.wait(2)
        agent.options["stop_check"]()
        raise AssertionError("deadline must stop the next action")

    manager = manager_with_agent(monkeypatch, run, task_timeout=30)
    task_id = manager.async_run("p", "Open Settings")
    try:
        assert entered.wait(2)
        manager._controls[task_id].deadline = 0
        release.set()
        status = terminal(manager, task_id)
        assert status["status"] == "timeout"
        assert "deadline" in status["error"].lower()
    finally:
        release.set()
        manager.shutdown()


def test_cli_cancelled_status_returns_without_polling(monkeypatch):
    monkeypatch.setattr(
        "contentswarm_cli.time.sleep",
        lambda _: pytest.fail("cancelled must be terminal"),
    )
    result = wait_for_task(
        SimpleNamespace(get=lambda _: {"status": "cancelled"}), "id", 1
    )
    assert result["status"] == "cancelled"


def test_api_preserves_pool_callback_and_forwards_terminal_events(monkeypatch):
    previous, emitted = [], []
    manager = manager_with_agent(
        monkeypatch, lambda *_: "Settings visible", event_callback=previous.append
    )
    socket = SimpleNamespace(emit=lambda _name, event, **_: emitted.append(event))
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint({"phone_manager": manager, "socketio": socket}),
        url_prefix="/api/v1",
    )
    try:
        result = app.test_client().post(
            "/api/v1/phones/p/task", json={"task": "Open Settings"}
        )
        assert result.status_code == 202
        status = terminal(manager, result.json["task_id"])
        assert (
            status["outcome_verified"] is False
        )  # Agent/input success is not independent proof.
        assert any(e["event"] == "task_completed" for e in previous)
        assert any(
            e["event"] == "task_completed" and e["task_id"] == status["task_id"]
            for e in emitted
        )
    finally:
        manager.shutdown()


@pytest.mark.parametrize("fails", [False, True])
def test_pipeline_discovery_outcome_is_pollable(fails):
    def discover(*_):
        if fails:
            raise RuntimeError("mock discovery failed")
        return [
            SimpleNamespace(
                title="Example",
                url="https://example.test/",
                views=1,
                engagement=2,
                hashtags=[],
            )
        ]

    automation = SimpleNamespace(discover_trending=discover)
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint({"automation": automation}), url_prefix="/api/v1"
    )
    client = app.test_client()
    response = client.post(
        "/api/v1/pipeline/discover",
        json={"platform": "tiktok", "phone": "p", "limit": 1},
    )
    assert response.status_code == 202
    assert "task_id" in response.json
    route = "/api/v1/tasks/" + response.json["task_id"]
    until = time.monotonic() + 2
    while time.monotonic() < until:
        status = client.get(route).json
        if status["status"] in ("completed", "failed"):
            break
    assert status["status"] == ("failed" if fails else "completed")
    assert (
        ("mock discovery failed" in status["error"])
        if fails
        else status["result"][0]["title"] == "Example"
    )


def test_cancel_api_requires_confirmation_and_does_not_release_running_phone(
    monkeypatch,
):
    entered, release = threading.Event(), threading.Event()

    def run(agent, task):
        entered.set()
        release.wait(2)
        agent.options["stop_check"]()

    manager = manager_with_agent(monkeypatch, run)
    app = Flask(__name__)
    app.register_blueprint(
        create_api_blueprint({"phone_manager": manager}), url_prefix="/api/v1"
    )
    client = app.test_client()
    task_id = manager.async_run("p", "Open Settings")
    try:
        assert entered.wait(2)
        route = "/api/v1/tasks/" + task_id + "/cancel"
        assert client.post(route, json={}).status_code == 409
        response = client.post(route, json={"confirm": True})
        assert response.status_code == 200
        assert (
            response.json["cancel_requested"] and response.json["status"] == "running"
        )
        release.set()
        assert terminal(manager, task_id)["status"] == "cancelled"
        assert client.post(route, json={"confirm": True}).status_code == 409
    finally:
        release.set()
        manager.shutdown()


def test_cli_run_exits_nonzero_for_cancelled_task(monkeypatch):
    from contentswarm_cli import build_parser, run_command

    args = build_parser().parse_args(["run", "p", "Open Settings", "--wait"])
    client = SimpleNamespace(
        post=lambda *_: {"task_id": "id"}, get=lambda _: {"status": "cancelled"}
    )
    with pytest.raises(SystemExit) as caught:
        run_command(args, client)
    assert caught.value.code == 1


@pytest.mark.parametrize("action", ["Call_API", "Interact"])
def test_missing_capabilities_do_not_claim_success(action):
    from phone_agent.actions.handler import ActionHandler, do

    result = ActionHandler().execute(do(action=action), 100, 100)
    assert result.should_finish and not result.success
