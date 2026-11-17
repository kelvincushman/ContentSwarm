"""Deterministic social app adapters. API calls only; no model or ADB imports."""

import re
import time
from urllib.parse import quote


class NotSent(ValueError):
    """Stopped before the commit tap: nothing was posted."""


def one(elements, **selector):
    matches = [e for e in elements if all(e.get(k) == v for k, v in selector.items())]
    if len(matches) != 1:
        raise ValueError("Expected one exact app control")
    return matches[0]


def editors(elements):
    """Editable fields. Instagram's comment field is an AutoCompleteTextView,
    which Android derives from EditText but whose class name doesn't say so."""
    return [e for e in elements if "EditText" in e.get("class", "") or e.get("class", "").endswith("AutoCompleteTextView")]


def x_identity(elements, handle):
    return sum(e.get("desc") == f"{handle}, Switch accounts" and e.get("enabled", False) for e in elements) == 1


def descendants(elements, ancestor):
    """Read one XML subtree without guessing relationships from screen position."""
    found = []
    for index, element in enumerate(elements):
        cursor = index
        while True:
            if cursor == ancestor:
                found.append(element)
                break
            parent = elements[cursor].get("parent_index")
            if type(parent) is not int or not 0 <= parent < cursor:
                break
            cursor = parent
    return found


def x_published(elements, handle, body, seconds_since_send):
    """Require a fresh, single-post subtree containing account, body and controls."""
    if editors(elements):
        return False  # A visible composer is never proof of publication.
    proofs = []
    for index, element in enumerate(elements):
        if element.get("text") != body or "EditText" in element.get("class", ""):
            continue
        cursor = index
        while True:
            group = descendants(elements, cursor)
            texts = [e.get("text", "") for e in group]
            header = [e.get("text", "") for e in descendants(elements[:index], cursor)]
            handles = [value for value in texts if re.fullmatch(r"@[A-Za-z0-9_]{1,15}", value)]
            labels = [e.get("desc", "") for e in group]
            complete = (labels.count("Reply") == 1 and labels.count("Repost") == 1
                        and sum(labels.count(label) for label in ("Like", "Undo Like")) == 1)
            fresh = False
            for value in header:
                stamp = re.fullmatch(r"[•·]?\s*(now|(\d{1,3})s)", value, re.I)
                if stamp and (stamp[1].lower() == "now" or int(stamp[2]) <= seconds_since_send + 5):
                    fresh = True
            if (complete and handles == [handle] and handle in header and fresh and not editors(group)
                    and not any(value in ("Sending", "Sending…", "Not sent", "Retry") for value in texts if value != body)):
                proofs.append(cursor)
                break
            if complete:
                # Never borrow identity/time from a wider screen ancestor.
                break
            parent = elements[cursor].get("parent_index")
            if type(parent) is not int or not 0 <= parent < cursor:
                break
            cursor = parent
    return len(proofs) == 1


def next_device_minute(client, route):
    """Wait at most 65 seconds for a later device minute; never alter its clock."""
    from datetime import datetime
    baseline = client.get(route + "/clock")["iso"]
    first = previous = datetime.fromisoformat(baseline)
    if first.utcoffset() is None:
        raise ValueError("Phone clock requires a UTC offset")
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        current = datetime.fromisoformat(client.get(route + "/clock")["iso"])
        if time.monotonic() >= deadline:
            raise ValueError("Phone clock minute wait expired")
        if current.utcoffset() != first.utcoffset() or not previous <= current or (current-first).total_seconds() > 65:
            raise ValueError("Phone clock changed unexpectedly")
        if current.replace(second=0, microsecond=0) > first:
            return baseline
        previous = current
        time.sleep(1)
    raise ValueError("Phone clock minute did not advance")


def x_post_control(elements):
    """Require one enabled Post label; Android can expose text or content-desc."""
    matches = [e for e in elements if e.get("text") == "Post" or e.get("desc") == "Post"]
    if len(matches) != 1 or not matches[0].get("enabled", False):
        raise ValueError("Expected one enabled X Post control (text or content-desc)")
    field = "desc" if matches[0].get("desc") == "Post" else "text"
    return {field: "Post"}


