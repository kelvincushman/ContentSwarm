"""Comment replies on Facebook, Instagram and TikTok, against recorded
accessibility trees. Names and text are invented; layouts follow the apps."""

import pytest

import social_delivery
from social_delivery import NotSent, instagram_reply, notification, shows_comment, tiktok_reply


def node(text="", desc="", cls="android.widget.TextView", parent=0, id="", scrollable=False):
    return dict(text=text, desc=desc, id=id, **{"class": cls}, parent_index=parent, enabled=True,
                scrollable=scrollable, bounds=[0, 0, 1080, 2000])


class Client:
    """Hands out screens in order; records every request."""
    def __init__(self, screens, package):
        self.screens, self.package, self.calls = list(screens), package, []

    def get(self, route):
        if route.endswith("/current_app"):
            return dict(package=self.package)
        return dict(elements=self.screens.pop(0) if len(self.screens) > 1 else self.screens[0])

    def post(self, route, data):
        self.calls.append((route, data))
        return {}

    def taps(self, **selector):
        return [d for _, d in self.calls if d.get("action") == "tap" and all(d.get(k) == v for k, v in selector.items())]

    def typed(self):
        return [d["text"] for _, d in self.calls if d.get("action") == "type"]

    def completed(self):
        return any(route.endswith("/complete") for route, _ in self.calls)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(social_delivery.time, "sleep", lambda _: None)


def spread(changes, key):
    """A changed comments screen stands for every read of it (found, back, row)."""
    changes = dict(changes)
    if key in changes:
        changes.update({f"{key}_back": changes[key], f"{key}_row": changes[key]})
    return changes


ORIGINAL = "Which glue did you use for the hinge on this one?"
BODY = "Plain wood glue, clamped overnight."


# TikTok

TT = "com.zhiliaoapp.musically"
TT_REVIEW = dict(id="t", revision=3, platform="tiktok", kind="reply", phone="phone", account="@owner.makes",
                 author="Asker Name", original=ORIGINAL, reply=BODY)
TT_NAV = [node(parent=None), node(cls="android.widget.FrameLayout"), node("Home", parent=1), node("Friends", parent=1),
          node("Inbox", parent=1), node("Profile", parent=1)]
TT_PROFILE = TT_NAV + [node("Owner Name"), node("@owner.makes"), node("Edit profile")]
TT_INBOX = TT_NAV + [node(cls="androidx.recyclerview.widget.RecyclerView", scrollable=True), node(parent=6),
                     node("Activity", parent=7), node("New followers", parent=6)]


def tt_activity(author="Asker Name", line=f"commented: {ORIGINAL}"):
    return TT_NAV + [node(cls="androidx.recyclerview.widget.RecyclerView", scrollable=True), node(parent=6),
                     node(author, parent=7), node(line, parent=7), node("2h", parent=7),
                     node(parent=6), node("Other Person", parent=11), node("liked your video", parent=11)]


def tt_comments(author="Asker Name", replies=1, extra=()):
    rows = [node(parent=None), node("2 comments"), node(cls="androidx.recyclerview.widget.RecyclerView", scrollable=True),
            node(parent=2), node(author, parent=3), node(ORIGINAL, parent=3), node("2h", parent=3)]
    rows += [node("Reply", parent=3) for _ in range(replies)]
    rows += [node(parent=2), node("Someone Else", parent=len(rows)), node("Nice one", parent=len(rows)), node("Reply", parent=len(rows))]
    return rows + list(extra)


def tt_composer(text="Reply to Asker Name"):
    return tt_comments() + [node(text, cls="android.widget.EditText"), node(desc="Post comment")]


def tt_published(age="Just now", badge="Creator", body=BODY):
    screen = tt_comments()
    row = len(screen)
    return screen + [node(parent=2), node("Owner Name", parent=row), node(badge, parent=row), node(body, parent=row),
                     node(age, parent=row), node("Reply", parent=row),
                     node("Add comment...", cls="android.widget.EditText")]


