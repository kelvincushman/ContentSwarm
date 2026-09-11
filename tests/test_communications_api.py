from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from flask import Flask

from phone_agent.api import create_api_blueprint
from phone_agent import bridge


@pytest.fixture
def client():
    phone = SimpleNamespace(device_id="serial-1", description="test", tags=[])
    pm = SimpleNamespace(
        phones={"primary": phone}, current_phone="primary",
        scan_and_add_devices=lambda: 0,
        check_connections=lambda: {"primary": True},
        phone_operation=lambda _phone: nullcontext(),
    )
    app = Flask(__name__)
    app.register_blueprint(create_api_blueprint({"phone_manager": pm}), url_prefix="/api/v1")
    return app.test_client()


def test_discover_returns_persisted_phone_inventory(client):
    response = client.post("/api/v1/phones/discover")
    assert response.status_code == 200
    assert response.get_json() == {
        "added": 0,
        "phones": [{"connected": True, "device_id": "serial-1", "name": "primary"}],
        "total": 1,
    }


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
        json={"action": "tap", "text": "Continue", "confirm": True},
    )
    assert response.status_code == 200
    assert response.get_json()["phone"] == "primary"
    assert seen == {"device": "serial-1", "action": "tap", "params": {"text": "Continue"}}


def test_every_tap_requires_confirmation_even_neutral_text(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "semantic_action",
        lambda *_args, **_kwargs: pytest.fail("bridge must not run before confirmation"),
    )
    response = client.post(
        "/api/v1/phones/primary/action",
        json={"action": "tap", "text": "Continue"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize("key", ["ENTER", "DPAD_CENTER", "BACK"])
def test_every_key_requires_confirmation(client, monkeypatch, key):
    monkeypatch.setattr(
        bridge, "semantic_action",
        lambda *_args, **_kwargs: pytest.fail("bridge must not run before confirmation"),
    )
    response = client.post(
        "/api/v1/phones/primary/action", json={"action": "key", "key": key},
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
        lambda device, channel, recipient, body, label: {
            "success": True, "channel": channel, "recipient": recipient,
            "characters": len(body), "sent": False,
            "recipient_verified": True, "body_verified": True,
        },
    )
    monkeypatch.setattr(
        bridge, "send_composed_message",
        lambda device, channel, recipient, body, label: {
            "success": True, "channel": channel, "sent": True,
            "verified": True, "verification": "composer-cleared",
        },
    )
    compose = client.post(
        "/api/v1/phones/primary/communications/compose",
        json={"channel": "sms", "recipient": "+447700900123", "body": "hello"},
    )
    assert compose.status_code == 200
    assert compose.get_json()["sent"] is False
    prepared_token = compose.get_json()["prepared_token"]

    response = client.post(
        "/api/v1/phones/primary/communications/send",
        json={
            "channel": "sms", "recipient": "+447700900123",
            "expected_body": "hello", "prepared_token": prepared_token,
            "confirm": True,
        },
    )
    assert response.status_code == 200
    assert response.get_json()["verified"] is True

    reused = client.post(
        "/api/v1/phones/primary/communications/send",
        json={
            "channel": "sms", "recipient": "+447700900123",
            "expected_body": "hello", "prepared_token": prepared_token,
            "confirm": True,
        },
    )
    assert reused.status_code == 409


def test_prepared_token_is_bound_to_recipient(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "compose_message",
        lambda device, channel, recipient, body, label: {
            "success": True, "channel": channel, "recipient": recipient,
            "characters": len(body), "sent": False,
            "recipient_verified": True, "body_verified": True,
        },
    )
    monkeypatch.setattr(
        bridge, "send_composed_message",
        lambda *_args: pytest.fail("mismatched recipient must never reach bridge send"),
    )
    compose = client.post(
        "/api/v1/phones/primary/communications/compose",
        json={"channel": "sms", "recipient": "+447700900123", "body": "hello"},
    ).get_json()
    response = client.post(
        "/api/v1/phones/primary/communications/send",
        json={
            "channel": "sms", "recipient": "+447700900999",
            "expected_body": "hello", "prepared_token": compose["prepared_token"],
            "confirm": True,
        },
    )
    assert response.status_code == 409


def test_new_compose_invalidates_previous_prepared_token(client, monkeypatch):
    monkeypatch.setattr(
        bridge, "compose_message",
        lambda device, channel, recipient, body, label: {
            "success": True, "channel": channel, "recipient": recipient,
            "characters": len(body), "sent": False,
            "recipient_verified": True, "body_verified": True,
        },
    )
    monkeypatch.setattr(
        bridge, "send_composed_message",
        lambda *_args: pytest.fail("invalidated token must not reach bridge send"),
    )
    first = client.post(
        "/api/v1/phones/primary/communications/compose",
        json={"channel": "sms", "recipient": "+447700900123", "body": "first"},
    ).get_json()
    client.post(
        "/api/v1/phones/primary/communications/compose",
        json={"channel": "sms", "recipient": "+447700900999", "body": "second"},
    )
    response = client.post(
        "/api/v1/phones/primary/communications/send",
        json={
            "channel": "sms", "recipient": "+447700900123", "expected_body": "first",
            "prepared_token": first["prepared_token"], "confirm": True,
        },
    )
    assert response.status_code == 409


def test_phone_clock_uses_requested_device_and_handles_failure(client,monkeypatch):
    def clock(device):
        assert device=='serial-1'
        return dict(iso='2026-09-11T20:15:00+01:00',epoch=1789154100)
    monkeypatch.setattr(bridge,'device_clock',clock)
    assert client.get('/api/v1/phones/primary/clock').status_code==200
    assert client.get('/api/v1/phones/missing/clock').status_code==404
    monkeypatch.setattr(bridge,'device_clock',lambda _:(_ for _ in ()).throw(RuntimeError('internal')))
    assert client.get('/api/v1/phones/primary/clock').status_code==503
