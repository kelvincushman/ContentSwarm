"""X replies and LinkedIn posts, against screens shaped like the real apps."""

import pytest

import social_delivery
from social_delivery import NotSent, linkedin_post, linkedin_published, x_reply, x_reply_composer


def node(text="", desc="", cls="android.widget.TextView", parent=0, id=""):
    return dict(text=text, desc=desc, id=id, **{"class": cls}, parent_index=parent, enabled=True, bounds=[0, 0, 1080, 2000])


ORIGINAL = "curious whether bolt at 2-bit holds up next to that setup."
BODY = "It holds up better than I expected."
REPLY = dict(id="r", revision=4, platform="x", kind="reply", phone="phone", account="@owner",
             author="@asker", original=ORIGINAL, reply=BODY)

HOME = [node(parent=None), node(desc="Show navigation drawer"), node(desc="Home"), node(desc="Notifications tab")]
MENTIONS = HOME + [node(desc="Mentions"), node(parent=0), node("@asker", parent=5), node("Replying to ﻿@owner﻿", parent=5),
                   node(ORIGINAL, parent=5), node(desc="Reply", parent=5)]


def reply_composer(body="", handle="@owner", original=ORIGINAL, author="@asker"):
    return [node(parent=None), node(author), node(original), node(f"Replying to ﻿{author}﻿"),
            node(desc=f"{handle}, Switch accounts"), node(text=body, cls="android.widget.EditText"), node(desc="Reply")]


def my_reply(age="4s", body=BODY):
    """Our reply on the profile's Replies tab, opened from the profile link."""
    return [node(parent=None), node("@owner"), node(age), node(body), node(desc="Reply"), node(desc="Repost"), node(desc="Like"),
            node(id="UserProfileScreen")]


class Client:
    """Hands out screens in order; records every request."""
    def __init__(self, screens, app="Twitter", package="com.twitter.android"):
        self.screens = list(screens)
        self.calls = []
        self.app, self.package = app, package
        self.clock = 0

    def get(self, route):
        if route.endswith("/clock"):
            self.clock += 1
            return dict(iso="2026-10-21T10:00:59+01:00" if self.clock == 1 else "2026-10-21T10:01:00+01:00")
        if route.endswith("/current_app"):
            return dict(current_app=self.app, package=self.package)
        return dict(elements=self.screens.pop(0) if len(self.screens) > 1 else self.screens[0])

    def post(self, route, data):
        self.calls.append((route, data))
        return {}

    def taps(self, **selector):
        return [d for _, d in self.calls if d.get("action") == "tap" and all(d.get(k) == v for k, v in selector.items())]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(social_delivery.time, "sleep", lambda _: None)


def reply_screens(last=None):
    return [HOME, MENTIONS, reply_composer(), reply_composer(BODY), reply_composer(BODY), last or my_reply()]


def test_reply_targets_the_mention_types_once_and_proves_it():
    client = Client(reply_screens())
    x_reply(client, REPLY)
    assert client.taps(desc="Reply", within=ORIGINAL)
    assert [d["text"] for _, d in client.calls if d.get("action") == "type"] == [BODY]
    assert len(client.taps(desc="Reply")) == 2  # The mention's own Reply, then one send.
    assert client.calls[-1][0] == "/reviews/r/complete"


@pytest.mark.parametrize("composer", [
    reply_composer(handle="@someone_else"),                # Wrong account.
    reply_composer(original="A different comment"),       # Wrong original.
    reply_composer(author="@another"),                     # Wrong author.
    reply_composer("Leftover draft"),                      # Editor not empty.
])
def test_reply_stops_before_sending_on_any_mismatch(composer):
    client = Client([HOME, MENTIONS, composer])
    with pytest.raises(NotSent):
        x_reply(client, REPLY)
    assert len(client.taps(desc="Reply")) == 1  # Only the mention's own Reply control.
    assert not any(route.endswith("/complete") for route, _ in client.calls)


def test_reply_changed_after_typing_is_not_sent():
    client = Client([HOME, MENTIONS, reply_composer(), reply_composer("Something else")])
    with pytest.raises(NotSent):
        x_reply(client, REPLY)
    assert len(client.taps(desc="Reply")) == 1


def test_reply_is_not_attempted_when_the_mention_is_gone():
    client = Client([HOME] + [HOME + [node(desc="Mentions")]] * 5)
    with pytest.raises(NotSent, match="not found"):
        x_reply(client, REPLY)
    assert not client.taps(desc="Reply")
    assert len([d for _, d in client.calls if d.get("action") == "swipe"]) == 3


def test_reply_refuses_an_open_editor_and_loose_handles():
    with pytest.raises(NotSent):
        x_reply(Client([[node(parent=None), node(cls="android.widget.EditText")]]), REPLY)
    with pytest.raises(NotSent):
        x_reply(Client([HOME]), dict(REPLY, author="Asker Name"))
    with pytest.raises(NotSent):
        x_reply(Client([HOME]), dict(REPLY, kind="post"))


def test_unproven_reply_is_left_for_the_owner():
    client = Client(reply_screens(my_reply(age="3d")))
    with pytest.raises(ValueError) as caught:
        x_reply(client, REPLY)
    assert not isinstance(caught.value, NotSent)  # It was sent: never "nothing was posted".
    assert len(client.taps(desc="Reply")) == 2
    assert not any(route.endswith("/complete") for route, _ in client.calls)


def test_composer_proof_needs_the_original_outside_the_editor():
    screen = reply_composer(ORIGINAL)
    screen[2]["text"] = ""
    assert not x_reply_composer(screen, "@owner", "@asker", ORIGINAL)
    assert x_reply_composer(reply_composer(), "@owner", "@asker", ORIGINAL)


# LinkedIn

