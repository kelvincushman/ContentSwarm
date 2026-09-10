from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from phone_agent.social import SocialStore, next_time
from phone_agent.review_queue import ReviewQueue


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def test_dst_month_end_and_interval():
    spec = dict(kind="daily", timezone="Europe/London", time="01:30")
    # 01:30 does not exist on the spring transition day.
    assert next_time(spec, stamp("2026-03-29T00:00:00+00:00")) == stamp("2026-03-30T01:30:00+01:00")
    # Do not repeat a folded wall time in autumn.
    assert next_time(spec, stamp("2026-10-25T01:31:00+01:00")) == stamp("2026-10-26T01:30:00+00:00")
    assert next_time(dict(kind="monthly", timezone="UTC", time="09:00", day=31), stamp("2026-04-01T00:00:00+00:00")) == stamp("2026-05-31T09:00:00+00:00")
    assert next_time(dict(kind="interval", minutes=60, anchor=100), 100000) == 100900


def test_account_scope_and_immutable_identity(tmp_path):
    store = SocialStore(tmp_path / "social.db")
    a = store.account(dict(name="Personal", platform="x", handle="@one", soul="Plain", phones=["p1", "p2"]))
    b = store.account(dict(name="Business", platform="x", handle="@two", soul="Practical", phones=["p2"]))
    store.remember(a["id"], dict(text="Private memory", source="note:one"), True)
    assert not store.context(b["id"])["memories"]
    assert store.context(a["id"])["memories"][0]["trusted"]
    with pytest.raises(ValueError, match="separate profile"):
        store.account(dict(a, handle="@changed"))


def test_tick_is_atomic_coalesces_and_edit_cancels_unstarted(tmp_path):
    store = SocialStore(tmp_path / "social.db")
    a = store.account(dict(name="A", platform="x", handle="@a", soul="Plain", phones=["p"]))
    schedule = store.schedule(dict(account_id=a["id"], prompt="Draft something", spec=dict(kind="interval", minutes=1)), now=0)
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: store.tick(1000), range(4)))
    assert len(store.list("jobs")) == 1
    store.tick(2000)
    assert len(store.list("jobs")) == 1
    updated = store.schedule(dict(schedule, prompt="New brief"), now=2000)
    assert store.list("jobs")[0]["status"] == "cancelled"
    store.tick(2100)
    with ThreadPoolExecutor(4) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(4)))
    assert len([j for j in claims if j]) == 1
    store.pause(updated["id"], updated["revision"])
    assert store.list("jobs")[0]["status"] == "running"
    # Crash recovery never silently reclaims an in-flight model request.
    assert SocialStore(tmp_path / "social.db").claim() is None


def test_publish_time_and_edit_invalidate_approval(tmp_path):
    queue = ReviewQueue(tmp_path / "review.db")
    r = queue.create(dict(kind="post", platform="x", account="@a", phone="p", source_url="https://x.com/", reply="A post", humanizer_version="3.0.0"))
    r = queue.update(r["id"], "approve", r)
    r = queue.update(r["id"], "schedule", dict(r, at="2099-01-01T10:00:00+00:00"))
    with pytest.raises(ValueError, match="not arrived"):
        queue.update(r["id"], "claim", r)
    r = queue.update(r["id"], "edit", dict(r, reply="Changed post"))
    assert r["status"] == "pending" and "publish_at" not in r
    with pytest.raises(ValueError, match="approved"):
        queue.update(r["id"], "claim", r)