def tt_screens(**changes):
    # Each search finds its match, looks one page below it, comes back; the
    # comment's page is read once more for its row.
    screens = dict(home=TT_NAV, nav=TT_NAV, profile=TT_PROFILE, nav2=TT_NAV, inbox=TT_INBOX, activity=tt_activity(),
                   activity_below=TT_NAV, activity_back=tt_activity(), comments=tt_comments(), comments_below=TT_NAV,
                   comments_back=tt_comments(), comments_row=tt_comments(),
                   composer=tt_composer(), typed=tt_composer(BODY), after=tt_published())
    screens.update(spread(changes, "comments"))
    return Client(list(screens.values()), TT)


def test_tiktok_finds_the_comment_types_once_and_proves_it():
    client = tt_screens()
    tiktok_reply(client, TT_REVIEW)
    assert client.taps(text="Profile") and client.taps(text="Inbox") and client.taps(text="Activity")
    assert client.taps(text=f"commented: {ORIGINAL}")
    assert client.taps(text="Reply", within=ORIGINAL)
    assert client.typed() == [BODY]
    assert len(client.taps(desc="Post comment")) == 1
    assert client.calls[-1][0] == "/reviews/t/complete"


@pytest.mark.parametrize("changes", [
    dict(profile=TT_NAV + [node("@someone.else")]),                      # Another account signed in.
    dict(profile=TT_NAV),                                                # No username shown.
    dict(activity=tt_activity(author="Other Person")),                   # Comment by someone else.
    dict(activity=tt_activity(line="commented: Which glue")),            # Text differs, not shortened.
    dict(comments=tt_comments(author="Asker Name2")),                    # Row names a longer name.
    dict(comments=tt_comments(replies=2)),                               # Ambiguous Reply in the row.
    dict(composer=tt_composer("Reply to Other Person")),                 # Replying to someone else.
    dict(composer=tt_composer("Leftover draft")),                        # Editor not empty.
    dict(typed=tt_composer("Something else")),                           # Text changed after typing.
    dict(typed=[n for n in tt_composer(BODY) if n.get("desc") != "Post comment"]),  # No send control.
    dict(composer=tt_composer() + [node(BODY)]),                         # The reply is already there.
])
def test_tiktok_stops_before_sending_on_any_mismatch(changes):
    client = tt_screens(**changes)
    with pytest.raises(NotSent):
        tiktok_reply(client, TT_REVIEW)
    assert not client.taps(desc="Post comment")
    assert not client.completed()


def test_tiktok_missing_notification_is_not_sent_after_three_pages():
    client = tt_screens(activity=TT_INBOX + [node("Nothing new")], comments=TT_INBOX)
    client.screens = client.screens[:6]
    with pytest.raises(NotSent, match="notification was not found"):
        tiktok_reply(client, TT_REVIEW)
    assert len([d for _, d in client.calls if d.get("action") == "swipe"]) == 3
    assert not client.taps(text="Reply")


@pytest.mark.parametrize("after", [
    tt_published(age="3d"),                 # Not fresh.
    tt_published(badge=""),                 # Not the creator's.
    tt_composer(BODY),                      # Still in the composer.
    tt_published() + [node(BODY)],          # Two copies.
])
def test_unproven_tiktok_reply_is_left_uncertain(after):
    client = tt_screens(after=after)
    with pytest.raises(ValueError) as caught:
        tiktok_reply(client, TT_REVIEW)
    assert not isinstance(caught.value, NotSent)  # It was sent: never "nothing was posted".
    assert len(client.taps(desc="Post comment")) == 1
    assert not client.completed()


def test_tiktok_refuses_other_apps_kinds_and_loose_identities():
    with pytest.raises(NotSent):
        tiktok_reply(Client([TT_NAV], "com.android.chrome"), TT_REVIEW)
    with pytest.raises(NotSent):
        tiktok_reply(Client([TT_NAV], TT), dict(TT_REVIEW, kind="post"))
    with pytest.raises(NotSent):
        tiktok_reply(Client([TT_NAV], TT), dict(TT_REVIEW, account="Owner Name"))
    with pytest.raises(NotSent):
        tiktok_reply(Client([TT_NAV], TT), dict(TT_REVIEW, author=" "))


# Instagram (shapes recorded from app 455 on the connected phone)

IGP = "com.instagram.android:id/"
IG_REVIEW = dict(id="i", revision=5, platform="instagram", kind="reply", phone="phone", account="@owner.makes",
                 author="@asker_01", original=ORIGINAL, reply=BODY)
IG_NAV = [node(parent=None), node(id=IGP + "feed_tab", desc="Home"), node(id=IGP + "profile_tab", desc="Profile"),
          node(id=IGP + "notification")]
