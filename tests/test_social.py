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


def test_calibration_controls_are_distinct_after_normalization(tmp_path):
    store = SocialStore(tmp_path / "social.db")
    data = dict(name="A", platform="x", handle="@a", soul="Plain", phones=[])
    with pytest.raises(ValueError, match="distinct"):
        store.account(dict(data, delivery_indicator=dict(id="app:id/account", text="@a", compose_id=" app:id/control ", posted_id="app:id/control")))
    saved = store.account(dict(data, delivery_indicator=dict(id=" app:id/account ", text="@a", compose_id="app:id/open", posted_id="app:id/content")))
    assert saved["delivery_indicator"]["id"] == "app:id/account"


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
    indicator = dict(id="app:id/account", text="@owner", compose_id="app:id/open_composer", posted_id="app:id/published")
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


@pytest.mark.parametrize("wrong_editor", [True, False])
def test_short_body_cannot_match_toolbar_or_unrelated_content(monkeypatch, wrong_editor):
    import social_worker
    indicator = dict(id="app:id/account", text="@owner", posted_id="app:id/published")
    review = dict(id="r", revision=3, kind="post", platform="x", phone="p", account="@owner", reply="Post")
    screens = iter([[indicator], [indicator, {"id":"editor", "class":"EditText", "text":"Post extra" if wrong_editor else "Post"}, {"id":"send", "text":"Post"}],
                    [{"id":"toolbar", "class":"TextView", "text":"Post"}]])
    actions = iter([{"action":"type"}, {"action":"send", "selector":{"id":"send"}}, {"action":"finish", "evidence":"I see Post"}])
    monkeypatch.setattr(social_worker, "choose_action", lambda *args: (next(actions), 0.01))
    calls=[]
    class Client:
        def get(self, path): return {"elements": next(screens)}
        def post(self, path, data): calls.append((path,data))
    with pytest.raises(ValueError, match="preconditions|delivery evidence"):
        social_worker.delivery_loop(Client(), review, indicator)
    assert not any(path.endswith("/complete") for path,_ in calls)


def test_reply_jobs_keep_source_through_schedule_edit_and_claim(tmp_path):
    store = SocialStore(tmp_path / "social.db")
    account = store.account(dict(name="A", platform="x", handle="@a", soul="Plain", phones=["p"]))
    target = dict(kind="reply", source_url="https://x.com/reader/status/123", author="Reader", original="Does it run locally?")
    job = store.enqueue(account["id"], "Explain the local part", target)
    assert all(job[k] == v for k, v in target.items())
    assert store.claim()["source_url"] == target["source_url"]
    schedule = store.schedule(dict(account_id=account["id"], prompt="Draft a response", spec=dict(kind="interval", minutes=60), **target), now=0)
    first = store.tick(3601)[0]
    updated = store.schedule(dict(schedule, original="Does it run offline?"), now=3602)
    assert store.get("jobs", first["id"])["status"] == "cancelled"
    next_job = store.tick(updated["next_at"])[0]
    assert next_job["original"] == "Does it run offline?"
    assert next_job["kind"] == "reply"
    assert store.get("jobs", job["id"])["original"] == target["original"]
    for changes in ({"kind": "send"}, {"source_url": "https://facebook.com/a/posts/1"}, {"source_url": "https://x.com/"}, {"author": ""}, {"original": ""}):
        with pytest.raises(ValueError):
            store.enqueue(account["id"], "Respond", dict(target, **changes))


def test_worker_reply_uses_thread_context_humanizer_and_approval_queue(monkeypatch):
    import json
    from types import SimpleNamespace
    from pathlib import Path
    import social_worker
    account = dict(id="account", platform="x", handle="@owner", phones=["offline", "online"])
    target = dict(kind="reply", author="Reader", original="What does it do?", source_url="https://x.com/reader/status/123")
    job = dict(id="job", account_id="account", prompt="Explain the project", **target)
    calls = []
    class FakeClient:
        def __init__(self, *args): pass
        def get(self, route):
            calls.append(route)
            if route == "/phones":
                return {"phones": [dict(name="offline", connected=False), dict(name="online", connected=True)]}
            assert "thread=https%3A%2F%2Fx.com%2Freader%2Fstatus%2F123" in route
            return dict(account=account, memories=[dict(text="A local tool", trusted=True)])
        def post(self, route, data=None):
            calls.append((route, data))
            if route == "/social/claim": return {"job": job}
            if route == "/reviews": return {"id": "review", "status": "pending"}
            return {}
    def model(command, **kwargs):
        payload = json.loads(kwargs["input"])
        assert payload["target"] == target
        assert payload["context"]["account"] == account
        system = Path(command[command.index("--system-prompt-file") + 1]).read_text()
        assert "target.original" in system and "Humanizer" in system
        assert "CONTENTSWARM_API_TOKEN" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=json.dumps({"result": "It runs the phone controls locally."}))
    monkeypatch.setattr(social_worker, "Client", FakeClient)
    monkeypatch.setattr(social_worker.subprocess, "run", model)
    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "secret")
    monkeypatch.delenv("CONTENTSWARM_DELIVERY_ENABLED", raising=False)
    social_worker.main()
    review = next(data for route, data in (c for c in calls if isinstance(c, tuple)) if route == "/reviews")
    assert all(review[k] == v for k, v in target.items())
    assert review["phone"] == "online"
    assert review["humanizer_version"] == "3.0.0"
    assert calls[-1] == ("/social/jobs/job/finish", {"result": {"review_id": "review"}})
    assert not any("/approve" in str(c) or "/action" in str(c) for c in calls)
