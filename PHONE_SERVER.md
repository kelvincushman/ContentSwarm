# Phone Control Server

A standalone, LAN-accessible **REST + WebSocket** service that lets an external
agent harness control one or many connected Android phones. It wraps the
existing `phone_agent/` package — no phone logic is re-implemented.

It exposes **four layers**:

1. **Raw primitives** — your harness is the brain: pull screenshots + the live
   UI hierarchy, then tap / swipe / type / launch / press keys. No AI model.
2. **High-level agent** — hand it a natural-language task and a
   vision-language model drives the phone to completion.
3. **App onboarding** — a training session that teaches the server a new app
   (screens, robust element selectors, reusable flows) and **saves** it.
4. **App control** — any agent then opens the app, taps named elements, and
   runs saved flows. **See [APP_ONBOARDING.md](APP_ONBOARDING.md).**

Plus a **web console** for humans and a **hookup-kit generator** for agents:
- **[UI_CONSOLE.md](UI_CONSOLE.md)** — React console served at `/`: devices,
  visual onboarding (click-to-label), accounts, settings, model selection.
- **[AGENT_INTEGRATION.md](AGENT_INTEGRATION.md)** — generate a system prompt +
  tool schemas + MCP config + REST cheatsheet from live state, for any agent.

> Lives alongside — and does not touch — `nova_api.py` (the older
> posting-specific Flask API) or the posting workflows.

**Module layout:** `phone_server/{config,deps,models,schemas,adb_ext,appstore,
flows,onboarding,registry,integration}.py` + `phone_server/routers/{devices,
agent,apps,onboard,streaming,config,registry,integration}.py` + a React app in
`phone_server/ui/`, assembled in `phone_server/server.py` (`uvicorn
phone_server.server:app`).

**New endpoint groups:** `/registry/*` (device configs + accounts), `/config` +
`/config/models` (editable settings + model discovery), `/integration*` (hookup
kit). Auto-generated OpenAPI at `/docs`.

---

## Run

```bash
cd ~/contentswarm
pip install -r requirements.txt            # adds fastapi + uvicorn
export PHONE_API_KEY="choose-a-long-secret"   # omit ONLY on a fully trusted LAN
python run_phone_server.py                  # binds 0.0.0.0:8770
```

### Environment variables

| Var                 | Default                     | Meaning                                   |
|---------------------|-----------------------------|-------------------------------------------|
| `PHONE_SERVER_HOST` | `0.0.0.0`                   | Bind address (all LAN interfaces)         |
| `PHONE_SERVER_PORT` | `8770`                      | Bind port                                 |
| `PHONE_API_KEY`     | *(unset = OPEN)*            | Shared secret. **Set this.**              |
| `VLM_BASE_URL`      | `http://localhost:8000/v1`  | OpenAI-compatible vision model endpoint   |
| `VLM_MODEL`         | `autoglm-phone-9b`          | Model name for `/run`                     |
| `PHONE_AGENT_LANG`  | `en`                        | Agent prompt language (`en` / `cn`)       |
| `PHONE_AGENT_MAX_STEPS` | `50`                    | Default step cap for `/run`               |
| `PHONE_STREAM_FPS`  | `2`                         | Default live-stream frame rate            |
| `PHONE_PROFILES_DIR`| `~/.contentswarm/phone_profiles` | Where onboarded app profiles are saved |

---

## Auth

- **REST:** header `X-API-Key: <key>`
- **WebSocket:** query param `?api_key=<key>`
- Enforced only when `PHONE_API_KEY` is set. Health check is always open.

---

## Device model & coordinates

- A **device_id** is exactly what `adb devices` shows (e.g. `RF8M90JL60K` for
  USB, or `192.168.1.50:5555` for WiFi).
- Input endpoints accept **absolute pixels** by default. Set
  `"normalized": true` to pass **0–1000 relative** coordinates instead — these
  are scaled to the *screenshot* dimensions (the same space the vision model
  uses), so a normalized tap lines up exactly with what you see in a screenshot.
- One **lock per device**: requests to the same phone are serialized; different
  phones run in parallel.

---

## REST endpoints

### Meta / devices
| Method | Path | Body / query | Notes |
|---|---|---|---|
| GET  | `/health` | — | Open, no auth |
| GET  | `/devices` | — | List all adb devices + status/model |
| POST | `/devices/connect` | `{address}` | `adb connect` a WiFi/remote phone |
| POST | `/devices/disconnect` | `{address}` | — |
| POST | `/devices/{id}/tcpip?port=5555` | — | Flip a USB phone to wireless; returns `wifi_address` |
| GET  | `/devices/{id}/screen_size` | — | Screenshot framebuffer size |
| GET  | `/devices/{id}/current_app` | — | Focused app name + resumed activity |
| GET  | `/devices/{id}/ui` | `?interactable_only=` | Parsed live UI hierarchy (selector-based control) |
| GET  | `/devices/{id}/packages` | — | Installed third-party packages (onboarding discovery) |

### Screenshot
| Method | Path | Notes |
|---|---|---|
| GET | `/devices/{id}/screenshot` | Returns **PNG** bytes; `X-Screen-Width/Height` headers |
| GET | `/devices/{id}/screenshot?format=base64` | Returns JSON `{width,height,is_sensitive,image_base64}` |