IG_PROFILE = IG_NAV + [node(id=IGP + "profile_header_create_button", desc="Create new"), node(desc="Edit profile"),
                       node("Edit profile", parent=5), node("owner.makes", id=IGP + "action_bar_title")]
FIELD = "android.widget.AutoCompleteTextView"


def ig_news(line=f"asker_01 commented: {ORIGINAL} 2h"):
    return IG_NAV + [node("Notifications", desc="Notifications", id=IGP + "action_bar_title"),
                     node(id=IGP + "activity_feed_list", cls="android.view.View", scrollable=True),
                     node(id=IGP + "activity_feed_newsfeed_story_row", parent=5), node(line, parent=6)]


def ig_line(parent, who, text):
    """A comment as Instagram prints it: one combined line, then a button for
    the name and (twice) one for the text."""
    return [node(f"{who} {text}", cls="com.instagram.ui.text.IgTextLayoutView", parent=parent),
            node(desc=who, cls="android.widget.Button", parent=parent + 1),
            node(desc=text, cls="android.widget.Button", parent=parent + 1),
            node(desc=text, cls="android.widget.Button", parent=parent + 1)]


def ig_comments(author="asker_01", extra=()):
    screen = [node(parent=None), node("Comments", id=IGP + "title_text_view"),
              node(id=IGP + "sticky_header_list", cls="androidx.recyclerview.widget.RecyclerView", scrollable=True),
              node(parent=2)]
    screen += ig_line(3, author, ORIGINAL) + [node("2h", parent=3), node("Reply", parent=3)]
    return screen + list(extra)


def ig_composer(text="@asker_01 ", banner="Replying to asker_01"):
    return ig_comments() + [node(banner), node(text, cls=FIELD, id=IGP + "layout_comment_thread_edittext_multiline"),
                            node(desc="Post")]


def ig_published(age="1s", who="owner.makes", body=f"@asker_01 {BODY}"):
    screen = ig_comments()
    row = len(screen)
    return screen + [node(parent=2)] + ig_line(row, who, body) + [
        node(age, parent=row), node("Reply", parent=row), node("Comment as owner.makes...", cls=FIELD)]


def ig_screens(**changes):
    screens = dict(home=IG_NAV, profile=IG_PROFILE, opened=ig_news(), news=ig_news(), news_below=IG_NAV, news_back=ig_news(),
                   comments=ig_comments(), comments_below=IG_NAV, comments_back=ig_comments(), comments_row=ig_comments(),
                   composer=ig_composer(), typed=ig_composer(f"@asker_01 {BODY}"), after=ig_published())
    screens.update(spread(changes, "comments"))
    return Client(list(screens.values()), "com.instagram.android")


def test_instagram_keeps_the_mention_types_once_and_proves_it():
    client = ig_screens()
    instagram_reply(client, IG_REVIEW)
    assert client.taps(id=IGP + "profile_tab") and client.taps(id=IGP + "notification")
    assert client.taps(text=f"asker_01 commented: {ORIGINAL} 2h")
    assert client.taps(text="Reply", within=f"asker_01 {ORIGINAL}")
    assert client.typed() == [f"@asker_01 {BODY}"]
    assert len(client.taps(desc="Post")) == 1
    assert client.calls[-1][0] == "/reviews/i/complete"


@pytest.mark.parametrize("changes", [
    dict(profile=IG_NAV + [node("owner.makes", id=IGP + "action_bar_title")]),       # Someone else's profile.
    dict(profile=[n if n.get("text") != "owner.makes" else dict(n, text="someone.else") for n in IG_PROFILE]),
    dict(opened=IG_NAV),                                                             # Notifications didn't open.
    dict(news=ig_news(f"asker_012 commented: {ORIGINAL} 2h")),
    dict(comments=ig_comments(author="someone")),
    dict(comments=ig_comments(extra=ig_line(3, "asker_01", ORIGINAL))),             # Same comment twice.
    dict(composer=ig_composer(banner="Replying to someone")),
    dict(composer=ig_composer("@someone ")),
    dict(typed=ig_composer(f"@asker_01 {BODY}", banner="")),
])
def test_instagram_stops_before_sending_on_any_mismatch(changes):
    client = ig_screens(**changes)
    with pytest.raises(NotSent):
        instagram_reply(client, IG_REVIEW)
    assert not client.taps(desc="Post")