def x_post(client, review):
    """Publish an already leased original post once, or leave it uncertain."""
    if review.get("kind") != "post" or review.get("platform") != "x":
        raise NotSent("X adapter handles original posts only")
    handle, body = review["account"], review["reply"]
    if not re.fullmatch(r"@[A-Za-z0-9_]{1,15}", handle):
        raise NotSent("X adapter requires an exact @handle")
    route = "/phones/" + quote(review["phone"], safe="")
    def sense():
        if client.get(route + "/current_app")["current_app"] not in ("X", "Twitter", "twitter"):
            raise ValueError("X is not the foreground app")
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    stage = "opening X"
    try:
        client.post(route + "/app", {"app": "X"})
        ui = sense()
        if editors(ui):
            raise ValueError("Existing composer left untouched")
        one(ui, desc="Show navigation drawer")
        one(ui, desc="Home")
        if any(e.get("text") == body for e in ui):
            raise ValueError("Matching text already visible; inspect before posting")
        one(ui, desc="Post")
        stage = "opening the empty composer"
        tap(desc="Post")
        ui = sense()
        fields = editors(ui)
        if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text"):
            raise ValueError("Composer account or empty editor not verified")
        stage = "checking the approved composer"
        client.post(route + "/action", dict(action="type", text=body, clear=True, confirm=True))
        ui = sense()
        fields = editors(ui)
        if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text") != body:
            raise ValueError("Final account/body check failed")
        x_post_control(ui)
        stage = "waiting for the timestamp boundary"
        started = next_device_minute(client, route)
        ui = sense()
        fields = editors(ui)
        if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text") != body:
            raise ValueError("Composer changed while waiting for timestamp boundary")
        selector = x_post_control(ui)
    except Exception as exc:
        raise NotSent(f"X stopped while {stage}: {type(exc).__name__}: {exc}") from exc
    sent_at = time.monotonic()
    tap(**selector)  # Exactly one commit request. Exceptions never replay it.
    for attempt in range(5):
        ui = sense()
        if x_published(ui, handle, body, time.monotonic() - sent_at):
            client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": "Verified exact approved text and account in one fresh X post subtree, outside the composer, with reply/repost/like controls."})
            return
        if attempt < 4:
            time.sleep(1)
    if editors(ui):
        raise ValueError("X composer remained open after the final Post tap; publication is unverified. Inspect before retrying.")
    # X goes back to the home feed, which shows display names, not handles; the
    # profile shows the handle and a fresh time on each of the account's posts.
    try:
        on_profile = x_profile_proof(client, route, sense, tap, handle, body, sent_at)
    except Exception:
        on_profile = False  # Navigation failed; the screenshot check below still applies.
    if on_profile:
        client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": f"Verified exact approved text in one fresh post of the account on its X profile, https://x.com/{handle.removeprefix('@')}, with reply/repost/like controls."})
        return
    try:
        # Back to Home, where the screenshot check looks for the post.
        if not any(e.get("desc") == "Show navigation drawer" for e in sense()):
            client.post(route + "/action", dict(action="key", key="BACK", confirm=True))
    except Exception:
        pass
    from social_vision import verify_x_detail
    evidence = verify_x_detail(client, route, handle, body, started, sense)
    client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": evidence})


X_HANDLE = r"@[A-Za-z0-9_]{1,15}"


def _x(client, route):
    def sense():
        if client.get(route + "/current_app")["current_app"] not in ("X", "Twitter", "twitter"):
            raise ValueError("X is not the foreground app")
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    return sense, tap


