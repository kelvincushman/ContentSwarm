"""Extra ADB helpers: UI-hierarchy capture, activity introspection, and
selector-based element resolution.

These power robust, resolution-independent control: instead of tapping fixed
coordinates, we dump the live Android view tree (`uiautomator dump`) and locate
nodes by resource-id / text / content-desc, then tap their center.
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from typing import Any, Optional

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_COMPONENT_RE = re.compile(r"([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)")


def _prefix(device_id: Optional[str]) -> list[str]:
    return ["adb", "-s", device_id] if device_id else ["adb"]


def dump_ui_xml(device_id: Optional[str] = None, timeout: int = 15) -> str:
    """Capture the current UI hierarchy as raw uiautomator XML."""
    p = _prefix(device_id)
    subprocess.run(
        p + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    r = subprocess.run(
        p + ["shell", "cat", "/sdcard/window_dump.xml"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return r.stdout


def parse_ui(xml: str) -> list[dict[str, Any]]:
    """Parse uiautomator XML into a flat list of node dicts with bounds/center."""
    nodes: list[dict[str, Any]] = []
    if not xml or "<" not in xml:
        return nodes
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return nodes

    for node in root.iter("node"):
        b = node.attrib.get("bounds", "")
        m = _BOUNDS_RE.search(b)
        if not m:
            continue
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        nodes.append(
            {
                "resource_id": node.attrib.get("resource-id", ""),
                "text": node.attrib.get("text", ""),
                "content_desc": node.attrib.get("content-desc", ""),
                "class_name": node.attrib.get("class", ""),
                "package": node.attrib.get("package", ""),
                "clickable": node.attrib.get("clickable") == "true",
                "enabled": node.attrib.get("enabled") == "true",
                "focused": node.attrib.get("focused") == "true",
                "scrollable": node.attrib.get("scrollable") == "true",
                "bounds": [x1, y1, x2, y2],
                "center": [(x1 + x2) // 2, (y1 + y2) // 2],
            }
        )
    return nodes


def get_ui_elements(device_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Convenience: dump + parse in one call."""
    return parse_ui(dump_ui_xml(device_id))


def match_selector(nodes: list[dict[str, Any]], selector: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every node matching a selector dict (fields ANDed, empties ignored)."""
    out: list[dict[str, Any]] = []
    rid = selector.get("resource_id")
    text = selector.get("text")
    contains = selector.get("text_contains")
    cdesc = selector.get("content_desc")
    cls = selector.get("class_name")
    clickable = selector.get("clickable")

    for n in nodes:
        if rid and n["resource_id"] != rid:
            continue
        if text is not None and n["text"] != text:
            continue
        if contains and contains.lower() not in n["text"].lower():
            continue
        if cdesc is not None and n["content_desc"] != cdesc:
            continue
        if cls and n["class_name"] != cls:
            continue
        if clickable is not None and n["clickable"] != clickable:
            continue
        out.append(n)
    return out


def resolve_selector(
    nodes: list[dict[str, Any]], selector: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Resolve a selector to a single node, honoring an optional `index`."""
    matches = match_selector(nodes, selector)
    if not matches:
        return None
    idx = selector.get("index")
    if idx is not None:
        return matches[idx] if 0 <= idx < len(matches) else None
    return matches[0]


def wake(device_id: Optional[str] = None) -> None:
    """Turn the screen on (does not unlock a secure keyguard)."""
    subprocess.run(
        _prefix(device_id) + ["shell", "input", "keyevent", "KEYCODE_WAKEUP"],
        capture_output=True,
        timeout=6,
    )


def keyguard_showing(device_id: Optional[str] = None) -> bool:
    """True if the lock screen (keyguard) is up — screenshots are blocked then."""
    try:
        r = subprocess.run(
            _prefix(device_id) + ["shell", "dumpsys", "window"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in r.stdout.splitlines():
            if "isKeyguardShowing=" in line:
                return "isKeyguardShowing=true" in line
    except Exception:
        pass
    return False


def get_current_activity(device_id: Optional[str] = None) -> Optional[str]:
    """Best-effort resumed activity component, e.g. 'com.pkg/.MainActivity'."""
    p = _prefix(device_id)
    try:
        r = subprocess.run(
            p + ["shell", "dumpsys", "activity", "activities"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in r.stdout.splitlines():
            if "mResumedActivity" in line or "ResumedActivity" in line:
                m = _COMPONENT_RE.search(line)
                if m:
                    return m.group(1)
    except Exception:
        pass

    try:
        r = subprocess.run(
            p + ["shell", "dumpsys", "window"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in r.stdout.splitlines():
            if "mCurrentFocus" in line:
                m = _COMPONENT_RE.search(line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def resolve_launch_activity(package: str, device_id: Optional[str] = None) -> Optional[str]:
    """Look up the launchable component for a package via `cmd package`."""
    p = _prefix(device_id)
    try:
        r = subprocess.run(
            p + ["shell", "cmd", "package", "resolve-activity", "--brief", package],
            capture_output=True,
            text=True,
            timeout=8,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if "/" in line and line.startswith(package):
                return line
    except Exception:
        pass
    return None


ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"

# Preferred human keyboards to fall back to, in order (Samsung, Gboard, SwiftKey).
_PREFERRED_IMES = ["honeyboard", "inputmethod.latin", "swiftkey"]


def get_current_ime(device_id: Optional[str] = None) -> str:
    r = subprocess.run(
        _prefix(device_id) + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
        timeout=6,
    )
    return (r.stdout + r.stderr).strip()


def list_imes(device_id: Optional[str] = None, enabled_only: bool = True) -> list[str]:
    """List IME ids. enabled_only=True -> `ime list -s`, else all installed."""
    args = ["shell", "ime", "list", "-s"] if enabled_only else ["shell", "ime", "list", "-a", "-s"]
    r = subprocess.run(_prefix(device_id) + args, capture_output=True, text=True, timeout=8)
    return [ln.strip() for ln in r.stdout.splitlines() if "/" in ln]


def set_ime(ime: str, device_id: Optional[str] = None) -> bool:
    r = subprocess.run(
        _prefix(device_id) + ["shell", "ime", "set", ime],
        capture_output=True,
        text=True,
        timeout=8,
    )
    out = (r.stdout + r.stderr).lower()
    return "selected" in out or r.returncode == 0


def reset_ime(device_id: Optional[str] = None, prefer: Optional[str] = None) -> Optional[str]:
    """Switch away from AdbIME to a human keyboard; returns the IME set, or None."""
    enabled = [i for i in list_imes(device_id, enabled_only=True) if "adbkeyboard" not in i]
    order = ([prefer] if prefer else []) + _PREFERRED_IMES
    for key in order:
        if not key:
            continue
        for ime in enabled:
            if key in ime and set_ime(ime, device_id):
                return ime
    for ime in enabled:  # fallback: first enabled non-adb IME
        if set_ime(ime, device_id):
            return ime
    return None


def list_third_party_packages(device_id: Optional[str] = None) -> list[str]:
    """List installed third-party package names (for onboarding discovery)."""
    p = _prefix(device_id)
    try:
        r = subprocess.run(
            p + ["shell", "pm", "list", "packages", "-3"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return sorted(
            line.split(":", 1)[1].strip()
            for line in r.stdout.splitlines()
            if line.startswith("package:")
        )
    except Exception:
        return []
