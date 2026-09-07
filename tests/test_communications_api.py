from types import SimpleNamespace

import pytest
from flask import Flask

from phone_agent.api import create_api_blueprint
from phone_agent import bridge


@pytest.fixture
def client():
    phone = SimpleNamespace(device_id="serial-1", description="test", tags=[])
    pm = SimpleNamespace(phones={"primary": phone}, current_phone="primary")
    app = Flask(__name__)
    app.register_blueprint(create_api_blueprint({"phone_manager": pm}), url_prefix="/api/v1")
    return app.test_client()


def test_action_rejects_non_json_and_missing_phone(client):
    response = client.post("/api/v1/phones/primary/action", data="tap")
    assert response.status_code == 415
    response = client.post("/api/v1/phones/missing/action", json={"action": "key", "key": "BACK"})
    assert response.status_code == 404


def test_action_calls_deterministic_bridge(client, monkeypatch):
    seen = {}

    def fake_action(device, action, **params):
        seen.update(device=device, action=action, params=params)
        return {"success": True, "action": action}

    monkeypatch.setattr(bridge, "semantic_action", fake_action)
    response = client.post(
        "/api/v1/phones/primary/action",
        json={"action": "tap", "text": "Continue"},
    )
    assert response.status_code == 200
    assert response.get_json()["phone"] == "primary"
    assert seen == {"device": "serial-1", "action": "tap", "params": {"text": "Continue"}}


def test_sensitive_tap_requires_confirmation(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "semantic_action",
        lambda *_args, **_kwargs: pytest.fail("bridge must not run before confirmation"),
    )
    response = client.post(
        "/api/v1/phones/primary/action",
        json={"action": "tap", "text": "Send"},
    )
    assert response.status_code == 409


def test_send_requires_literal_confirmation(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "send_composed_message",
        lambda *_args: pytest.fail("bridge must not be called without confirmation"),
    )
    response = client.post(
        "/api/v1/phones/primary/communications/send",
        json={"channel": "sms", "expected_body": "hello"},
    )
    assert response.status_code == 409


def test_compose_and_confirmed_send_contract(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "compose_message",
        lambda device, channel, recipient, body: {
            "success": True, "channel": channel, "recipient": recipient,
            "characters": len(body), "sent": False,
        },
    )
    monkeypatch.setattr(
        bridge, "send_composed_message",
        lambda device, channel, body: {
            "success": True, "channel": channel, "sent": True,
            "verified": True, "verification": "composer-cleared",
        },
    )
    response = client.post(
        "/api/v1/phones/primary/communications/compose",
        json={"channel": "sms", "recipient": "+447700900123", "body": "hello"},
    )
    assert response.status_code == 200
    assert response.get_json()["sent"] is False

    response = client.post(
        "/api/v1/phones/primary/communications/send",
        json={"channel": "sms", "expected_body": "hello", "confirm": True},
    )
    assert response.status_code == 200
    assert response.get_json()["verified"] is True