def _swipe_up(client, route, elements):
    """Scroll one page using the root's own bounds; no device-specific numbers."""
    left, top, right, bottom = elements[0]["bounds"]
    x = (left + right) // 2
    client.post(route + "/action", dict(action="swipe", x1=x, y1=top + (bottom - top) * 3 // 4,
                                        x2=x, y2=top + (bottom - top) // 4, duration_ms=400))


def x_profile_proof(client, route, sense, tap, handle, body, sent_at, tab=None):
    """Open the account's profile (optionally one tab) and look for one fresh
    post of the handle with the exact text, over up to three pages.

    The profile opens from its link (https://x.com/<handle>) in the X app, from
    whatever screen X is on; it must show the handle before anything is read."""
    client.post(route + "/action", dict(action="open_url", url="https://x.com/" + handle.removeprefix("@")))
    for wait in range(8):
        time.sleep(1)
        ui = sense()
        if any(e.get("id") == "UserProfileScreen" for e in ui) and any(e.get("text") == handle for e in ui):
            break
    else:
        return False
    if tab:
        tap(text=tab)
    for page in range(3):
        ui = sense()
        if x_published(ui, handle, body, time.monotonic() - sent_at):
            return True
        if page < 2:
            _swipe_up(client, route, ui)
    return False


def _names(text, handle):
    """Whether text names this exact @handle (not a longer one)."""
    return re.search(re.escape(handle) + r"(?![A-Za-z0-9_])", text or "") is not None


def x_mention(elements, author, original):
    """One mention whose own row holds the exact text, the author's handle and
    one Reply control. The row is the smallest subtree around the text holding
    a Reply, never reaching the scrolling list itself."""
    anchors = [i for i, e in enumerate(elements) if e.get("text") == original and "EditText" not in e.get("class", "")]
    if len(anchors) != 1:
        return False
    cursor = anchors[0]
    while True:
        if elements[cursor].get("scrollable"):
            return False
        group = descendants(elements, cursor)
        replies = sum(e.get("desc") == "Reply" for e in group)
        if replies:
            return replies == 1 and any(e.get("text") == author for e in group)
        parent = elements[cursor].get("parent_index")
        if type(parent) is not int or not 0 <= parent < cursor:
            return False
        cursor = parent


def x_reply_composer(elements, handle, author, original):
    """The reply composer opened from a mention's own Reply control says who it
    replies to and shows our account. Opened from the Mentions list it doesn't
    repeat the comment; when it does, the comment must be the exact original."""
    shown = [e for e in elements if e.get("text") == original and "EditText" not in e.get("class", "")]
    # A composer that quotes a comment shows its author's handle on a line of
    # its own; the quoted comment must then be exactly the original.
    quoting = any(e.get("text") == author for e in elements)
    return (x_identity(elements, handle)
            and len(shown) == (1 if quoting else 0)
            and any(e.get("text", "").startswith("Replying to") and _names(e.get("text"), author) for e in elements))


def x_reply(client, review):
    """Reply once to a mention, found by its author and exact text, or stop.

    Everything before the single Reply tap raises NotSent. The reply is proved
    by a fresh post of ours with the exact text on our profile's Replies tab.
    """
    if review.get("kind") != "reply" or review.get("platform") != "x":
        raise NotSent("X reply adapter handles replies only")
    handle, author, original, body = review["account"], review["author"].strip(), review["original"], review["reply"]
    if not re.fullmatch(X_HANDLE, handle) or not re.fullmatch(X_HANDLE, author):
        raise NotSent("X replies need exact @handles for the account and the author")
    route = "/phones/" + quote(review["phone"], safe="")
    sense, tap = _x(client, route)
    try:
        client.post(route + "/app", {"app": "X"})
        ui = sense()
        if editors(ui):
            raise NotSent("An X composer or reply field is open; left untouched")
        one(ui, desc="Show navigation drawer")
        # X reopens where it was left; on Notifications the selected tab can't
        # be pressed, so only go there when its filters aren't showing.
        if not any(e.get("desc") == "Mentions" for e in ui):
            tap(desc="Notifications tab")
        tap(desc="Mentions")
        for page in range(4):
            ui = sense()
            if sum(e.get("text") == original for e in ui) == 1:
                if not x_mention(ui, author, original):
                    raise NotSent("The comment's row doesn't show its author and one Reply control")
                break
            if page == 3:
                raise NotSent("The comment was not found under Mentions")
            _swipe_up(client, route, ui)
        tap(desc="Reply", within=original)
        ui = sense()
        fields = editors(ui)
        if not x_reply_composer(ui, handle, author, original) or len(fields) != 1 or fields[0].get("text"):
            raise NotSent("Reply composer, account or original not verified")
        client.post(route + "/action", dict(action="type", text=body, clear=True))
        ui = sense()
        fields = editors(ui)
        if not x_reply_composer(ui, handle, author, original) or len(fields) != 1 or fields[0].get("text") != body:
            raise NotSent("Final account, original or body check failed")
        one(ui, desc="Reply")
        next_device_minute(client, route)
        ui = sense()
        fields = editors(ui)
        if not x_reply_composer(ui, handle, author, original) or len(fields) != 1 or fields[0].get("text") != body:
            raise NotSent("Composer changed while waiting for timestamp boundary")
        one(ui, desc="Reply")
    except NotSent:
        raise
    except Exception as exc:
        raise NotSent(str(exc)[:300]) from exc
    sent_at = time.monotonic()
    tap(desc="Reply")  # Exactly one commit request. Exceptions never replay it.
    time.sleep(2)
    if x_profile_proof(client, route, sense, tap, handle, body, sent_at, tab="Replies"):
        client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": f"Replied to {author}. Verified the exact approved text in one fresh post of {handle} on its Replies tab, https://x.com/{handle.removeprefix('@')}/with_replies, with reply/repost/like controls."})
        return
    raise ValueError("Reply was sent but not found fresh on the Replies tab")


def _linkedin(client, route):
    def sense():
        if client.get(route + "/current_app").get("package") != "com.linkedin.android":
            raise ValueError("LinkedIn is not the foreground app")
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    return sense, tap


def linkedin_identity(elements):
    """The member name in the profile menu, the one place the app shows it."""
    names = [e.get("text") for e in elements if e.get("id", "").endswith(":id/identity_mirror_component_profile_name")]
    return names[0] if len(names) == 1 else None


def linkedin_published(elements, name, body):
    """One feed post, outside any composer, whose full text is the approved
    body and whose own subtree names the member."""
    proofs = 0
    for index, element in enumerate(elements):
        if "EditText" in element.get("class", "") or body not in (element.get("text"), element.get("desc")):
            continue
        cursor = index
        while True:
            group = descendants(elements, cursor)
            if any(e.get("text") == name for e in group):
                if (not editors(group) and sum(e.get("desc") == "Comment" for e in group) <= 1
                        and sum(body in (e.get("text"), e.get("desc")) for e in group) == 1):
                    proofs += 1
                break
            parent = elements[cursor].get("parent_index")
            if type(parent) is not int or not 0 <= parent < cursor:
                break
            cursor = parent
    return proofs == 1


def linkedin_post(client, review):
    """Publish an approved original LinkedIn post as the member, once."""
    if review.get("kind") != "post" or review.get("platform") != "linkedin":
        raise NotSent("LinkedIn adapter handles original posts only")
    name, body = review["account"].strip(), review["reply"]
    route = "/phones/" + quote(review["phone"], safe="")
    sense, tap = _linkedin(client, route)
    try:
        client.post(route + "/app", {"app": "LinkedIn"})
        ui = sense()
        if editors(ui):
            raise NotSent("A LinkedIn editor is open; left untouched")
        one(ui, id="com.linkedin.android:id/tab_feed")
        if any(body in (e.get("text"), e.get("desc")) for e in ui):
            raise NotSent("Matching text already visible; inspect before posting")
        tap(id="me_launcher_container")
        seen = linkedin_identity(sense())
        client.post(route + "/action", dict(action="key", key="BACK", confirm=True))
        if seen != name:
            raise NotSent("The signed-in LinkedIn member is not this account")
        ui = sense()
        if linkedin_identity(ui) is not None:
            raise NotSent("Profile menu did not close")
        tap(id="home_post")
        def ready(expected):
            ui = sense()
            fields = editors(ui)
            if (len(fields) != 1 or fields[0].get("text", "") != expected or sum(e.get("text") == "Anyone" for e in ui) != 1
                    or linkedin_identity(ui) is not None):
                raise NotSent("Composer, audience or body not verified")
            one(ui, text="Post")
            return ui
        ready("")
        client.post(route + "/action", dict(action="type", text=body, clear=True))
        ready(body)
    except NotSent:
        raise
    except Exception as exc:
        raise NotSent(str(exc)[:300]) from exc
    tap(text="Post")  # Exactly one commit request. Exceptions never replay it.
    for attempt in range(8):
        time.sleep(2)
        ui = sense()
        # After posting, LinkedIn may cover the feed with a paid "boost your
        # post" offer. Decline it ("Not now"), never the offer itself.
        texts = [e.get("text", "") for e in ui]
        if "Your post was successful" in texts and "Not now" in texts:
            tap(text="Not now")
            continue
        if linkedin_published(ui, name, body):
            client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": f"Posted to Anyone as {name} (checked in the profile menu first). Verified the exact approved text in one feed post naming {name}, outside the composer."})
            return
    raise ValueError("Post was sent but not found in the feed")


# Comment replies on the account's own posts: Facebook, Instagram and TikTok.
#
# One engine, three app descriptions. Every app is driven from its own
# notifications: the comment's notification opens the post with its comments,
# where the comment's own row must hold the author and exactly one Reply. The
# composer opened from that Reply must say who it replies to. The approved text
# is typed once, checked, and sent with one tap; proof is a fresh reply of the
# account with the exact text in the same comments list. Anything before the
# send raises NotSent; after it, missing proof leaves the review uncertain.

FRESH = re.compile(r"(?:just now|now|\d{1,2}\s?s|1\s?m|\d{1,2} sec(?:ond)?s?(?: ago)?)", re.I)


def _app(client, route, package, label):
    def sense():
        if client.get(route + "/current_app").get("package") != package:
            raise ValueError(f"{label} is not the foreground app")
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    return sense, tap


def label_of(element):
    return element.get("text") or element.get("desc") or ""


def subtree_texts(elements, index):
    return [label_of(e) for e in descendants(elements, index)]


def comment_row(elements, anchor, has_author, reply_label="Reply"):
    """The smallest subtree around the comment's text (element anchor) holding
    a Reply control, never the scrolling list: it must hold exactly one Reply
    and the author. Returns that row's index or None."""
    cursor = anchor
    while True:
        if elements[cursor].get("scrollable"):
            return None
        group = descendants(elements, cursor)
        replies = sum(reply_label in (e.get("text"), e.get("desc")) for e in group)
        if replies:
            return cursor if replies == 1 and has_author(group) else None
        parent = elements[cursor].get("parent_index")
        if type(parent) is not int or not 0 <= parent < cursor:
            return None
        cursor = parent


def comment_reply(client, review, app):
    """Reply once to a comment on the account's own post, or stop."""
    if review.get("kind") != "reply" or review.get("platform") != app["platform"]:
        raise NotSent(f"{app['label']} adapter handles comment replies only")
    handle, body = review["account"], review["reply"]
    author, original = review["author"].strip(), review["original"]
    try:
        author = app["author"](author)
    except ValueError as exc:
        raise NotSent(str(exc)) from exc
    if not app["handle"](handle):
        raise NotSent(f"{app['label']} delivery needs the account's exact identity as its handle")
    route = "/phones/" + quote(review["phone"], safe="")
    sense, tap = _app(client, route, app["package"], app["label"])
    try:
        client.post(route + "/app", {"app": app["label"]})
        time.sleep(2)
        ui = sense()
        blank = lambda value: value in app["blank"](handle, author)
        if any(not blank(e.get("text", "")) for e in editors(ui)):
            raise NotSent(f"A {app['label']} composer holds text; left untouched")
        seen = app["identity"](client, route, sense, tap)
        if seen != handle:
            raise NotSent(f"The signed-in {app['label']} account is not this account")
        app["inbox"](client, route, sense, tap)
        # The approved comment is the one notification by its author showing
        # its text; a second one (another post, an older copy) stops delivery.
        target = _find_once(client, route, sense, lambda ui: notification_rows(ui, author, original),
                            "The comment's notification was not found", "The comment has more than one notification")
        tap(**target)
        time.sleep(1)
        shown = app.get("comment_texts", lambda author, original: [original])(author, original)
        def comments(ui):
            return [(e["text"], tuple(label_of(x) for x in descendants(ui, _row(ui, i))))
                    for i, e in enumerate(ui) if e.get("text") in shown and e not in editors(ui)]
        anchor = _find_once(client, route, sense, comments,
                            "The comment was not found on the post", "The comment's text appears more than once on the post")
        ui = sense()
        anchors = [i for i, e in enumerate(ui) if e.get("text") == anchor]
        if len(anchors) != 1 or comment_row(ui, anchors[0], lambda group: app["row_author"](group, author), app["reply_label"]) is None:
            raise NotSent("The comment's row doesn't show its author and one Reply control")
        # Tap the Reply inside the comment's own row, anchored on its exact text.
        tap(**app["reply_tap"], within=anchor)
        time.sleep(1)
        ui = sense()
        fields = editors(ui)
        start = fields[0].get("text", "") if len(fields) == 1 else None
        if start is None or not app["composer"](ui, author):
            raise NotSent("Reply composer or the comment it replies to not verified")
        prefix = "" if blank(start) else app["prefix"](author, start)
        if prefix is None:
            raise NotSent("Reply editor is not empty")
        expected = body if body.startswith(prefix.strip()) else prefix + body
        forms = app.get("forms", lambda handle, body: [body])(handle, expected) + [body]
        if any(e.get("text") in forms or e.get("desc") in forms for e in ui if e not in fields):
            raise NotSent("Matching text already visible; inspect before replying")
        client.post(route + "/action", dict(action="type", text=expected, clear=True))
        time.sleep(1)
        ui = sense()
        fields = editors(ui)
        typed = app.get("typed", lambda ui, author, original: app["composer"](ui, author))
        if len(fields) != 1 or fields[0].get("text") != expected or not typed(ui, author, original):
            raise NotSent("Final reply target or body check failed")
        send = app["send"](ui)
    except NotSent:
        raise
    except Exception as exc:
        raise NotSent(str(exc)[:300]) from exc
    tap(**send)  # Exactly one commit request. Exceptions never replay it.
    for attempt in range(6):
        time.sleep(2)
        ui = sense()
        if app["published"](ui, handle, expected):
            client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence":
                        f"Replied on {app['label']} to {author}'s comment (found from its notification; row held the author and one Reply; "
                        f"composer replied to {author}). Verified one fresh reply of {handle} with the exact approved text in the post's comments, outside the composer."})
            return
    raise ValueError("Reply was sent but not found fresh in the post's comments")


