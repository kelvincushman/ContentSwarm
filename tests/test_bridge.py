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
    fake = use_bridge(FakeBridge([[
        element(text="+44 7700 900123", id="conversation_contact_name", clickable=False),
        element(text="Hello", cls="android.widget.EditText"),
    ]]))
    result = bridge.compose_message("serial", "whatsapp", "+44 7700 900123", "Hello")
    assert result == {
        "success": True, "channel": "whatsapp", "recipient": "+44 7700 900123",
        "characters": 5, "sent": False, "recipient_verified": True,
        "body_verified": True,
    }
    assert fake.calls == [("compose_whatsapp", "+44 7700 900123", "Hello")]


def test_send_requires_expected_body_and_verifies_editor_cleared(use_bridge, monkeypatch):
    body = "Dentist confirmed"
    before = [
        element(text="+447700900123", id="conversation_contact_name", clickable=False),
        element(text=body, cls="android.widget.EditText", clickable=True),
        element(id="com.whatsapp:id/send", desc="Send"),
    ]
    after = [element(text="", cls="android.widget.EditText", clickable=True)]
    fake = use_bridge(FakeBridge([before, after]))
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)

    result = bridge.send_composed_message(
        "serial", "whatsapp", "+447700900123", body
    )
    assert result["sent"] is True
    assert result["verified"] is True
    assert result["verification"] == "composer-cleared"
    assert len(fake.calls) == 1


@pytest.mark.parametrize("after", [[], [element(text="Sent", id="message_text")]])
def test_send_is_unverified_without_positive_empty_editor_evidence(
    use_bridge, monkeypatch, after,
):
    body = "Approved body"
    editor = element(
        text=body, id="message_editor", cls="android.widget.EditText",
        bounds=(0, 100, 500, 200),
    )
    before = [
        element(text="+447700900123", id="recipient_text_view", clickable=False),
        editor,
        element(id="send_message", desc="Send"),
    ]
    fake = use_bridge(FakeBridge([before, after]))
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)
    result = bridge.send_composed_message(
        "serial", "sms", "+447700900123", body,
    )
    assert result["sent"] is False
    assert result["verified"] is False
    assert result["verification"] == "composer-clear-not-observed"


def test_send_does_not_tap_when_body_is_stale(use_bridge):
    fake = use_bridge(FakeBridge([[
        element(text="+447700900123", id="recipient_text_view", clickable=False),
        element(text="approved draft stale", cls="android.widget.EditText"),
        element(id="send_message", desc="Send"),
    ]]))
    with pytest.raises(LookupError, match="expected body"):
        bridge.send_composed_message(
            "serial", "sms", "+447700900123", "approved draft"
        )
    assert fake.calls == []


def test_compose_fails_closed_when_recipient_is_not_visible(use_bridge):
    fake = use_bridge(FakeBridge([[
        element(text="Wrong contact", clickable=False),
        element(text="Hello", cls="android.widget.EditText"),
    ]]))
    with pytest.raises(LookupError, match="recipient"):
        bridge.compose_message("serial", "sms", "+447700900123", "Hello")
    assert all(call[0] != "tap" for call in fake.calls)


@pytest.mark.parametrize("editor_text", ["+447700900123", "Kelvin"])
def test_editor_text_cannot_prove_recipient(use_bridge, editor_text):
    fake = use_bridge(FakeBridge([[
        element(text="Wrong contact", clickable=False),
        element(text=editor_text, cls="android.widget.EditText"),
        element(id="send_message", desc="Send"),
    ]]))
    with pytest.raises(LookupError, match="recipient"):
        bridge.compose_message(
            "serial", "sms", "+447700900123", editor_text,
            recipient_label="Kelvin",
        )
    assert all(call[0] != "tap" for call in fake.calls)


def test_send_does_not_trust_editor_as_recipient(use_bridge):
    body = "+447700900123"
    fake = use_bridge(FakeBridge([[
        element(text="Wrong contact", clickable=False),
        element(text=body, cls="android.widget.EditText"),
        element(id="send_message", desc="Send"),
    ]]))
    with pytest.raises(LookupError, match="recipient"):
        bridge.send_composed_message("serial", "sms", body, body)
    assert fake.calls == []


def test_message_bubble_cannot_prove_recipient(use_bridge):
    body = "Approved text"
    fake = use_bridge(FakeBridge([[
        element(text="+447700900123", id="message_text", clickable=False),
        element(text=body, cls="android.widget.EditText"),
        element(id="send_message", desc="Send"),
    ]]))
    with pytest.raises(LookupError, match="recipient"):
        bridge.send_composed_message("serial", "sms", "+447700900123", body)
    assert fake.calls == []


def test_exact_tap_selector_cannot_expand_to_send(use_bridge):
    fake = use_bridge(FakeBridge([[element(text="Send")]]))
    with pytest.raises(LookupError, match="no enabled"):
        bridge.semantic_action("serial", "tap", text="s")
    assert fake.calls == []