def test_instagram_composer_hint_counts_as_empty():
    client = ig_screens(composer=ig_composer("Comment as owner.makes..."), typed=ig_composer(BODY), after=ig_published(body=BODY))
    instagram_reply(client, IG_REVIEW)
    assert client.typed() == [BODY]


@pytest.mark.parametrize("after", [ig_published(age="5w"), ig_published(who="someone.else"), ig_composer(f"@asker_01 {BODY}")])
def test_unproven_instagram_reply_is_left_uncertain(after):
    client = ig_screens(after=after)
    with pytest.raises(ValueError) as caught:
        instagram_reply(client, IG_REVIEW)
    assert not isinstance(caught.value, NotSent)
    assert len(client.taps(desc="Post")) == 1
    assert not client.completed()


# Facebook (navigation and identity recorded from app 587 on the connected phone)

FB_REVIEW = dict(id="f", revision=2, platform="facebook", kind="reply", phone="phone", account="Owner Name",
                 author="Asker Name", original=ORIGINAL, reply=BODY)


def fb_tabs(bounds=(0, 2007, 180, 2069)):
    tabs = [node(parent=None)]
    for i, name in enumerate(("Home", "Reels", "Friends", "Marketplace", "Notifications, tab 5 of 6, 1 new", "Profile"), 1):
        tab = node(desc=name if "," in name else f"{name}, tab {i} of 6", cls="android.app.ActionBar$Tab")
        tab["bounds"] = list(bounds)
        tabs.append(tab)
    return tabs


FB_PROFILE = fb_tabs() + [node(desc="Edit profile"), node(parent=0), node("Owner Name\xa0\xa0", parent=8),
                          node("Owner Name", parent=8), node("\xa0", desc="Get verified", parent=8),
                          node(desc="Open profile switcher", parent=8)]


def fb_notifications(line=f'Asker Name commented on your post: "{ORIGINAL}". 5 minutes ago'):
    return fb_tabs() + [node(cls="androidx.recyclerview.widget.RecyclerView", scrollable=True), node(parent=7),
                        node(line, desc=line, parent=8)]


def fb_post(author="Asker Name", extra=()):
    return [node(parent=None), node(cls="androidx.recyclerview.widget.RecyclerView", scrollable=True), node(parent=1),
            node(author, desc=author, parent=2), node(ORIGINAL, desc=ORIGINAL, parent=2), node("5m", parent=2),
            node("Like", parent=2), node("Reply", parent=2)] + list(extra)


def fb_composer(text="Asker Name", banner="Replying to Asker Name"):
    return fb_post() + [node(banner), node(text, cls="android.widget.EditText"), node(desc="Send")]


def fb_published(age="Just now", who="Owner Name"):
    screen = fb_post()
    row = len(screen)
    body = f"Asker Name {BODY}"
    return screen + [node(parent=1), node(who, desc=who, parent=row), node(body, desc=body, parent=row),
                     node(age, parent=row), node("Reply", parent=row), node("Write a reply…", cls="android.widget.EditText")]


def fb_screens(**changes):
    screens = dict(home=fb_tabs(), tabs=fb_tabs(), profile=FB_PROFILE, tabs2=fb_tabs(), notifications=fb_notifications(),
                   notifications_below=fb_tabs(), notifications_back=fb_notifications(), post=fb_post(), post_below=fb_tabs(),
                   post_back=fb_post(), post_row=fb_post(),
                   composer=fb_composer(), typed=fb_composer(f"Asker Name {BODY}"), after=fb_published())
    screens.update(spread(changes, "post"))
    return Client(list(screens.values()), "com.facebook.katana")


def test_facebook_checks_the_profile_finds_the_comment_and_proves_the_reply():
    client = fb_screens()
    social_delivery.facebook_reply(client, FB_REVIEW)
    assert client.taps(desc="Profile, tab 6 of 6") and client.taps(desc="Notifications, tab 5 of 6, 1 new")
    assert client.taps(text="Reply", within=ORIGINAL)
    assert client.typed() == [f"Asker Name {BODY}"]
    assert len(client.taps(desc="Send")) == 1
    assert client.calls[-1][0] == "/reviews/f/complete"


