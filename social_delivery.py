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
    return [e for e in elements if "EditText" in e.get("class", "")]


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


def x_post(client, review):
    """Publish an already leased original post once, or leave it uncertain."""
    if review.get("kind") != "post" or review.get("platform") != "x":
        raise ValueError("X adapter handles original posts only")
    handle, body = review["account"], review["reply"]
    if not re.fullmatch(r"@[A-Za-z0-9_]{1,15}", handle):
        raise ValueError("X adapter requires an exact @handle")
    route = "/phones/" + quote(review["phone"], safe="")
    def sense():
        if client.get(route + "/current_app")["current_app"] not in ("X", "Twitter", "twitter"):
            raise ValueError("X is not the foreground app")
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    client.post(route + "/app", {"app": "X"})
    ui = sense()
    if editors(ui):
        raise ValueError("Existing composer left untouched")
    one(ui, desc="Show navigation drawer")
    one(ui, desc="Home")
    if any(e.get("text") == body for e in ui):
        raise ValueError("Matching text already visible; inspect before posting")
    one(ui, desc="Post")
    tap(desc="Post")
    ui = sense()
    fields = editors(ui)
    if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text"):
        raise ValueError("Composer account or empty editor not verified")
    client.post(route + "/action", dict(action="type", text=body, clear=True, confirm=True))
    ui = sense()
    fields = editors(ui)
    if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text") != body:
        raise ValueError("Final account/body check failed")
    one(ui, desc="Post")
    started = next_device_minute(client, route)
    ui = sense()
    fields = editors(ui)
    if not x_identity(ui, handle) or len(fields) != 1 or fields[0].get("text") != body:
        raise ValueError("Composer changed while waiting for timestamp boundary")
    one(ui, desc="Post")
    sent_at = time.monotonic()
    tap(desc="Post")  # Exactly one commit request. Exceptions never replay it.
    for attempt in range(5):
        ui = sense()
        if x_published(ui, handle, body, time.monotonic() - sent_at):
            client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": "Verified exact approved text and account in one fresh X post subtree, outside the composer, with reply/repost/like controls."})
            return
        if attempt < 4:
            time.sleep(1)
    # X goes back to the home feed, which shows display names, not handles; the
    # profile shows the handle and a fresh time on each of the account's posts.
    try:
        on_profile = x_profile_proof(client, route, sense, tap, handle, body, sent_at)
    except Exception:
        on_profile = False  # Navigation failed; the screenshot check below still applies.
    if on_profile:
        client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": "Verified exact approved text in one fresh post of the account on its X profile, outside the composer, with reply/repost/like controls."})
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
    post of the handle with the exact text, over up to three pages."""
    tap(desc="Show navigation drawer")
    tap(text="Profile")
    if tab:
        tap(text=tab)
    for page in range(3):
        ui = sense()
        if x_published(ui, handle, body, time.monotonic() - sent_at):
            return True
        if page < 2:
            _swipe_up(client, route, ui)
    return False


def x_reply_composer(elements, handle, author, original):
    """The reply composer opened from the original's own Reply control shows
    the original's author and exact text, who it replies to, and our account."""
    return (x_identity(elements, handle)
            and sum(e.get("text") == original and "EditText" not in e.get("class", "") for e in elements) == 1
            and any(e.get("text") == author for e in elements)
            and any(e.get("text", "").startswith("Replying to") and author in e.get("text", "") for e in elements))


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
        tap(desc="Notifications tab")
        tap(desc="Mentions")
        for page in range(4):
            ui = sense()
            if sum(e.get("text") == original for e in ui) == 1:
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
        client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": f"Replied to {author}. Verified the exact approved text in one fresh post of {handle} on its Replies tab, outside any composer, with reply/repost/like controls."})
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
        if linkedin_published(ui, name, body):
            client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": f"Posted to Anyone as {name} (checked in the profile menu first). Verified the exact approved text in one feed post naming {name}, outside the composer."})
            return
    raise ValueError("Post was sent but not found in the feed")
