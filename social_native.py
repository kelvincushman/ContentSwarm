"""Read the native Android share preview without selecting any recipient."""

import re
from social_delivery import descendants, one


def preview_data(elements):
    """Select metadata within the preview, excluding suggested-contact labels."""
    roots = [i for i, e in enumerate(elements) if e.get("id") == "android:id/content_preview_container"]
    if len(roots) != 1:
        return None
    group = descendants(elements, roots[0])
    titles = [e.get("text", "") for e in group if e.get("id") == "android:id/text1"]
    bodies = [e.get("text", "") for e in group if e.get("id") == "android:id/text2"]
    if len(titles) != 1 or len(bodies) != 1 or not bodies[0]:
        return None
    match = re.fullmatch(r"[^\n]+ \((@[A-Za-z0-9_]{1,15})\) on X", titles[0])
    return dict(handle=match[1], body=bodies[0], single_post=True) if match else None


def read_x_preview(client, route):
    """Open Share via, read system metadata, and restore the X detail screen.

    Unsupported layouts return no observation. Interrupted navigation raises;
    no application, recipient, copy action or final share control is selected.
    """
    def package():
        return client.get(route + "/current_app").get("package")
    def focused(allowed):
        import time
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = package()
            if value in allowed:
                return value
            time.sleep(0.2)
        raise ValueError("Expected window did not gain focus")
    def ui():
        return client.get(route + "/ui")["elements"]
    def tap(**selector):
        client.post(route + "/action", dict(action="tap", confirm=True, **selector))
    if package() != "com.twitter.android":
        raise ValueError("X is not the focused package")
    one(ui(), desc="Share")
    tap(desc="Share")
    try:
        if package() != "com.twitter.android":
            raise ValueError("Unexpected share window")
        controls = ui()
        if sum(e.get("text") == "Share via…" for e in controls) != 1:
            return None
        tap(text="Share via…")
        foreground = focused({"android", "com.android.intentresolver"})
        import time
        for attempt in range(3):
            elements = ui()
            if package() != foreground:
                raise ValueError("Chooser focus changed during observation")
            observation = preview_data(elements)
            if observation is not None:
                return observation
            if attempt < 2:
                time.sleep(0.2)
        return None
    finally:
        foreground = package()
        if foreground in ("android", "com.android.intentresolver"):
            client.post(route + "/action", dict(action="key", key="BACK", confirm=True))
            foreground = focused({"com.twitter.android"})
        if foreground != "com.twitter.android":
            raise ValueError("Cannot restore X after share preview")
        controls = ui()
        if sum(e.get("desc") == "Close sheet" for e in controls) == 1:
            tap(desc="Close sheet")