def test_facebook_scrolls_once_to_show_a_collapsed_tab_bar():
    client = fb_screens(tabs=fb_tabs(bounds=(0, 0, 0, 0)))
    client.screens.insert(2, fb_tabs())
    social_delivery.facebook_reply(client, FB_REVIEW)
    assert len([d for _, d in client.calls if d.get("action") == "swipe" and d["duration_ms"] == 300]) == 1
    assert client.calls[-1][0] == "/reviews/f/complete"


@pytest.mark.parametrize("changes", [
    dict(profile=[n for n in FB_PROFILE if n.get("desc") != "Edit profile"]),           # Not our profile.
    dict(profile=[dict(n, text="Someone Else") if n.get("text") == "Owner Name" else n for n in FB_PROFILE]),
    dict(notifications=fb_notifications(f'Other Person commented on your post: "{ORIGINAL}".')),
    dict(post=fb_post(author="Asker Namesake")),
    dict(composer=fb_composer(banner="Replying to Other Person")),
    dict(composer=fb_composer("Old draft")),
    dict(typed=fb_composer(f"Asker Name {BODY} extra")),
])
def test_facebook_stops_before_sending_on_any_mismatch(changes):
    client = fb_screens(**changes)
    with pytest.raises(NotSent):
        social_delivery.facebook_reply(client, FB_REVIEW)
    assert not client.taps(desc="Send")


@pytest.mark.parametrize("after", [fb_published(age="2d"), fb_published(who="Someone Else")])
def test_unproven_facebook_reply_is_left_uncertain(after):
    client = fb_screens(after=after)
    with pytest.raises(ValueError) as caught:
        social_delivery.facebook_reply(client, FB_REVIEW)
    assert not isinstance(caught.value, NotSent)
    assert not client.completed()


# Shared matching

def test_notification_lines_may_shorten_long_comments():
    long = "This is a long comment that the notification list will certainly shorten for us"
    assert shows_comment(f"asker commented: {long[:40]}…", long)
    assert not shows_comment("asker commented: This is a…", long)          # Too little shown.
    assert not shows_comment(f"asker commented: {long[:40]}", long)        # Cut without an ellipsis.
    assert not shows_comment("asker commented: This is a long comment that differs…", long)


def test_one_notification_or_none():
    screen = ig_news()
    assert notification(screen, "asker_01", ORIGINAL) == {"text": f"asker_01 commented: {ORIGINAL} 2h"}
    assert notification(screen + [node(f"asker_01 commented: {ORIGINAL} 1d", parent=5)], "asker_01", ORIGINAL) is None
    assert notification(ig_news(f"asker_01 liked: {ORIGINAL}"), "asker_01", ORIGINAL) is None


def test_adapters_need_their_platform_and_exact_handles(tmp_path):
    from phone_agent.social import SocialStore
    store = SocialStore(tmp_path / "social.sqlite3")
    ok = [("tiktok", "@owner.makes", "tiktok-accessibility-v1"), ("instagram", "@owner.makes", "instagram-accessibility-v1"),
          ("facebook", "Owner Name", "facebook-accessibility-v1")]
    for platform, handle, adapter in ok:
        saved = store.account(dict(name=platform, platform=platform, handle=handle, soul="Plain", phones=["p"], delivery_adapter=adapter))
        assert saved["delivery_adapter"] == adapter
    bad = [("tiktok", "owner", "tiktok-accessibility-v1"), ("tiktok", "@owner.", "tiktok-accessibility-v1"),
           ("instagram", "@two..dots", "instagram-accessibility-v1"), ("instagram", "@x" * 20, "instagram-accessibility-v1"),
           ("facebook", "@owner", "facebook-accessibility-v1"), ("x", "@owner_x", "tiktok-accessibility-v1")]
    for platform, handle, adapter in bad:
        with pytest.raises(ValueError):
            store.account(dict(name="bad", platform=platform, handle=handle, soul="Plain", phones=["p"], delivery_adapter=adapter))


