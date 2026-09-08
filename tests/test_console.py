from flask import Flask, jsonify
import pytest
from dashboard.console import install_console, transport_allowed
from phone_agent.api import create_api_blueprint


@pytest.fixture(autouse=True)
def owner_credential(monkeypatch):
    monkeypatch.setenv("CONTENTSWARM_CONSOLE_TOKEN", "owner-token")


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
    assert client.post("/api/console/login",json={"token":"test-token"}).status_code == 401
    csrf=client.post("/api/console/login",json={"token":"owner-token"}).json["csrf"]
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
    response = app.test_client().post("/api/console/login", json={"token": "owner-token"}, base_url="https://console.example")
    assert "; Secure;" in response.headers["Set-Cookie"]
    monkeypatch.setenv("CONTENTSWARM_COOKIE_SECURE", "0")
    monkeypatch.setenv("CONTENTSWARM_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="loopback"):
        install_console(Flask(__name__))
    monkeypatch.delenv("CONTENTSWARM_HOST", raising=False)
    local = Flask(__name__)
    install_console(local)
    response = local.test_client().post("/api/console/login", json={"token": "owner-token"})
    assert "; Secure;" not in response.headers["Set-Cookie"]


def test_remote_plaintext_refused_and_explicit_proxy_trust(monkeypatch):
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "test-token")
    monkeypatch.setenv("CONTENTSWARM_HOST", "127.0.0.1")
    monkeypatch.delenv("CONTENTSWARM_TRUST_PROXY", raising=False)
    app = Flask(__name__)
    install_console(app)
    assert app.test_client().post("/api/console/login", base_url="http://remote.example", json={"token": "test-token"}, headers={"X-Forwarded-Proto": "https"}).status_code == 403
    monkeypatch.setenv("CONTENTSWARM_TRUST_PROXY", "1")
    proxied = Flask(__name__)
    install_console(proxied)
    assert proxied.test_client().post("/api/console/login", base_url="http://remote.example", json={"token": "owner-token"}, headers={"X-Forwarded-Proto": "https"}).status_code == 200


def test_agent_cannot_make_owner_decisions(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "agent-token")
    monkeypatch.setenv("CONTENTSWARM_STATE_DIR", str(tmp_path))
    app = Flask(__name__)
    install_console(app)
    app.register_blueprint(create_api_blueprint({"phone_manager": SimpleNamespace(phones={"phone": SimpleNamespace(device_id="test")})}), url_prefix="/api/v1")
    agent = app.test_client()
    bearer = {"Authorization": "Bearer agent-token"}
    item = agent.post("/api/v1/reviews", headers=bearer, json=dict(platform="x", account="@owner", phone="phone", source_url="https://x.com/test/status/1", author="Reader", original="Hello", reply="Hi", humanizer_version="3.0.0")).json
    route = f"/api/v1/reviews/{item['id']}"
    for action in ("approve", "reject", "edit"):
        assert agent.post(route + "/" + action, headers=bearer, json={"revision": 1, "reply": "Changed"}).status_code == 403
    assert agent.post("/api/console/login", json={"token": "agent-token"}).status_code == 401
    owner = app.test_client()
    csrf = owner.post("/api/console/login", json={"token": "owner-token"}).json["csrf"]
    assert owner.post(route + "/approve", json={"revision": 1}).status_code == 403
    approved = owner.post(route + "/approve", headers={"X-CSRF-Token": csrf}, json={"revision": 1})
    assert approved.status_code == 200
    assert agent.post(route + "/claim", headers=bearer, json={"revision": approved.json["revision"]}).status_code == 200


def test_owner_secret_cannot_reuse_agent_secret(monkeypatch):
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "owner-token")
    with pytest.raises(RuntimeError, match="must differ"):
        install_console(Flask(__name__))


def test_transport_check_covers_socket_paths():
    app = Flask(__name__)
    for base, allowed in (("http://remote.example", False), ("https://remote.example", True), ("http://127.0.0.1:5055", True)):
        with app.test_request_context("/socket.io/", base_url=base):
            assert transport_allowed() is allowed
