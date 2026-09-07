from types import SimpleNamespace

import pytest

from phone_agent import bridge


def element(
    *, text="", id="", desc="", cls="android.widget.Button",
    bounds=(0, 0, 100, 100), clickable=True, enabled=True,
):
    return SimpleNamespace(
        text=text, id=id, desc=desc, cls=cls, bounds=bounds,
        center=((bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2),
        clickable=clickable, scrollable=False, enabled=enabled,
    )


class FakeBridge:
    def __init__(self, screens=None):
        self.screens = list(screens or [[]])
        self.calls = []

    def ui(self):
        return self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]

    def tap(self, target):
        self.calls.append(("tap", target))

    def text(self, value, clear=False):
        self.calls.append(("text", value, clear))

    def key(self, value):
        self.calls.append(("key", value))

    def swipe(self, *values, ms=300):
        self.calls.append(("swipe", *values, ms))

    def compose_sms(self, recipient, body):
        self.calls.append(("compose_sms", recipient, body))

    def compose_whatsapp(self, recipient, body):
        self.calls.append(("compose_whatsapp", recipient, body))

    def open_uri(self, uri, package=None):
        self.calls.append(("open_uri", uri, package))


@pytest.fixture
def use_bridge(monkeypatch):
    def install(fake):
        monkeypatch.setattr(bridge, "get_bridge", lambda _device=None: fake)
        return fake
    return install


def test_tap_requires_one_clickable_enabled_match(use_bridge):
    fake = use_bridge(FakeBridge([[element(text="Send"), element(text="Send")]]))
    with pytest.raises(RuntimeError, match="ambiguous"):
        bridge.semantic_action("serial", "tap", text="Send")
    assert fake.calls == []


def test_allowlisted_actions_do_not_expose_raw_shell(use_bridge):
    fake = use_bridge(FakeBridge([[element(text="Continue")]]))
    assert bridge.semantic_action("serial", "tap", text="Continue")["success"]
    assert bridge.semantic_action("serial", "type", text="hello", clear=True)["characters"] == 5
    assert bridge.semantic_action("serial", "key", key="back")["key"] == "BACK"
    assert bridge.semantic_action(
        "serial", "swipe", x1=1, y1=2, x2=3, y2=4, duration_ms=250
    )["success"]
    with pytest.raises(ValueError, match="allowlisted"):
        bridge.semantic_action("serial", "key", key="POWER")
    with pytest.raises(ValueError, match="action must"):
        bridge.semantic_action("serial", "shell", text="rm -rf /")


def test_compose_never_taps_send(use_bridge):
    fake = use_bridge(FakeBridge())
    result = bridge.compose_message("serial", "whatsapp", "+44 7700 900123", "Hello")
    assert result == {
        "success": True, "channel": "whatsapp", "recipient": "+44 7700 900123",
        "characters": 5, "sent": False,
    }
    assert fake.calls == [("compose_whatsapp", "+44 7700 900123", "Hello")]


def test_send_requires_expected_body_and_verifies_editor_cleared(use_bridge, monkeypatch):
    body = "Dentist confirmed"
    before = [
        element(text=body, cls="android.widget.EditText", clickable=True),
        element(id="com.whatsapp:id/send", desc="Send"),
    ]
    after = [element(text="", cls="android.widget.EditText", clickable=True)]
    fake = use_bridge(FakeBridge([before, after]))
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)

    result = bridge.send_composed_message("serial", "whatsapp", body)
    assert result["sent"] is True
    assert result["verified"] is True
    assert result["verification"] == "composer-cleared"
    assert len(fake.calls) == 1


def test_send_does_not_tap_when_body_is_stale(use_bridge):
    fake = use_bridge(FakeBridge([[
        element(text="different draft", cls="android.widget.EditText"),
        element(id="send_message", desc="Send"),
    ]]))
    with pytest.raises(LookupError, match="expected body"):
        bridge.send_composed_message("serial", "sms", "approved draft")
    assert fake.calls == []