def test_tiktok_sources_and_worker_routing(tmp_path):
    import social_worker
    from phone_agent.review_queue import ReviewQueue
    from phone_agent.social import SocialStore
    store = SocialStore(tmp_path / "social.sqlite3")
    account = store.account(dict(name="TT", platform="tiktok", handle="@owner.makes", soul="Plain", phones=["p"]))
    for url in ("https://www.tiktok.com/@owner.makes/video/1", "https://vm.tiktok.com/ZAbc/"):
        store.enqueue(account["id"], "Reply", dict(kind="reply", source_url=url, author="Asker Name", original=ORIGINAL))
    with pytest.raises(ValueError):
        store.enqueue(account["id"], "Reply", dict(kind="reply", source_url="https://tiktok.com.evil.test/a", author="A", original="B"))
    queue = ReviewQueue(tmp_path / "reviews.sqlite3")
    item = queue.create(dict(platform="tiktok", account="@owner.makes", phone="p", source_url="https://www.tiktok.com/@owner.makes/video/1",
                             author="Asker Name", original=ORIGINAL, reply=BODY, humanizer_version="3.1.0"))
    assert item["platform"] == "tiktok"
    for adapter, function in (("facebook-accessibility-v1", "facebook_reply"), ("instagram-accessibility-v1", "instagram_reply"),
                              ("tiktok-accessibility-v1", "tiktok_reply")):
        assert social_worker.delivery_ready(dict(delivery_adapter=adapter), "reply")
        assert not social_worker.delivery_ready(dict(delivery_adapter=adapter), "post")
        assert callable(getattr(social_delivery, function))
    assert not social_worker.delivery_ready(dict(platform="tiktok", delivery_indicator=dict(posted_id="a:id/b")), "post")


def test_open_url_opens_the_new_apps_in_their_own_app():
    from phone_agent.bridge import _url_app
    assert _url_app("https://www.instagram.com/p/abc/") == "com.instagram.android"
    assert _url_app("https://vm.tiktok.com/ZAbc/") == "com.zhiliaoapp.musically"
    assert _url_app("https://www.facebook.com/some.page/posts/1") == "com.facebook.katana"
    with pytest.raises(ValueError):
        _url_app("https://tiktok.com.evil.test/")


# Review follow-ups

def test_a_second_match_one_page_below_stops_delivery():
    second = tt_activity(line=f"replied to your comment: {ORIGINAL}")
    client = tt_screens(activity_below=second)
    with pytest.raises(NotSent, match="more than one notification"):
        tiktok_reply(client, TT_REVIEW)
    assert not client.taps(text="Reply")
    older = [dict(n, text="3d") if n.get("text") == "2h" else n for n in tt_comments()]  # Same words, another comment.
    client = tt_screens(comments_below=older)
    with pytest.raises(NotSent, match="more than once"):
        tiktok_reply(client, TT_REVIEW)
    assert not client.taps(text="Reply")


def test_the_same_row_seen_again_below_is_not_a_duplicate():
    client = tt_screens(activity_below=tt_activity(), comments_below=tt_comments())
    tiktok_reply(client, TT_REVIEW)
    assert client.calls[-1][0] == "/reviews/t/complete"


def test_the_match_must_still_be_there_after_looking_below():
    client = tt_screens(activity_back=TT_NAV)
    with pytest.raises(NotSent, match="again"):
        tiktok_reply(client, TT_REVIEW)
    assert not client.taps(text=f"commented: {ORIGINAL}")


def test_an_earlier_reply_in_any_printed_form_stops_before_typing():
    composer = ig_composer() + ig_line(3, "owner.makes", f"@asker_01 {BODY}")
    client = ig_screens(composer=composer)
    with pytest.raises(NotSent, match="already visible"):
        instagram_reply(client, IG_REVIEW)
    assert not client.typed()


def test_tiktok_typed_fallback_never_overrides_a_visible_other_target():
    typed = tt_comments() + [node("Reply to Other Person"), node(BODY, cls="android.widget.EditText"), node(desc="Post comment")]
    client = tt_screens(typed=typed)
    with pytest.raises(NotSent):
        tiktok_reply(client, TT_REVIEW)
    assert not client.taps(desc="Post comment")


@pytest.mark.parametrize("draft", ["Add a comment about the hinge", "Comment as someone.else...", "Reply to asker_01 later"])
def test_drafts_that_look_like_hints_are_never_cleared(draft):
    client = ig_screens(composer=ig_composer(draft))
    with pytest.raises(NotSent, match="not empty"):
        instagram_reply(client, IG_REVIEW)
    assert not client.typed()
