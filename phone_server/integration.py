"""Generate the 'hookup kit' that lets any agent drive the phone server.

Reads live server state (devices, accounts, onboarded apps + flows) and emits:
  * system_prompt   — paste into OpenClaw / Hermes / Claude Code / any LLM
  * tools           — OpenAI + Anthropic function-calling schemas
  * mcp             — MCP server config (via mcp-openapi-proxy over our OpenAPI)
  * rest_cheatsheet — curl examples

Because it's generated from live state, the kit always reflects the phones and
flows that actually exist right now.
"""

from __future__ import annotations

from typing import Any

from phone_server.appstore import STORE
from phone_server.config import get_settings
from phone_server.registry import REGISTRY

settings = get_settings()
_REDACTED = "<YOUR_API_KEY>"


def _state() -> dict[str, Any]:
    devices = []
    for did, dc in REGISTRY.devices.items():
        devices.append(
            {
                "device_id": did,
                "label": dc.label,
                "accounts": [
                    {"name": a.name, "platform": a.platform, "kind": a.kind, "app": a.app, "handle": a.handle}
                    for a in dc.accounts.values()
                ],
            }
        )
    apps = []
    for slug in STORE.list_apps():
        p = STORE.load(slug)
        if p:
            apps.append(
                {
                    "app": p.app,
                    "package": p.package,
                    "display_name": p.display_name,
                    "flows": {name: f.params for name, f in p.flows.items()},
                    "elements": sorted(p.elements),
                }
            )
    return {"devices": devices, "apps": apps}


# --- tool schemas ----------------------------------------------------------


def _tools_openai() -> list[dict[str, Any]]:
    def fn(name, desc, props, required):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }

    S = {"type": "string"}
    I = {"type": "integer"}
    B = {"type": "boolean"}
    return [
        fn("list_devices", "List connected phones with labels and accounts.", {}, []),
        fn("list_apps", "List onboarded apps with their flows and parameters.", {}, []),
        fn("list_accounts", "List all social accounts across phones (platform, kind, app, flows).", {}, []),
        fn(
            "get_screenshot",
            "Capture the phone screen. Returns base64 PNG.",
            {"device_id": S},
            ["device_id"],
        ),
        fn(
            "get_ui",
            "Return the live UI hierarchy (nodes with resource-id/text/bounds) for selector-based control.",
            {"device_id": S},
            ["device_id"],
        ),
        fn(
            "tap",
            "Tap the screen. Use normalized=true for 0-1000 coordinates.",
            {"device_id": S, "x": I, "y": I, "normalized": B},
            ["device_id", "x", "y"],
        ),
        fn(
            "type_text",
            "Type text (Unicode/emoji-safe). restore=false to keep ADB keyboard set for bulk typing.",
            {"device_id": S, "text": S, "restore": B},
            ["device_id", "text"],
        ),
        fn("open_app", "Open an onboarded app on a phone.", {"device_id": S, "app": S}, ["device_id", "app"]),
        fn(
            "detect_screen",
            "Which known screen of an app is currently showing.",
            {"device_id": S, "app": S},
            ["device_id", "app"],
        ),
        fn(
            "tap_element",
            "Tap a named UI element of an onboarded app (resolved live).",
            {"device_id": S, "app": S, "element": S},
            ["device_id", "app", "element"],
        ),
        fn(
            "run_flow",
            "Run a saved flow of an onboarded app with parameters (e.g. post_tweet {text}).",
            {"device_id": S, "app": S, "flow": S, "params": {"type": "object"}},
            ["device_id", "app", "flow"],
        ),
    ]


def _tools_anthropic(openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]}
        for t in openai_tools
    ]


# --- endpoint mapping (for the agent to actually call) ---------------------

_ENDPOINTS = {
    "list_devices": "GET  /registry/devices",
    "list_apps": "GET  /apps",
    "list_accounts": "GET  /registry/accounts",
    "get_screenshot": "GET  /devices/{device_id}/screenshot?format=base64",
    "get_ui": "GET  /devices/{device_id}/ui",
    "tap": "POST /devices/{device_id}/tap  {x,y,normalized}",
    "type_text": "POST /devices/{device_id}/type  {text,restore}",
    "open_app": "POST /apps/{app}/devices/{device_id}/open",
    "detect_screen": "GET  /apps/{app}/devices/{device_id}/screen",
    "tap_element": "POST /apps/{app}/devices/{device_id}/element/tap  {element}",
    "run_flow": "POST /apps/{app}/devices/{device_id}/flows/{flow}/run  {params}",
}


# --- builders --------------------------------------------------------------


def build_kit(base_url: str, redact: bool = False) -> dict[str, Any]:
    base_url = (REGISTRY.config.public_url or base_url).rstrip("/")
    api_key = _REDACTED if (redact or not settings.api_key) else settings.api_key
    state = _state()
    openai_tools = _tools_openai()

    return {
        "server": {"base_url": base_url, "auth_header": "X-API-Key", "auth_required": bool(settings.api_key)},
        "state": state,
        "system_prompt": _system_prompt(base_url, api_key, state),
        "tools": openai_tools,
        "tools_anthropic": _tools_anthropic(openai_tools),
        "endpoint_map": _ENDPOINTS,
        "mcp": _mcp_config(base_url, api_key),
        "rest_cheatsheet": _rest_cheatsheet(base_url, api_key, state),
    }


