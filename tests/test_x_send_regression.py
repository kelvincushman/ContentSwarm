"""Offline regressions: no device, network, model, or social send calls."""

import pytest
from test_social_delivery import FEED, REVIEW, Client, composer, node, post

from social_delivery import x_post, x_published


def test_post_accepts_unique_enabled_text_label_for_final_commit():
    typed = composer("Approved text")
    typed[-1] = node(text="Post")  # Android may name a control via text, not desc.
    client = Client([FEED, composer(), typed, typed, post()])
    x_post(client, REVIEW)
    commits = [
        data
        for _, data in client.calls
        if data.get("action") == "tap" and data.get("text") == "Post"
    ]
    assert len(commits) == 1
    assert client.calls[-1][0].endswith("/complete")


def test_precommit_error_is_identified_as_not_sent():
    from social_delivery import NotSent

    class BrokenClock(Client):
        def get(self, route):
            if route.endswith("/clock"):
                raise ValueError("Phone clock unavailable")
            return super().get(route)

    client = BrokenClock()
    with pytest.raises(NotSent, match="timestamp boundary.*Phone clock unavailable"):
        x_post(client, REVIEW)
    assert client.post_taps == 1  # Entry only; body reached composer, no commit.


def test_publication_proof_rejects_a_still_open_composer():
    elements = [node(parent=None)] + [
        dict(e, parent_index=1 if e["parent_index"] == 0 else 0) for e in post()
    ]
    elements.append(node("Approved text", cls="android.widget.EditText"))
    assert not x_published(elements, "@owner", "Approved text", 2)


@pytest.mark.parametrize(
    "error",
    [TimeoutError("response lost"), ValueError("Final account/body check failed")],
)
def test_worker_surfaces_delivery_error_without_retry(monkeypatch, error):
    import tempfile
    from pathlib import Path

    import social_worker
    from phone_agent.review_queue import ReviewQueue

    with tempfile.TemporaryDirectory() as root:
        queue = ReviewQueue(Path(root) / "reviews.db")
        item = queue.create(
            dict(
                REVIEW,
                account_id="account",
                source_url="https://x.com/",
                humanizer_version="test",
            )
        )
        item = queue.update(item["id"], "approve", {"revision": item["revision"]})
        profile = dict(delivery_adapter="x-accessibility-v1", phones=["phone"])

        class ClaimClient:
            api_url = "http://test/api/v1"
            headers = {"Authorization": "Bearer secret"}

            def get(self, route):
                return {"account": profile}

            def post(self, route, data):
                return queue.update(item["id"], "claim", data)

        class DeliveryClient:
            def __init__(self, *args):
                self.headers = {}

            def get(self, route):
                return {"reviews": queue.list()}

            def post(self, route, data):
                return queue.update(
                    item["id"],
                    route.rsplit("/", 1)[-1],
                    dict(data, lease_token=self.headers["X-ContentSwarm-Lease"]),
                )

        attempted = []

        def broken(*args):
            attempted.append(True)
            raise error

        monkeypatch.setattr(social_worker, "Client", DeliveryClient)
        monkeypatch.setattr("social_delivery.x_post", broken)
        social_worker.deliver(ClaimClient(), item)
        result = queue.list()[0]
        assert result["status"] == "uncertain"
        assert type(error).__name__ in result["evidence"]
        assert str(error) in result["evidence"]
        assert result["reply"] == REVIEW["reply"]
        for action in ("claim", "approve"):
            with pytest.raises(ValueError):
                queue.update(item["id"], action, {"revision": result["revision"]})
        assert len(attempted) == 1


