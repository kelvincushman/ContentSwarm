# ContentSwarm

## Mobile console

The server opens a workspace for tasks, phone preview, app controls, learned
flows and reply review for X, LinkedIn and Facebook. Compare the source with a
Humanizer-edited draft, approve it, or reject and rewrite. Approved replies wait
for an external agent to claim and deliver them.

Sign in at the server root with its separate owner console token. Read the
[console guide](dashboard/CONSOLE.md) for setup and delivery limits.

ContentSwarm is the Android phone kernel for AI agents. It exposes connected
phones through a JSON CLI and authenticated REST API, while keeping routine
device operations deterministic. A model is used only to understand an
unfamiliar interface or teach a reusable flow; app launch, screen inspection,
typing, tapping, swiping, messaging, and learned-flow replay run through code.

Developed by **Kelvin Lee** and released under Apache-2.0.

## Architecture

```text
Omarchy Assistant / Orphus / Pi (intent and language)
                 │
                 └─ contentswarm CLI ─HTTP─▶ ContentSwarm :5000/api/v1
                                               │
                         ┌─────────────────────┼──────────────────────┐
                         │                     │                      │
                  deterministic         learn once with        optional social
                  phone kernel          a vision model          content pipeline
                         │                     │                      │
                         └────────────── ADB + adb-agent-bridge ──────┘
                                               │
                                         Android phones
```

The separation is deliberate:

- **The brain understands the request.** Omarchy Assistant, Orphus, or Pi
  decides what should happen and asks for human approval where required.
- **ContentSwarm performs phone operations.** Its public boundary is the
  `contentswarm` CLI and `/api/v1`; agents do not import its Python modules.
- **adb-agent-bridge supplies constrained Android primitives.** It exposes the
  accessibility tree, semantic element taps, fast text entry, allowlisted keys
  and URI composers. It never exposes an arbitrary device shell.
- **Learn once, replay deterministically.** A vision model may demonstrate a
  new app flow once. Later runs use the recorded semantic targets and exact
  coordinates without a model.

See [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) for the component-level design and
[orphus/README.md](orphus/README.md) for agent integration.

## What it can do

- Control one to twenty Android phones with one operation lock per physical
  ADB device, shared by direct, synchronous, and asynchronous tasks.
- List devices, installed apps, connection state, and the foreground app.
- Launch registered apps directly.
- Read the current accessibility tree as structured JSON.
- Tap one unambiguous enabled element by text, resource id, or description.
- Type Unicode text, press allowlisted navigation keys, and swipe.
- Capture screenshots for pixel-level verification.
- Inspect SMS and WhatsApp, prepare a message without sending, and send a
  prepared message through a separately confirmed operation.
- Learn unfamiliar app workflows with a vision model and replay them without
  one.
- Run and verify repeatable social workflows for TikTok, Instagram, YouTube,
  X, Facebook, and LinkedIn.
- Track replay reports and verified-rate trends in SQLite.
- Operate through an authenticated API, JSON CLI, web dashboard, Orphus skill,
  or the Omarchy phone kernel.

## Safety contract

ContentSwarm separates preparation from commitment:

1. `compose` opens SMS or WhatsApp with the recipient and body filled in. It
   never taps Send.
2. The caller shows the exact action to the user and obtains approval.
3. `send --confirm` checks that the approved body is still in an enabled
   message editor, finds one enabled Send control, taps it once, and then
   checks that the composer cleared.
4. A state-changing tap such as Send, Delete, Post, Pay, Like, Follow, or Login
   also requires `--confirm`.

The kernel never blindly retries a state-changing action. A transport error
after a tap is reported as uncertain and must be inspected before another
attempt. API tokens stay in environment variables; message bodies and tokens
are omitted from emitted events.

ContentSwarm does not root a phone, bypass Android permissions, defeat app
login or multi-factor authentication, read private app databases, circumvent
end-to-end encryption, or capture screens protected by Android
`FLAG_SECURE`. SMS and WhatsApp access is through normal Android intents and
the visible accessibility tree.

## Quick start

### Requirements