NAME = "Owner Name"
POST = dict(id="p", revision=2, platform="linkedin", kind="post", phone="phone", account=NAME, reply="Shipping notes.")
LI = "com.linkedin.android:id/"
FEED = [node(parent=None), node(id=LI + "tab_feed", desc="Home 1 of 5"), node(id=LI + "home_post", desc="Post"),
        node(id=LI + "me_launcher_container")]
MENU = FEED + [node(NAME, id=LI + "identity_mirror_component_profile_name")]


def li_composer(body=""):
    return [node(parent=None), node(desc="Close"), node("Anyone"), node("Post"), node(text=body, cls="android.widget.EditText")]


def li_feed_post(name=NAME, body="Shipping notes."):
    return FEED + [node(parent=0), node(name, parent=4), node("now", parent=4), node(desc=body, parent=4), node(desc="Comment", parent=4)]


def li_client(menu=MENU, after=None, composer=None):
    screens = [FEED, menu, FEED, composer or li_composer(), li_composer("Shipping notes."), after or li_feed_post()]
    return Client(screens, app="LinkedIn", package="com.linkedin.android")


def test_linkedin_checks_the_member_then_posts_once_and_proves_it():
    client = li_client()
    linkedin_post(client, POST)
    assert client.taps(id="me_launcher_container")
    assert len(client.taps(text="Post")) == 1
    assert [d["text"] for _, d in client.calls if d.get("action") == "type"] == ["Shipping notes."]
    assert client.calls[-1][0] == "/reviews/p/complete"


@pytest.mark.parametrize("client", [
    lambda: li_client(menu=FEED + [node("Someone Else", id=LI + "identity_mirror_component_profile_name")]),
    lambda: li_client(menu=FEED),
    lambda: li_client(composer=li_composer("Old draft")),
    lambda: li_client(composer=[n for n in li_composer() if n.get("text") != "Anyone"]),
])
def test_linkedin_stops_before_posting_on_any_mismatch(client):
    client = client()
    with pytest.raises(NotSent):
        linkedin_post(client, POST)
    assert not client.taps(text="Post")


def test_unproven_linkedin_post_is_left_for_the_owner():
    client = li_client(after=FEED)
    with pytest.raises(ValueError) as caught:
        linkedin_post(client, POST)
    assert not isinstance(caught.value, NotSent)
    assert len(client.taps(text="Post")) == 1
    assert not any(route.endswith("/complete") for route, _ in client.calls)


def test_linkedin_proof_needs_the_member_in_the_same_post():
    assert linkedin_published(li_feed_post(), NAME, "Shipping notes.")
    assert not linkedin_published(li_feed_post(name="Someone Else"), NAME, "Shipping notes.")
    assert not linkedin_published(li_feed_post() + [node(desc="Shipping notes.", parent=4)], NAME, "Shipping notes.")


def test_linkedin_adapter_requires_the_member_name_as_handle(tmp_path):
    from phone_agent.social import SocialStore
    store = SocialStore(tmp_path / "social.sqlite3")
    base = dict(name="Owner", platform="linkedin", handle=NAME, soul="Plain", phones=["p"], delivery_adapter="linkedin-accessibility-v1")
    assert store.account(base)["delivery_adapter"] == "linkedin-accessibility-v1"
    for changes in ({"handle": "@owner"}, {"platform": "x", "handle": "@owner2"}):
        with pytest.raises(ValueError):
            store.account(dict(base, **changes))


def test_worker_picks_the_adapter_by_kind_and_reports_stops_honestly(monkeypatch):
    import social_worker
    assert social_worker.delivery_ready(dict(delivery_adapter="x-accessibility-v1"), "reply")
    assert social_worker.delivery_ready(dict(delivery_adapter="linkedin-accessibility-v1"), "post")
    assert not social_worker.delivery_ready(dict(delivery_adapter="linkedin-accessibility-v1"), "reply")
    assert not social_worker.delivery_ready(dict(delivery_indicator=dict(posted_id="a:id/b")), "reply")

    review = dict(REPLY, account_id="account")
    profile = dict(delivery_adapter="x-accessibility-v1", phones=["phone"])

    class ClaimClient:
        api_url = "http://test/api/v1"
        headers = {"Authorization": "Bearer agent"}
        def get(self, route): return {"account": profile}
        def post(self, route, data): return dict(review, lease_token="lease")

    recorded = []

    class DeliveryClient:
        def __init__(self, *args): self.headers = {}
        def get(self, route): return {"reviews": [dict(review, status="executing")]}
        def post(self, route, data): recorded.append((route, data))

    def stop(client, item):
        raise NotSent("The comment was not found under Mentions")

    monkeypatch.setattr(social_worker, "Client", DeliveryClient)
    monkeypatch.setattr(social_delivery, "x_reply", stop)
    social_worker.deliver(ClaimClient(), review)
    assert recorded[0][0] == "/reviews/r/uncertain"
    assert recorded[0][1]["evidence"].startswith("Stopped before sending; nothing was posted.")


def test_x_not_in_front_is_reported_as_not_sent():
    client = Client([HOME], app="Chrome", package="com.android.chrome")
    with pytest.raises(NotSent):
        x_reply(client, REPLY)
    with pytest.raises(NotSent):
        linkedin_post(Client([FEED], app="Chrome", package="com.android.chrome"), POST)


def test_reply_proof_needs_the_right_profile():
    other = [dict(n, text="@someone_else") if n.get("text") == "@owner" else n for n in my_reply()]
    client = Client(reply_screens(other))
    with pytest.raises(ValueError):
        x_reply(client, REPLY)
    assert any(d.get("url") == "https://x.com/owner" for _, d in client.calls)
    assert not any(route.endswith("/complete") for route, _ in client.calls)