def test_api_owner_boundary_and_untrusted_capture(tmp_path, monkeypatch):
    from flask import Flask
    from dashboard.console import install_console
    from phone_agent.api import create_api_blueprint
    monkeypatch.setenv("CONTENTSWARM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "agent")
    monkeypatch.setenv("CONTENTSWARM_CONSOLE_TOKEN", "owner")
    app = Flask(__name__)
    install_console(app)
    app.register_blueprint(create_api_blueprint({}), url_prefix="/api/v1")
    agent, owner = app.test_client(), app.test_client()
    headers = {"Authorization": "Bearer agent"}
    csrf = owner.post("/api/console/login", json={"token": "owner"}).json["csrf"]
    data = dict(name="A", platform="x", handle="@a", soul="Plain", phones=[])
    assert agent.post("/api/v1/social/accounts", json=data, headers=headers).status_code == 403
    account = owner.post("/api/v1/social/accounts", json=data, headers={"X-CSRF-Token": csrf}).json
    result = agent.post(f"/api/v1/social/accounts/{account['id']}/memory", json=dict(text="They said this", source="thread", trusted=True), headers=headers)
    assert result.status_code == 201 and result.json["trusted"] is False


def test_delivery_reserves_phone_across_requests(tmp_path, monkeypatch):
    import threading
    from flask import Flask
    from phone_agent.api import create_api_blueprint
    from phone_agent.phone_pool import PhonePoolManager
    from types import SimpleNamespace
    monkeypatch.setenv("CONTENTSWARM_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "agent")
    pm = PhonePoolManager()
    pm.phones = {"p1": SimpleNamespace(device_id="serial1"), "p2": SimpleNamespace(device_id="serial2")}
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(create_api_blueprint({"phone_manager": pm}), url_prefix="/api/v1")
    q = ReviewQueue(tmp_path / "reviews.sqlite3")
    r = q.create(dict(platform="x", account="@a", phone="p1", source_url="https://x.com/", author="a", original="Hi", reply="Hi", humanizer_version="3"))
    r = q.update(r["id"], "approve", r)
    client = app.test_client()
    bearer = {"Authorization": "Bearer agent"}
    try:
        with pm.phone_operation("p1"):
            assert client.post(f"/api/v1/reviews/{r['id']}/claim", json=r, headers=bearer).status_code == 409
        claimed = client.post(f"/api/v1/reviews/{r['id']}/claim", json=r, headers=bearer)
        assert claimed.status_code == 200
        with pytest.raises(RuntimeError, match="busy"):
            with pm.phone_operation("p1"):
                pass
        with pm.phone_operation("p2"):
            pass
        # Knowing a public review id cannot impersonate its lease holder.
        with app.test_request_context(headers=dict(bearer, **{"X-ContentSwarm-Review": r["id"]})):
            with pytest.raises(RuntimeError, match="lease"):
                with pm.phone_operation("p1"):
                    pass
        assert "lease_token" not in q.list()[0] and "lease_hash" not in q.list()[0]
        headers = dict(bearer, **{"X-ContentSwarm-Review": r["id"], "X-ContentSwarm-Lease": claimed.json["lease_token"]})
        with app.test_request_context(headers=headers):
            with pm.phone_operation("p1"):
                pass
            with pytest.raises(RuntimeError, match="cannot control"):
                with pm.phone_operation("p2"):
                    pass
        outcome = client.post(f"/api/v1/reviews/{r['id']}/uncertain", json=dict(claimed.json, evidence="Stopped before verification"), headers=headers)
        assert outcome.status_code == 200
        with pm.phone_operation("p1"):
            pass
    finally:
        pm.shutdown()


def test_delivery_does_not_trust_mentions_or_stale_account_indicator(monkeypatch):
    import social_worker
    indicator = {"id": "test:id/composer_account", "text": "@owner"}
    review = dict(id="r", revision=3, kind="post", platform="x", phone="p", account="@owner", reply="Approved text")

    class Client:
        def __init__(self, screens):
            self.screens = iter(screens)
            self.posts = []
        def get(self, path):
            return {"elements": next(self.screens)}
        def post(self, path, data):
            self.posts.append((path, data))

    monkeypatch.setattr(social_worker, "choose_action", lambda *args: ({"action": "type"}, 0.01))
    client = Client([[{"id": "test:id/post_text", "text": "@owner"}]])
    with pytest.raises(ValueError, match="identity"):
        social_worker.delivery_loop(client, review, indicator)
    assert len(client.posts) == 1  # App launch only; no text entered.
    actions = iter([{"action": "type"}, {"action": "send", "selector": {"text": "Post"}}])
    monkeypatch.setattr(social_worker, "choose_action", lambda *args: (next(actions), 0.01))
    client = Client([[indicator], [{"text": "@other", "id": indicator["id"]}, {"text": "Approved text"}, {"text": "Post"}]])
    with pytest.raises(ValueError, match="preconditions"):
        social_worker.delivery_loop(client, review, indicator)
    assert not any(data.get("action") == "tap" for _, data in client.posts)


def test_model_receives_no_service_secrets(monkeypatch):
    from social_worker import model_environment
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "secret")
    monkeypatch.setenv("OTHER_SECRET", "also-secret")
    env = model_environment()
    assert "CONTENTSWARM_API_TOKEN" not in env and "OTHER_SECRET" not in env


def test_calibrated_post_navigation_send_and_independent_finish(monkeypatch):
    import social_worker
    indicator = dict(id="app:id/account", text="@owner", compose_id="app:id/open_composer")
    review = dict(id="r", revision=3, kind="post", platform="x", phone="p", account="@owner", reply="Approved body")
    screens = iter([
        [{"id": "app:id/open_composer", "text": "Post"}],
        [indicator],
        [indicator, {"id": "app:id/editor", "class": "EditText", "text": "Approved body"}, {"id": "app:id/send", "text": "Post"}],
        [{"id": "app:id/published", "class": "TextView", "text": "Approved body"}],
    ])
    actions = iter([{"action": "tap", "selector": {"id": "app:id/open_composer"}}, {"action": "type", "text": "Ignored model rewrite"},
                    {"action": "send", "selector": {"id": "app:id/send"}}, {"action": "finish", "evidence": "Published body in thread"}])
    monkeypatch.setattr(social_worker, "choose_action", lambda *args: (next(actions), 0.01))
    calls = []
    class Client:
        def get(self, path):
            return {"elements": next(screens)}
        def post(self, path, data):
            calls.append((path, data))
    social_worker.delivery_loop(Client(), review, indicator)
    assert [body["text"] for _, body in calls if body.get("action") == "type"] == ["Approved body"]
    assert sum(body.get("id") == "app:id/send" for _, body in calls) == 1
    assert calls[-1][0] == "/reviews/r/complete"