def _fold(value):
    return " ".join((value or "").split())


def shows_comment(label, original):
    """Whether a notification line shows this comment: all of it, or (as lists
    shorten long comments) at least its first 30 characters then an ellipsis."""
    label, original = _fold(label), _fold(original)
    if not original:
        return False
    if original in label:
        return True
    for cut in (m.start() for m in re.finditer(r"…|\.\.\.", label)):
        before = label[:cut].rstrip()
        for size in range(min(len(original), len(before)), min(30, len(original)) - 1, -1):
            if before.endswith(original[:size].rstrip()):
                return True
    return False


def names(label, author):
    """Whether a label names this exact author (not a longer name)."""
    return re.search(r"(?<![\w.@])" + re.escape(author) + r"(?![\w.])", label or "") is not None


def notification(elements, author, original):
    """The tap selector of the one notification naming the author and showing
    the comment, or None."""
    found = notifications(elements, author, original)
    return found[0] if len(found) == 1 else None  # None also when not tappable.


def notifications(elements, author, original):
    """One tap selector per notification row naming the author and showing
    the comment (None where its line isn't uniquely tappable). A row is the
    whole list item holding the line; a line repeated inside one row (a label
    and its button) is one notification."""
    return [selector for selector, _ in notification_rows(elements, author, original)]


