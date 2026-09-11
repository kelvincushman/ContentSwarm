"""Deterministic social app adapters. API calls only; no model or ADB imports."""

import re
import time
from urllib.parse import quote


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
    from social_vision import verify_x_detail
    evidence = verify_x_detail(client, route, handle, body, started, sense)
    client.post(f"/reviews/{review['id']}/complete", {"revision": review["revision"], "evidence": evidence})