- Linux with Python 3.10+ (the documented service and keyring setup targets Linux)
- Android Platform Tools (`adb`)
- One or more Android 7+ phones with USB debugging enabled
- [ADB Keyboard](https://github.com/senzhk/ADBKeyBoard) on each phone for fast
  Unicode text entry
- A vision-model endpoint only for `run` and `learn`

### Install and run locally

```bash
git clone https://github.com/kelvincushman/ContentSwarm
cd ContentSwarm
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r dashboard/requirements.txt
.venv/bin/pip install -e .

# Create phones_config.json using the example below, then:
# Store one random token in the desktop keyring, then reuse it for both sides.
python -c 'import secrets; print(secrets.token_urlsafe(32))' |
  secret-tool store --label="ContentSwarm API" service contentswarm account api-token
export CONTENTSWARM_API_TOKEN="$(secret-tool lookup service contentswarm account api-token)"
# Generate a separate owner credential; do not export it in agent shells.
python -c 'import secrets; print(secrets.token_urlsafe(32))' |
  secret-tool store --label="ContentSwarm Console" service contentswarm account console-token
export CONTENTSWARM_CONSOLE_TOKEN="$(secret-tool lookup service contentswarm account console-token)"
export CONTENTSWARM_HOST=127.0.0.1 CONTENTSWARM_COOKIE_SECURE=0
.venv/bin/python run_server.py
```

`phones_config.json` uses this shape:

```json
{
  "phones": [
    {
      "name": "primary",
      "device_id": "192.168.1.40:5555",
      "description": "Kelvin's Android phone",
      "tags": ["personal"]
    }
  ]
}
```

In another shell:

```bash
export CONTENTSWARM_API_URL="http://127.0.0.1:5000/api/v1"
export CONTENTSWARM_API_TOKEN="$(secret-tool lookup service contentswarm account api-token)"
contentswarm status
contentswarm discover
contentswarm phones
```

For a systemd deployment on a home server, follow
[deploy/AISERVER_SETUP.md](deploy/AISERVER_SETUP.md).

## Deterministic phone control

Every CLI command prints JSON and exits nonzero on failure.

```bash
contentswarm phones
contentswarm discover
contentswarm phone primary
contentswarm installed primary
contentswarm apps
contentswarm current primary
contentswarm launch primary WhatsApp
contentswarm ui primary
contentswarm screenshot primary -o /tmp/primary.png
```

Act on semantic elements whenever possible:

```bash
contentswarm tap primary --text Continue --confirm
contentswarm tap primary --id com.example:id/save --confirm
contentswarm type primary "A Unicode caption ✓"
contentswarm type primary " additional text" --append
contentswarm key primary BACK --confirm
contentswarm swipe primary 500 1600 500 500 --duration-ms 300
```

`tap` rejects zero matches, disabled controls, fuzzy selectors, and ambiguous
matches. Every tap requires `--confirm` so the caller asserts the exact action
it just sensed. Sensitive targets additionally require human approval in the
calling agent:

```bash
contentswarm tap primary --text Post --confirm
```

Every key event also requires `--confirm`. Because `ENTER` and `DPAD_CENTER`
can activate a focused control, callers must obtain human approval when that
control would send, post, delete, log in, or make a payment. Supported keys are
`BACK`, `HOME`, `ENTER`, `TAB`, `ESCAPE`, directional
DPAD keys, `DPAD_CENTER`, `DEL`, `FORWARD_DEL`, `PAGE_UP`, and `PAGE_DOWN`.
There is no raw-shell command.

## SMS and WhatsApp

Read the visible messaging screen:

```bash
contentswarm messages primary sms
contentswarm messages primary whatsapp
```

Prepare a message. Prefer a file or stdin so shell history does not retain its
contents:

```bash
BODY_FILE=$(mktemp)
TOKEN_FILE=$(mktemp)
trap 'rm -f "$BODY_FILE" "$TOKEN_FILE"' EXIT
chmod 600 "$BODY_FILE" "$TOKEN_FILE"
printf '%s' 'I will arrive at 09:00.' >"$BODY_FILE"
contentswarm compose primary sms +447700900123 \
  --body-file "$BODY_FILE" --token-file "$TOKEN_FILE"

printf '%s' 'The appointment is confirmed.' |
  contentswarm compose primary whatsapp +447700900123
```

After the user approves the exact recipient and body, send the prepared draft:

```bash
contentswarm send primary sms +447700900123 \
  --expect-body-file "$BODY_FILE" --prepared-token-file "$TOKEN_FILE" --confirm
```

Composition verifies the body in the editor and the recipient in a separate
recipient-specific UI element; editor text never counts as recipient proof. If Android
shows a saved contact name instead of its number, add `--recipient-label` with
that exact visible name. It returns a five-minute, single-use token bound to
the phone, channel, recipient, and body; `--token-file` keeps it out of output.

The send result contains `sent`, `verified`, and `verification`. A successful send
requires the same enabled editor to remain visible with an empty value. If the
composer disappears, the result stays unverified. For stronger
proof, inspect the conversation or take a screenshot after sending.

## Social media

ContentSwarm ships app skills for TikTok, Instagram, YouTube, X, Facebook, and
LinkedIn. Use the deterministic ladder:

1. Inspect with `ui` and use `launch`, `tap`, `type`, `key`, and `swipe` for a
   short known operation.
2. Check `contentswarm flows` for an existing learned workflow.
3. Replay a known flow with no model.
4. Use `learn` when the workflow is new and will recur.
5. Use `run` only for a one-off, open-ended task.

```bash
contentswarm installed primary
contentswarm learn primary \
  "Open Instagram, reach the new-post caption screen, then stop" \
  --name instagram-open-caption --wait
contentswarm replay primary instagram-open-caption --wait
contentswarm runs instagram-open-caption
contentswarm health instagram-open-caption --days 7
```

Posting, commenting, liking, following, sharing, logging in, deleting, and
buying require approval in the calling agent. A learned flow that reaches a
commit button should end before that button; use one confirmed semantic tap
for the final action.

The optional content pipeline is retained for discovery, analysis, generation,
and distribution. It is separate from the phone kernel and should be enabled
only when its external generation and analysis providers are configured. See
[VIRAL_CONTENT_GUIDE.md](VIRAL_CONTENT_GUIDE.md).

## Learn once, replay without AI

During `learn`, `PhoneAgent` uses a compatible vision model to navigate an app.
The recorder stores successful actions in resolution-independent coordinates
and stores the text, id, and description of tapped elements when available.

During `replay`, ContentSwarm:

- looks for the recorded semantic element at its current location;
- taps its current center when found;
- falls back to the recorded coordinate when necessary;
- records whether each step was semantic and verified or a coordinate fallback;
- never calls the vision model.

Flows live under `CONTENTSWARM_FLOWS_DIR` (default `flows/`). Run reports and
the SQLite health index live under `<flows_dir>/runs/`. Back up this directory:
it is the fleet's learned operational knowledge.

## REST API

The server exposes these routes below `/api/v1`:

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/status` | Server, fleet, pipeline, and bridge state |
| `GET` | `/phones` | List configured phones and connections |
| `POST` | `/phones/discover` | Scan authorized ADB devices and persist new phones |
| `GET` | `/phones/<phone>` | One phone |
| `POST` | `/phones/<phone>/app` | Launch a registered app |
| `GET` | `/phones/<phone>/current_app` | Foreground package |
| `GET` | `/phones/<phone>/installed` | Third-party packages |
| `GET` | `/phones/<phone>/ui` | Accessibility elements |
| `GET` | `/phones/<phone>/screenshot` | PNG screenshot |
| `POST` | `/phones/<phone>/action` | Tap, type, key, or swipe |
| `GET` | `/phones/<phone>/communications/<channel>` | Inspect SMS or WhatsApp |
| `POST` | `/phones/<phone>/communications/compose` | Prepare a message |
| `POST` | `/phones/<phone>/communications/send` | Confirm and send prepared message |
| `POST` | `/phones/<phone>/task` | Asynchronous one-off vision task |
| `POST` | `/phones/<phone>/learn` | Teach and record a flow |
| `POST` | `/phones/<phone>/replay` | Deterministically replay a flow |
| `GET` | `/tasks`, `/tasks/<id>` | Task status |
| `GET` | `/flows`, `/flows/<name>` | Flow inventory and details |
| `GET` | `/flows/<name>/runs` | Replay reports |
| `GET` | `/flows/health`, `/flows/<name>/health` | Verified-rate health |

When `CONTENTSWARM_API_TOKEN` is set, every route requires
`Authorization: Bearer <token>`. Production deployments should always set it
and restrict port 5000 to the local network or a private overlay network such
as NetBird.

Example:

```bash
curl -sS \
  -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" \
  "$CONTENTSWARM_API_URL/phones"

curl -sS -X POST \
  -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"action":"key","key":"BACK"}' \
  "$CONTENTSWARM_API_URL/phones/primary/action"
