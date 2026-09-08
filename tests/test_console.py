from flask import Flask, jsonify
import pytest
from dashboard.console import install_console
from phone_agent.api import create_api_blueprint


def test_console_login_csrf_and_legacy_auth(monkeypatch):
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN","test-token")
    app=Flask(__name__)
    app.add_url_rule("/", "index", lambda:"console")
    app.add_url_rule("/api/legacy", "legacy", lambda:jsonify(ok=True), methods=["GET","POST"])
    install_console(app)
    app.register_blueprint(create_api_blueprint({}),url_prefix="/api/v1")
    client=app.test_client()
    assert client.get("/api/legacy").status_code==401
    assert client.post("/api/console/login",json={"token":"wrong"}).status_code==401
    assert client.post("/api/console/login",json={"token":"test-token"},headers={"Origin":"https://evil.example"}).status_code==403
    csrf=client.post("/api/console/login",json={"token":"test-token"}).json["csrf"]
    assert client.get("/api/legacy").status_code==200
    assert client.post("/api/legacy",json={}).status_code==403
    assert client.post("/api/legacy",json={},headers={"X-CSRF-Token":csrf}).status_code==200
    assert client.get("/api/v1/phones").status_code==503  # authenticated, no hardware manager
    assert client.post("/api/console/logout",json={},headers={"X-CSRF-Token":csrf}).status_code==200
    assert client.get("/api/legacy").status_code==401
    assert client.get("/api/legacy",headers={"Authorization":"Bearer test-token"}).status_code==200


def test_startup_requires_token_and_secure_remote_cookies(monkeypatch):
    monkeypatch.delenv("CONTENTSWARM_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TOKEN is required"):
        install_console(Flask(__name__))
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "test-token")
    monkeypatch.delenv("CONTENTSWARM_COOKIE_SECURE", raising=False)
    app = Flask(__name__)
    install_console(app)
    response = app.test_client().post("/api/console/login", json={"token": "test-token"}, base_url="https://console.example")
    assert "; Secure;" in response.headers["Set-Cookie"]
    monkeypatch.setenv("CONTENTSWARM_COOKIE_SECURE", "0")
    monkeypatch.setenv("CONTENTSWARM_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="loopback"):
        install_console(Flask(__name__))
    monkeypatch.setenv("CONTENTSWARM_HOST", "127.0.0.1")
    local = Flask(__name__)
    install_console(local)
    response = local.test_client().post("/api/console/login", json={"token": "test-token"})
    assert "; Secure;" not in response.headers["Set-Cookie"]