@pytest.mark.parametrize(
    "controls",
    [
        [],
        [dict(node(desc="Post"), enabled=False)],
        [node(desc="Post"), node(text="Post")],
    ],
)
def test_missing_disabled_or_ambiguous_commit_control_stops_before_send(controls):
    from social_delivery import NotSent

    typed = composer("Approved text")[:-1] + controls
    client = Client([FEED, composer(), typed])
    with pytest.raises(NotSent, match="one enabled X Post control"):
        x_post(client, REVIEW)
    assert client.post_taps == 1
    assert not any(route.endswith("/complete") for route, _ in client.calls)


def test_successful_tap_with_open_composer_is_not_a_success_or_retried(monkeypatch):
    monkeypatch.setattr("social_delivery.time.sleep", lambda _: None)
    client = Client(
        [
            FEED,
            composer(),
            composer("Approved text"),
            composer("Approved text"),
            composer("Approved text"),
        ]
    )
    with pytest.raises(ValueError, match="composer remained open"):
        x_post(client, REVIEW)
    assert client.post_taps == 2
    assert not any(route.endswith("/complete") for route, _ in client.calls)
    assert not any(data.get("action") == "open_url" for _, data in client.calls)


def test_error_evidence_redacts_copy_and_credentials():
    from types import SimpleNamespace

    from social_worker import delivery_error

    client = SimpleNamespace(
        headers={
            "Authorization": "Bearer api-secret",
            "X-ContentSwarm-Lease": "lease-secret",
        }
    )
    message = "Rejected Bearer api-secret / api-secret / lease-secret / Approved text"
    detail = delivery_error(ValueError(message), client, REVIEW)
    assert "ValueError: Rejected" in detail
    for secret in ("api-secret", "lease-secret", "Approved text"):
        assert secret not in detail


def test_uncertain_send_needs_owner_inspection_before_retry(monkeypatch, tmp_path):
    from flask import Flask

    from dashboard.console import install_console
    from phone_agent.api import create_api_blueprint
    from phone_agent.review_queue import ReviewQueue

    monkeypatch.setenv("CONTENTSWARM_API_TOKEN", "agent-token")
    monkeypatch.setenv("CONTENTSWARM_CONSOLE_TOKEN", "owner-token")
    monkeypatch.setenv("CONTENTSWARM_STATE_DIR", str(tmp_path))
    queue = ReviewQueue(tmp_path / "reviews.sqlite3")
    item = queue.create(
        dict(REVIEW, source_url="https://x.com/", humanizer_version="test")
    )
    app = Flask(__name__)
    install_console(app)
    app.register_blueprint(create_api_blueprint({}), url_prefix="/api/v1")
    agent, owner = app.test_client(), app.test_client()
    bearer = {"Authorization": "Bearer agent-token"}
    route = f"/api/v1/reviews/{item['id']}"
    assert (
        agent.post(route + "/approve", headers=bearer, json={"revision": 1}).status_code
        == 403
    )
    csrf = owner.post("/api/console/login", json={"token": "owner-token"}).json["csrf"]
    approved = owner.post(
        route + "/approve", headers={"X-CSRF-Token": csrf}, json={"revision": 1}
    ).json
    claim = agent.post(
        route + "/claim", headers=bearer, json={"revision": approved["revision"]}
    ).json
    uncertain = agent.post(
        route + "/uncertain",
        headers=dict(bearer, **{"X-ContentSwarm-Lease": claim["lease_token"]}),
        json={
            "revision": claim["revision"],
            "evidence": "Post response lost; check timeline.",
        },
    ).json
    assert uncertain["status"] == "uncertain"
    for action in ("claim", "approve", "confirm", "retry"):
        response = agent.post(
            route + "/" + action,
            headers=bearer,
            json={"revision": uncertain["revision"]},
        )
        assert response.status_code in (403, 409)
    assert (
        owner.post(
            route + "/retry", json={"revision": uncertain["revision"]}
        ).status_code
        == 403
    )
    response = owner.post(
        route + "/retry",
        headers={"X-CSRF-Token": csrf},
        json={"revision": uncertain["revision"]},
    )
    assert response.status_code == 200
    assert response.json["status"] == "approved"