```

## Vision model configuration

Only `run` and `learn` need a model. Configure an OpenAI-compatible endpoint:

```bash
export PHONE_AGENT_BASE_URL="http://localhost:8000/v1"
export PHONE_AGENT_MODEL="autoglm-phone-9b"
export PHONE_AGENT_API_KEY="EMPTY"
export PHONE_AGENT_MAX_STEPS="100"
export PHONE_AGENT_LANG="en"
```

The service starts without a phone or reachable model, so its deterministic
status API can still be tested. Model failures affect only model-backed tasks.

## Omarchy and Orphus

The Omarchy Assistant integration runs ContentSwarm as a user service and
exposes a smaller `omarchy-phone-kernel` command to its voice brain. The kernel
retrieves the API token from the desktop keyring, applies the Omarchy approval
menu to sends and other state-changing actions, and then invokes this CLI.

The `orphus/` directory contains phone and communications skills, per-app
social skills, a phone-operator definition, a multi-phone fleet blueprint, and
an installer for `~/.orphus/agent` or a Pi-compatible directory. Run
`./orphus/install.sh`, then see [orphus/README.md](orphus/README.md).

## Development and review

```bash
python -m compileall -q phone_agent dashboard contentswarm_cli.py run_server.py main.py
python -m pytest -q
python contentswarm_cli.py --help
```

Every repository change uses a feature branch and includes its documentation.
CodeRabbit reviews the pull request and GPT Sol is the final gate before merge.
The exact contributor and agent rules are in [CLAUDE.md](CLAUDE.md).

## Related documentation

- [System overview](SYSTEM_OVERVIEW.md)
- [AI server setup](deploy/AISERVER_SETUP.md)
- [Orphus and Pi integration](orphus/README.md)
- [Phone pool guide](PHONE_POOL_GUIDE.md)
- [Flow-learning skill](orphus/skills/contentswarm-flow-learning/SKILL.md)
- [Communications skill](orphus/skills/contentswarm-communications/SKILL.md)
- [Social content pipeline](VIRAL_CONTENT_GUIDE.md)
- [adb-agent-bridge](https://github.com/kelvincushman/adb-agent-bridge)
