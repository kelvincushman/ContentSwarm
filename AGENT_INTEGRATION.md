# Agent Integration (Hookup Kit)

The server generates a ready-to-use **hookup kit** so any agent — OpenClaw,
Hermes, Claude Code, an OpenAI/Anthropic app, or an MCP client — can drive the
phones. It's generated from **live state** (phones, accounts, onboarded apps +
flows), so it always reflects what actually exists.

Get it from the **Agent Hookup** tab of the [console](UI_CONSOLE.md), or the API:

```
GET /integration                 # everything (JSON)
GET /integration/system_prompt   # one format as text
GET /integration/tools           # OpenAI tool schemas
GET /integration/tools_anthropic # Anthropic tool schemas
GET /integration/mcp             # MCP server config
GET /integration/rest_cheatsheet # curl examples
# add ?redact=true to replace the API key with a placeholder
```

## The four formats

### 1. System prompt
Human-readable instructions embedding the server URL, auth header, the list of
phones + accounts, and the onboarded apps + flows, plus rules (prefer flows,
resolve the right account, normalized coords, reset keyboard after bulk typing).

**Use it in:**
- **OpenClaw / Hermes** — paste into the agent's system prompt / SOUL/CONTEXT
  file. The agent calls the REST API with its HTTP tool.
- **Claude Code** — drop into `CLAUDE.md` or a skill; it will curl the endpoints.
- **Any LLM** — prepend to your system prompt; give the model an HTTP tool.

### 2. Tool / function schemas
`tools` (OpenAI) and `tools_anthropic` give function-calling definitions for the
common actions: `list_devices`, `list_apps`, `list_accounts`, `get_screenshot`,
`get_ui`, `tap`, `type_text`, `open_app`, `detect_screen`, `tap_element`,
`run_flow`. Register them with your agent framework and route each call to the
matching endpoint (the `endpoint_map` in `GET /integration` gives the mapping).

```python
# OpenAI example
tools = requests.get(f"{B}/integration/tools", headers=H).json()
resp = client.chat.completions.create(model="...", tools=tools, messages=[...])
# then dispatch resp tool_calls to the phone server endpoints
```

### 3. MCP config
For MCP-capable agents. Uses **`mcp-openapi-proxy`** over the server's OpenAPI
spec, so every endpoint becomes an MCP tool automatically:

```json
{
  "mcpServers": {
    "phone-server": {
      "command": "uvx",
      "args": ["mcp-openapi-proxy"],
      "env": {
        "OPENAPI_SPEC_URL": "http://<server>:8770/openapi.json",
        "EXTRA_HEADERS": "X-API-Key: <key>"
      }
    }
  }
}
```
Install the bridge: `uvx mcp-openapi-proxy` (or `pip install mcp-openapi-proxy`).
Add the block to your MCP client config (Claude Desktop, etc.).

### 4. REST cheatsheet
Copy-paste `curl` for phones, accounts, screenshot, tap, type, open app, and run
flow — filled in with your first real device/app/flow.

## Recommended agent pattern

1. `GET /registry/accounts` → resolve which **device + app + flow** matches the
   task ("the X personal account", "the LinkedIn business page").
2. Prefer `POST /apps/{app}/devices/{id}/flows/{flow}/run` with params — flows
   resolve UI live and return per-step results.
3. Fall back to screenshot + `tap`/`type` only when no flow fits.
4. After a bulk `type` run with `restore:false`, call `/devices/{id}/keyboard/reset`.

## Security
The kit embeds your `X-API-Key` so it works when pasted. Treat it as a secret,
or generate with `?redact=true` and fill the key in yourself.
