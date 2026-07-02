"""Generate agent 'skills' from live server state.

A skill is a self-contained folder with a SKILL.md (YAML frontmatter: name +
description) that tells an agent WHEN to use it and HOW. This is an alternative
to MCP: drop the folder into an agent's skills directory (Claude Code, Hermes,
OpenClaw) and the description makes the agent invoke it at the right moment.

Generated:
  * phone-control/         — base skill: screenshot/tap/type/open/run-flow +
                             a `phone.py` CLI helper.
  * <app>-<flow>/          — one focused skill per onboarded flow, with a
                             trigger tuned to the app/platform/accounts.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

from phone_server.appstore import STORE
from phone_server.config import get_settings
from phone_server.registry import REGISTRY

settings = get_settings()
_REDACTED = "<YOUR_API_KEY>"

# Platform → natural-language triggers so the agent recognises the intent.
_PLATFORM_WORDS = {
    "x": "tweet, post to X, post to Twitter",
    "twitter": "tweet, post to Twitter/X",
    "facebook": "post to Facebook, share on Facebook",
    "instagram": "post to Instagram, share a reel/story",
    "linkedin": "post to LinkedIn, share an update",
    "tiktok": "post to TikTok, upload a TikTok",
    "youtube": "upload to YouTube, post a short",
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _base_url(base_url: str) -> str:
    return (REGISTRY.config.public_url or base_url).rstrip("/")


def _accounts_for_app(app: str) -> list[dict[str, Any]]:
    out = []
    for did, dc in REGISTRY.devices.items():
        for a in dc.accounts.values():
            if a.app == app:
                out.append({"device_id": did, "name": a.name, "platform": a.platform, "kind": a.kind, "handle": a.handle})
    return out


# --- CLI helper shipped inside the base skill ------------------------------


def _phone_cli(base_url: str, api_key: str) -> str:
    return f'''#!/usr/bin/env python3
"""phone.py — tiny CLI for the ContentSwarm Phone Server.

Config via env (or the baked-in defaults below):
  PHONE_SERVER_URL   default {base_url}
  PHONE_SERVER_KEY   default (set on the server)

Examples:
  python phone.py devices
  python phone.py accounts
  python phone.py screenshot RF8M90JL60K out.png
  python phone.py tap RF8M90JL60K 500 500
  python phone.py type RF8M90JL60K "hello world"
  python phone.py open twitter RF8M90JL60K
  python phone.py flow twitter RF8M90JL60K post_tweet text="hi from my agent"
"""
import os, sys, json, urllib.request

BASE = os.environ.get("PHONE_SERVER_URL", "{base_url}").rstrip("/")
KEY  = os.environ.get("PHONE_SERVER_KEY", "{api_key}")

def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={{"X-API-Key": KEY, "Content-Type": "application/json"}})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def main(a):
    if not a: return print(__doc__)
    cmd, rest = a[0], a[1:]
    if cmd == "devices":   return print(call("GET", "/registry/devices").decode())
    if cmd == "accounts":  return print(call("GET", "/registry/accounts").decode())
    if cmd == "screenshot":
        dev, out = rest[0], (rest[1] if len(rest) > 1 else "screen.png")
        d = json.loads(call("GET", f"/devices/{{dev}}/screenshot?format=base64"))
        import base64; open(out, "wb").write(base64.b64decode(d["image_base64"]))
        return print(out)
    if cmd == "tap":  return print(call("POST", f"/devices/{{rest[0]}}/tap",  {{"x": int(rest[1]), "y": int(rest[2]), "normalized": True}}).decode())
    if cmd == "type": return print(call("POST", f"/devices/{{rest[0]}}/type", {{"text": rest[1]}}).decode())
    if cmd == "open": return print(call("POST", f"/apps/{{rest[0]}}/devices/{{rest[1]}}/open").decode())
    if cmd == "flow":
        app, dev, flow = rest[0], rest[1], rest[2]
        params = dict(kv.split("=", 1) for kv in rest[3:])
        return print(call("POST", f"/apps/{{app}}/devices/{{dev}}/flows/{{flow}}/run", {{"params": params}}).decode())
    print("unknown command:", cmd)

if __name__ == "__main__":
    main(sys.argv[1:])
'''


def _base_skill_md(base_url: str, api_key: str) -> str:
    devs = "\n".join(f"  - {did} \"{dc.label}\"" for did, dc in REGISTRY.devices.items()) or "  - (configure phones in the console)"
    return f"""---