def notification_rows(elements, author, original):
    """(tap selector or None, row signature) for each matching notification
    row; the signature (every label in the row) tells two rows apart."""
    rows = {}
    for index, element in enumerate(elements):
        label = label_of(element)
        if element in editors(elements) or not shows_comment(label, original):
            continue
        row = _row(elements, index)
        group = descendants(elements, row)
        words = " ".join(label_of(e) for e in group)
        if re.search(r"comment|repl", words, re.I) and any(names(label_of(e), author) for e in group):
            rows.setdefault(row, (label, tuple(label_of(e) for e in group)))
    found = []
    for label, signature in rows.values():
        if sum(e.get("text") == label for e in elements) == 1:
            found.append(({"text": label}, signature))
        elif sum(e.get("desc") == label for e in elements) == 1:
            found.append(({"desc": label}, signature))
        else:
            found.append((None, signature))
    return found


def _find_once(client, route, sense, matches, missing, repeated):
    """Find exactly one match over up to four pages, then look one page
    further for another and come back to it. Matches are (value, row
    signature) pairs: the same row seen again after scrolling has the same
    signature, another row with the same text differs (time, counts).
    Returns the match's value."""
    for page in range(4):
        ui = sense()
        found = matches(ui)
        if len(found) > 1 or any(value is None for value, _ in found):
            raise NotSent(repeated)
        if found:
            _swipe_up(client, route, ui)
            time.sleep(1)
            below = sense()
            if any(other != found[0] for other in matches(below)) or len(matches(below)) > 1:
                raise NotSent(repeated)
            _swipe_down(client, route, below)
            time.sleep(1)
            if matches(sense()) != found:
                raise NotSent(f"{missing} again after checking below it")
            return found[0][0]
        if page == 3:
            raise NotSent(missing)
        _swipe_up(client, route, ui)