def _fmt_devices(state) -> str:
    if not state["devices"]:
        return "  (none configured yet — add phones in the console)"
    lines = []
    for d in state["devices"]:
        accs = ", ".join(f"{a['name']}[{a['platform']}/{a['kind']}→{a['app']}]" for a in d["accounts"]) or "no accounts"
        lines.append(f"  - {d['device_id']} \"{d['label']}\": {accs}")
    return "\n".join(lines)


def _fmt_apps(state) -> str:
    if not state["apps"]:
        return "  (no apps onboarded yet)"
    lines = []
    for a in state["apps"]:
        flows = "; ".join(f"{n}({', '.join(p)})" for n, p in a["flows"].items()) or "no flows"
        lines.append(f"  - {a['app']} ({a['package']}): flows: {flows}")
    return "\n".join(lines)


def _system_prompt(base_url: str, api_key: str, state) -> str:
    return f"""You can control real Android phones through the ContentSwarm Phone Server.

SERVER: {base_url}
AUTH:   send header `X-API-Key: {api_key}` on every request.

You act by calling the server's HTTP API. Two ways to work:
 1. Reliable, preferred: OPEN an onboarded app and RUN a saved flow (e.g. post
    to an account). Flows resolve UI elements live, so they're robust.
 2. Freehand: GET a screenshot (or the UI hierarchy), decide, then tap/type.

PHONES:
{_fmt_devices(state)}

ONBOARDED APPS & FLOWS:
{_fmt_apps(state)}

HOW TO CALL (curl form; use your HTTP tool):
 - List phones:     GET  {base_url}/registry/devices
 - List accounts:   GET  {base_url}/registry/accounts
 - Screenshot:      GET  {base_url}/devices/DEVICE/screenshot?format=base64
 - Tap:             POST {base_url}/devices/DEVICE/tap   body {{"x":500,"y":500,"normalized":true}}
 - Type:            POST {base_url}/devices/DEVICE/type  body {{"text":"hi 🚀"}}
 - Open app:        POST {base_url}/apps/APP/devices/DEVICE/open
 - Run a flow:      POST {base_url}/apps/APP/devices/DEVICE/flows/FLOW/run  body {{"params":{{...}}}}

RULES:
 - Pick the phone/account that matches the task (e.g. "the LinkedIn business
   account"). Use list_accounts to resolve which DEVICE + APP + FLOW to use.
 - Prefer run_flow over freehand taps when a flow exists for the task.
 - Coordinates are 0-1000 normalized when normalized=true.
 - After a bulk typing run with restore=false, POST /devices/DEVICE/keyboard/reset.
 - Report what you did and the server's per-step results.
"""


def _mcp_config(base_url: str, api_key: str) -> dict[str, Any]:
    return {
        "mcpServers": {
            "phone-server": {
                "command": "uvx",
                "args": ["mcp-openapi-proxy"],
                "env": {
                    "OPENAPI_SPEC_URL": f"{base_url}/openapi.json",
                    "API_KEY": api_key,
                    "EXTRA_HEADERS": f"X-API-Key: {api_key}",
                },
            }
        },
        "_note": "Uses the mcp-openapi-proxy bridge over the server's OpenAPI. "
        "Install: `uvx mcp-openapi-proxy` (or `pip install mcp-openapi-proxy`).",
    }


def _rest_cheatsheet(base_url: str, api_key: str, state) -> str:
    dev = state["devices"][0]["device_id"] if state["devices"] else "DEVICE_ID"
    app = state["apps"][0]["app"] if state["apps"] else "APP"
    flow = next(iter(state["apps"][0]["flows"]), "FLOW") if state["apps"] else "FLOW"
    h = f'-H "X-API-Key: {api_key}"'
    return f"""# Phone Server REST cheatsheet
B={base_url}

# phones + accounts
curl -s {h} $B/registry/devices
curl -s {h} $B/registry/accounts

# see the screen
curl -s {h} "$B/devices/{dev}/screenshot" -o screen.png

# tap (normalized 0-1000) and type
curl -s {h} -H 'Content-Type: application/json' -X POST $B/devices/{dev}/tap  -d '{{"x":500,"y":500,"normalized":true}}'
curl -s {h} -H 'Content-Type: application/json' -X POST $B/devices/{dev}/type -d '{{"text":"hello 🚀"}}'

# open an app + run a saved flow
curl -s {h} -X POST $B/apps/{app}/devices/{dev}/open
curl -s {h} -H 'Content-Type: application/json' -X POST $B/apps/{app}/devices/{dev}/flows/{flow}/run -d '{{"params":{{}}}}'
"""