name: phone-control
description: >-
  Control the connected Android phone(s) over the ContentSwarm Phone Server.
  Use this whenever the user wants to operate a phone: take a screenshot, tap or
  type on screen, open an app, or post to a social account (Facebook, Instagram,
  LinkedIn, X/Twitter, TikTok). Prefer a specific per-flow skill when one exists.
metadata:
  server: {base_url}
---

# Phone Control

Drive real Android phones through the phone server at `{base_url}`.
Auth: send header `X-API-Key: {api_key}` on every request.

Phones:
{devs}

## Quick CLI (bundled)
```bash
export PHONE_SERVER_URL={base_url}
export PHONE_SERVER_KEY={api_key}
python phone.py devices                       # list phones + accounts
python phone.py accounts                       # list social accounts
python phone.py screenshot DEVICE out.png      # see the screen
python phone.py tap DEVICE 500 500             # tap (0-1000 normalized)
python phone.py type DEVICE "hello 🚀"          # type (unicode-safe)
python phone.py open APP DEVICE                # open an onboarded app
python phone.py flow APP DEVICE FLOW k=v       # run a saved flow
```

## Or call the API directly
```bash
B={base_url}; H='-H "X-API-Key: {api_key}"'
curl -s $H $B/registry/accounts
curl -s $H -X POST $B/apps/APP/devices/DEVICE/flows/FLOW/run -d '{{"params":{{}}}}' -H 'Content-Type: application/json'
```

## How to choose
1. `accounts` → pick the phone+app+flow that matches the request (e.g. "the
   LinkedIn business account").
2. Prefer running a **flow** (robust, resolves UI live) over freehand taps.
3. Freehand only when no flow fits: `screenshot` → decide → `tap`/`type`.
4. After bulk typing, reset the keyboard: `POST /devices/DEVICE/keyboard/reset`.
"""


def _flow_skill_md(app: dict, flow_name: str, params: list[str], base_url: str, api_key: str) -> str:
    slug = _slug(f"{app['app']}-{flow_name}")
    accts = _accounts_for_app(app["app"])
    platforms = sorted({a["platform"] for a in accts})
    words = ", ".join(_PLATFORM_WORDS.get(p, p) for p in platforms) or app["display_name"] or app["app"]
    acct_line = "; ".join(f"{a['name']} ({a['platform']}/{a['kind']} {a['handle']})" for a in accts) or "no linked accounts"
    param_json = ", ".join(f'"{p}": "..."' for p in params)
    return slug, f"""---
name: {slug}
description: >-
  Use when the user wants to {words}. Runs the '{flow_name}' flow on the
  onboarded '{app['app']}' app. Accounts: {acct_line}.
  Parameters: {', '.join(params) or 'none'}.
metadata:
  app: {app['app']}
  flow: {flow_name}
  server: {base_url}
---

# {app['display_name'] or app['app']} · {flow_name}

Runs the saved **{flow_name}** flow. Parameters: {', '.join(params) or 'none'}.

## Run it
```bash
B={base_url}
curl -s -H "X-API-Key: {api_key}" -H 'Content-Type: application/json' \\
  -X POST $B/apps/{app['app']}/devices/DEVICE/flows/{flow_name}/run \\
  -d '{{"params": {{{param_json}}}}}'
```
Replace `DEVICE` with the phone id for the target account (see `phone-control`
skill → `accounts`). The response includes per-step results so you can confirm
success or see where it stopped.
"""


# --- assembly --------------------------------------------------------------


def generate(base_url: str, redact: bool = False) -> dict[str, Any]:
    base_url = _base_url(base_url)
    api_key = _REDACTED if (redact or not settings.api_key) else settings.api_key

    files: list[dict[str, str]] = [
        {"path": "phone-control/SKILL.md", "content": _base_skill_md(base_url, api_key)},
        {"path": "phone-control/phone.py", "content": _phone_cli(base_url, api_key)},
    ]
    skills = [{"name": "phone-control", "description": "Base skill: screenshot/tap/type/open/run-flow + CLI"}]

    for slug in STORE.list_apps():
        p = STORE.load(slug)
        if not p:
            continue
        appd = {"app": p.app, "display_name": p.display_name, "package": p.package}
        for flow_name, flow in p.flows.items():
            s, md = _flow_skill_md(appd, flow_name, flow.params, base_url, api_key)
            files.append({"path": f"{s}/SKILL.md", "content": md})
            skills.append({"name": s, "description": f"Run '{flow_name}' on {p.app}"})

    return {"count": len(skills), "skills": skills, "files": files}


def zip_bytes(base_url: str, redact: bool = False) -> bytes:
    kit = generate(base_url, redact)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in kit["files"]:
            z.writestr(f["path"], f["content"])
    return buf.getvalue()