def _swipe_down(client, route, elements):
    """Scroll back one page (the reverse of _swipe_up)."""
    left, top, right, bottom = elements[0]["bounds"]
    x = (left + right) // 2
    client.post(route + "/action", dict(action="swipe", x1=x, y1=top + (bottom - top) // 4,
                                        x2=x, y2=top + (bottom - top) * 3 // 4, duration_ms=400))


def _row(elements, index):
    """Climb from an element to its list item: the last ancestor below the
    scrolling list. Outside any list there is no row (the root is refused)."""
    cursor = index
    while True:
        parent = elements[cursor].get("parent_index")
        if type(parent) is not int or not 0 <= parent < cursor:
            return index  # No list: only the element itself.
        if elements[parent].get("scrollable"):
            return cursor
        cursor = parent


def fresh_reply(elements, body, is_ours, bodies=None):
    """One element outside any editor whose text is exactly the reply (or one
    of bodies, the forms the app prints it in), whose row (below the list) is
    ours by is_ours and shows a fresh time, and no other copy on screen."""
    bodies = bodies or [body]
    if any(e.get("text") in bodies for e in editors(elements)):
        return False  # Still sitting in the composer: never proof.
    copies = [i for i, e in enumerate(elements) if e.get("text") in bodies and e not in editors(elements)]
    if len(copies) != 1:
        return False
    group = descendants(elements, _row(elements, copies[0]))
    labels = [label_of(e) for e in group]
    return is_ours(group) and any(FRESH.fullmatch(_fold(v).strip("·• ")) for v in labels)


def _hints(phrases):
    """The exact placeholder texts an empty field may report: each phrase
    alone or followed by "..." or "…", and the empty string."""
    return {""} | {phrase + end for phrase in phrases for end in ("", "...", "…")}


def _handle_rule(rule):
    from phone_agent.social import valid_handle
    return lambda handle: valid_handle(rule, handle)


def _shown_name(value):
    """Facebook and TikTok comments show the commenter's display name."""
    if not value or value != value.strip() or "\n" in value or len(value) > 100:
        raise ValueError("The author must be the commenter's name exactly as the comment shows it")
    return value


def _one_label(elements, *labels):
    """One enabled control labelled (text or content-desc) with one of labels."""
    matches = [e for e in elements if e.get("text") in labels or e.get("desc") in labels]
    if len(matches) != 1 or not matches[0].get("enabled", False):
        raise ValueError(f"Expected one enabled {labels[0]} control")
    field = "text" if matches[0].get("text") in labels else "desc"
    return {field: matches[0][field]}


# TikTok: built from its public layout; verify live after sign-in.
TIKTOK_HANDLE = r"@[A-Za-z0-9_.]{2,24}"


def tiktok_identity(client, route, sense, tap):
    """The @username on the account's own Profile tab."""
    tap(**_one_label(sense(), "Profile"))
    time.sleep(2)
    shown = {e.get("text") for e in sense() if re.fullmatch(TIKTOK_HANDLE, e.get("text") or "")}
    return shown.pop() if len(shown) == 1 else None


def tiktok_inbox(client, route, sense, tap):
    tap(**_one_label(sense(), "Inbox"))
    time.sleep(2)
    ui = sense()
    if any(label_of(e) == "Activity" for e in ui):
        tap(**_one_label(ui, "Activity"))
        time.sleep(2)


def tiktok_composer(elements, author):
    """TikTok's reply field says whom it replies to ("Reply to NAME")."""
    return any(label_of(e).startswith("Reply to") and names(label_of(e), author) for e in elements)


TIKTOK = dict(
    platform="tiktok", label="TikTok", package="com.zhiliaoapp.musically",
    handle=_handle_rule("tiktok"), author=_shown_name,
    # An empty field shows its hint as its text; only these exact hints count.
    blank=lambda handle, author: _hints(["Add comment", f"Reply to {author}", f"Reply to @{author}"]),
    identity=tiktok_identity, inbox=tiktok_inbox, notification=notification,
    row_author=lambda group, author: any(label_of(e) == author for e in group),
    reply_label="Reply", reply_tap={"text": "Reply"}, composer=tiktok_composer,
    # Typing replaces the "Reply to NAME" hint, the only reply-target label
    # in the field; the comment it replied to must still be on screen once.
    typed=lambda ui, author, original: tiktok_composer(ui, author) or (
        not any(label_of(e).startswith("Reply to") for e in ui)
        and sum(e.get("text") == original for e in ui if e not in editors(ui)) == 1),
    prefix=lambda author, start: None,  # TikTok doesn't prefill a reply.
    send=lambda ui: _one_label(ui, "Post comment", "Post", "Send"),
    # Comments on the account's own video carry TikTok's "Creator" badge.
    published=lambda ui, handle, body: fresh_reply(ui, body, lambda group: any(label_of(e) == "Creator" for e in group)),
)


def tiktok_reply(client, review):
    """Reply once to a comment on the account's own TikTok video, or stop."""
    comment_reply(client, review, TIKTOK)


# Instagram, as seen on the connected phone (app 455): the username is the
# title of the account's own profile (with Edit profile and Create new, which
# other profiles lack); notifications open from the heart (`id/notification`)
# on Home; rows print "USERNAME commented: TEXT 2h" as one line; post text
# prints as one IgTextLayoutView line "USERNAME TEXT"; the comment field is an
# AutoCompleteTextView whose empty hint is "Comment as USERNAME...".
IG = "com.instagram.android:id/"


def _bare(handle):
    return handle.removeprefix("@")


def instagram_author(value):
    from phone_agent.social import valid_handle
    if not valid_handle("instagram", "@" + _bare(value)):
        raise ValueError("The author must be the commenter's exact Instagram username")
    return _bare(value)


def instagram_identity(client, route, sense, tap):
    tap(id=IG + "profile_tab")
    time.sleep(2)
    ui = sense()
    own = any(e.get("id") == IG + "profile_header_create_button" for e in ui) and any(label_of(e) == "Edit profile" for e in ui)
    shown = [e.get("text") for e in ui if e.get("id") == IG + "action_bar_title"]
    return "@" + shown[0] if own and len(shown) == 1 and shown[0] else None


def instagram_inbox(client, route, sense, tap):
    tap(id=IG + "feed_tab")
    time.sleep(2)
    tap(id=IG + "notification")
    time.sleep(2)
    if not any(e.get("id") == IG + "action_bar_title" and e.get("text") == "Notifications" for e in sense()):
        raise ValueError("Instagram notifications did not open")


INSTAGRAM = dict(
    platform="instagram", label="Instagram", package="com.instagram.android",
    handle=_handle_rule("instagram"), author=instagram_author,
    blank=lambda handle, author: _hints([f"Comment as {_bare(handle)}", "Add a comment", f"Reply to {author}"]),
    identity=instagram_identity, inbox=instagram_inbox, notification=notification,
    # A comment prints as its own text or as one line "USERNAME TEXT".
    comment_texts=lambda author, original: [original, f"{author} {original}"],
    row_author=lambda group, author: any(label_of(e) == author or label_of(e).startswith(author + " ") for e in group),
    reply_label="Reply", reply_tap={"text": "Reply"},
    composer=lambda ui, author: any(label_of(e) == f"Replying to {author}" for e in ui),
    # Reply prefills "@USERNAME "; that mention is kept.
    prefix=lambda author, start: f"@{author} " if start.rstrip() == f"@{author}" else None,
    send=lambda ui: _one_label(ui, "Post"),
    # A reply prints as its own text or as one line "USERNAME TEXT".
    forms=lambda handle, body: [body, f"{_bare(handle)} {body}"],
    published=lambda ui, handle, body: fresh_reply(ui, body, lambda group: any(
        label_of(e) == _bare(handle) or label_of(e).startswith(_bare(handle) + " ") for e in group),
        bodies=[body, f"{_bare(handle)} {body}"]),
)


def instagram_reply(client, review):
    """Reply once to a comment on the account's own Instagram post, or stop."""
    comment_reply(client, review, INSTAGRAM)


# Facebook, as seen on the connected phone (app 587): tabs are described
# "Home, tab 1 of 6" … "Notifications, tab 5 of 6, 1 new", "Profile, tab 6 of 6"
# and collapse (empty bounds) while the feed is scrolled; the account's own
# profile shows its name beside "Open profile switcher", with "Edit profile".
def _tap_tab(client, route, sense, tap, name):
    """Tap the one tab named name, scrolling up once if the bar is collapsed."""
    pattern = re.escape(name) + r", tab \d+ of \d+(?:, \d+ new)?"
    for attempt in range(2):
        ui = sense()
        found = [e for e in ui if re.fullmatch(pattern, e.get("desc") or "")]
        if len(found) != 1:
            raise ValueError(f"Expected one Facebook {name} tab")
        left, top, right, bottom = found[0].get("bounds", [0, 0, 0, 0])
        if right > left and bottom > top:
            tap(desc=found[0]["desc"])
            return
        if attempt == 0:
            left, top, right, bottom = ui[0]["bounds"]
            x = (left + right) // 2
            client.post(route + "/action", dict(action="swipe", x1=x, y1=top + (bottom - top) // 3,
                                                x2=x, y2=top + (bottom - top) * 2 // 3, duration_ms=300))
            time.sleep(1)
    raise ValueError(f"The Facebook {name} tab is not showing")


def facebook_identity(client, route, sense, tap):
    _tap_tab(client, route, sense, tap, "Profile")
    time.sleep(2)
    ui = sense()
    if not any(e.get("desc") == "Edit profile" for e in ui):
        return None  # Not the account's own profile.
    switchers = [i for i, e in enumerate(ui) if e.get("desc") == "Open profile switcher" and e.get("parent_index") is not None]
    names_shown = set()
    for index in switchers:
        names_shown |= {(e.get("text") or "").strip() for e in descendants(ui, ui[index]["parent_index"])} - {""}
    return names_shown.pop() if len(names_shown) == 1 else None


def facebook_inbox(client, route, sense, tap):
    _tap_tab(client, route, sense, tap, "Notifications")
    time.sleep(2)


FACEBOOK = dict(
    platform="facebook", label="Facebook", package="com.facebook.katana",
    handle=_handle_rule("name"), author=_shown_name,
    blank=lambda handle, author: _hints(["Write a reply", "Write a comment", f"Reply to {author}", f"Comment as {handle}"]),
    identity=facebook_identity, inbox=facebook_inbox, notification=notification,
    row_author=lambda group, author: any(label_of(e) == author or names(label_of(e), author) for e in group),
    reply_label="Reply", reply_tap={"text": "Reply"},
    composer=lambda ui, author: any(label_of(e).startswith("Replying to") and names(label_of(e), author) for e in ui),
    # Reply on Facebook may tag the commenter: the field then starts with their name.
    prefix=lambda author, start: f"{author} " if start.rstrip() == author else None,
    send=lambda ui: _one_label(ui, "Send", "Post", "Comment"),
    published=lambda ui, handle, body: fresh_reply(ui, body, lambda group: any(label_of(e) == handle for e in group)),
)


def facebook_reply(client, review):
    """Reply once to a comment on the account's own Facebook post, or stop."""
    comment_reply(client, review, FACEBOOK)