### Raw input primitives (all POST)
| Path | Body |
|---|---|
| `/devices/{id}/tap` | `{x, y, normalized?}` |
| `/devices/{id}/double_tap` | `{x, y, normalized?}` |
| `/devices/{id}/long_press` | `{x, y, normalized?}` |
| `/devices/{id}/swipe` | `{start_x, start_y, end_x, end_y, duration_ms?, normalized?}` |
| `/devices/{id}/type` | `{text, clear?, restore?}` — Unicode/emoji-safe via ADB Keyboard IME |
| `/devices/{id}/back` | — |
| `/devices/{id}/home` | — |
| `/devices/{id}/launch` | `{app}` — name must be in `phone_agent/config/apps.py` |
| `/devices/{id}/action` | `{action, params}` — full ActionHandler vocabulary, 0–1000 coords |

### Keyboard / IME (the Unicode-typing solution)
Plain `adb shell input text` drops Unicode, emoji, and spaces. Typing therefore
goes through the **ADB Keyboard** IME (`com.android.adbkeyboard/.AdbIME`), which
receives text as a **base64 broadcast** — the same approach used in production.

| Method | Path | Body | Notes |
|---|---|---|---|
| GET  | `/devices/{id}/keyboard` | — | Current IME, whether AdbIME is active/installed, enabled + installed IMEs |
| POST | `/devices/{id}/keyboard/set` | `{ime}` | Force a specific IME |
| POST | `/devices/{id}/keyboard/reset` | `{prefer?}` | Switch off AdbIME back to a human keyboard |

**`restore` on `/type`:** default `true` switches to AdbIME, types, then restores
the human keyboard (safe for a shared phone). Set `restore: false` for bulk
posting ("set once, stay set") — faster because it skips the IME round-trip each
call. After a bulk run, call `/keyboard/reset` once to return to a normal
keyboard (once AdbIME is left set, `restore` alone can't recover the original).

### High-level agent
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/devices/{id}/run` | `{task, max_steps?, lang?, model_base_url?, model_name?}` | **Blocks**, returns full step transcript |
| POST | `/devices/{id}/run/async` | same | Returns `{job_id}` immediately |
| GET  | `/jobs/{job_id}` | — | Poll async job status/result |

> `/run*` requires the vision model to be serving at `VLM_BASE_URL`
> (start `autoglm-phone-9b` with sglang/vLLM — see `requirements.txt`).

---

## WebSocket endpoints

### Live screen stream
```
ws://HOST:8770/ws/{id}/stream?api_key=KEY&fps=3
```
Server pushes `{type:"frame", width, height, is_sensitive, data(base64 png), ts}`.

### Streaming agent run
```
ws://HOST:8770/ws/{id}/run?api_key=KEY
```
Client sends one JSON message: `{task, max_steps?, lang?}`.
Server emits `{type:"step", index, step}` per step, then
`{type:"done", finished, final_message, step_count}`.

---

## Quick harness examples

### Raw control (Python)
```python
import requests
B, H = "http://LENOVO_VM_IP:8770", {"X-API-Key": "your-secret"}

# 1. see the screen
shot = requests.get(f"{B}/devices/RF8M90JL60K/screenshot?format=base64", headers=H).json()

# 2. your harness decides, then acts (normalized 0-1000 coords)
requests.post(f"{B}/devices/RF8M90JL60K/tap",
              headers=H, json={"x": 500, "y": 120, "normalized": True})
requests.post(f"{B}/devices/RF8M90JL60K/type",
              headers=H, json={"text": "hello world"})
```

### High-level task
```python
r = requests.post(f"{B}/devices/RF8M90JL60K/run",
                  headers=H, json={"task": "Open Chrome and search for cats"})
print(r.json()["final_message"])
```

### Onboarded app (no coordinates, no model)
```python
# after an app has been onboarded (see APP_ONBOARDING.md)
requests.post(f"{B}/apps/twitter/devices/RF8M90JL60K/flows/post_tweet/run",
              headers=H, json={"params": {"text": "hello from my agent"}})
```

---

## App onboarding & control

The `/onboard/*` and `/apps/*` routes let agents **teach** the server an app
once, then drive it by named elements and flows — resilient to layout changes
because targets resolve against the live view hierarchy. Full guide, endpoint
tables, and the flow-step reference: **[APP_ONBOARDING.md](APP_ONBOARDING.md)**.

---

## Connecting more phones over WiFi (LAN)

1. Plug the phone in via USB once, authorize the RSA prompt.
2. `POST /devices/{usb_id}/tcpip` → note the returned `wifi_address`.
3. Unplug USB. `POST /devices/connect {"address": "<wifi_address>"}`.
4. The phone now appears in `/devices` as `ip:port` and is fully controllable.

Each phone must have the **ADB Keyboard** app installed for `/type` to work
(https://github.com/nicnocquee/AdbKeyboard).

---

## Notes / limitations

- `/run*` needs the vision model running; the raw layer does not.
- Async job registry is in-memory (cleared on restart).
- Screenshots on DRM/"sensitive" screens return a black image with
  `is_sensitive: true`.
- Runs great under systemd or docker — it's a plain uvicorn app
  (`phone_server.server:app`).
