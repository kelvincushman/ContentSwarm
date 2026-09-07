# ContentSwarm system overview

ContentSwarm is a constrained Android execution service. Agent harnesses own
language, planning, and user interaction. ContentSwarm owns device identity,
serialization, actions, learned flows, and verification evidence.

## Components

```text
voice/text request
      │
      ▼
Omarchy Assistant / Orphus / Pi
      │  JSON CLI contract
      ▼
contentswarm CLI
      │  bearer-authenticated HTTP
      ▼
Flask API blueprint ────────────────────────────────┐
      │                                             │
      ├─ deterministic routes                       ├─ model-backed routes
      │   app, current, ui, action,                  │   task, learn
      │   screenshot, communications                │
      │                                             │
      ├─ flow routes                                └─ optional content pipeline
      │   replay, reports, health
      ▼
PhonePoolManager + per-device bridge lock
      │
      ├─ phone_agent.adb: app launch and screenshots
      ├─ adb-agent-bridge: tree, tap, text, key, swipe, URI composers
      └─ FlowReplayer: semantic target then coordinate fallback
      ▼
Android Debug Bridge
      ▼
one to twenty Android phones
```

## Responsibility boundaries

| Layer | Owns | Does not own |
|---|---|---|
| Agent brain | Understanding, planning, reply text, approval dialogue | Direct ADB or ContentSwarm module imports |
| Omarchy phone kernel | Keyring token lookup, approval UI, constrained command routing | Phone UI implementation |
| CLI and REST API | Stable JSON contract, validation, HTTP auth | Natural-language interpretation |
| PhonePoolManager | Device registry, async tasks, per-phone task locks | User consent |
| Deterministic bridge | Semantic sensing and allowlisted actions | Arbitrary device shell |
| Vision agent | First-time/open-ended UI navigation and flow teaching | Routine replay |
| Flow replayer | Repeat execution and step reports | Replanning a changed app |

## Deterministic control

`phone_agent/bridge.py` wraps
[adb-agent-bridge](https://github.com/kelvincushman/adb-agent-bridge). It caches
one bridge per device and serializes bridge calls with one lock per device.
The exposed operations are intentionally finite:

- inspect accessibility elements;
- tap exactly one enabled, clickable semantic match;
- type at most 4,000 characters;
- press a navigation/editing key from an allowlist;
- swipe within validated coordinates and duration;
- open validated SMS and WhatsApp composers;
- send a prepared message after verifying the approved body.

No route accepts a shell command, Android intent action, arbitrary URI scheme,
or application package from the caller.

## Communications transaction

```text
inspect ─▶ compose(recipient, body) ─▶ external user approval
                                             │
                                             ▼
                                send(confirm=true, expected_body)
                                             │
                   ┌─────────────────────────┼─────────────────────────┐
                   │                         │                         │
             body matches             one Send control          otherwise stop
                   │                         │
                   └──────────── tap exactly once
                                             │
                                      inspect again
                                             │
                            composer cleared = verified
```

Composition and send are separate routes. A successful composition checks the
live recipient and exact body, then returns a five-minute, single-use token
bound to the device, channel, recipient, and body hash. A new composition on
the device invalidates its earlier token. Send consumes the token before its
one state-changing attempt and independently checks the live composer.

The API requires the literal JSON boolean `confirm: true`. The CLI requires
`--confirm`. The Omarchy wrapper adds a desktop Allow/Deny menu before invoking
that CLI flag. The API does not emit recipients, tokens, or message bodies to
its event stream.

## Social workflows

Social apps use the same ladder:

1. semantic primitives for short known steps;
2. a deterministic replay when a flow exists;
3. a vision-backed `learn` for a reusable unknown flow;
4. a vision-backed `task` only for an unrepeated open-ended job.

Flows should stop before Post, Send, Delete, Pay, Follow, Like, Share, or other
external commitments. The calling agent obtains approval and commits with one
confirmed semantic tap. This preserves deterministic replay while keeping the
user at the irreversible boundary.

## Flow data and verification

The learning recorder stores actions in a 0–1000 coordinate space and records
the semantic identity of tapped elements. During replay, the current semantic
match wins; recorded coordinates are a fallback. Each run report records
whether a step used an element or coordinates. The SQLite run index aggregates
verified rates over time so app changes can trigger re-learning.

Flow files live under `CONTENTSWARM_FLOWS_DIR`; reports and the index live in
its `runs/` child. Treat the directory as operational data and back it up.

## API security

- Set `CONTENTSWARM_API_TOKEN`; clients send it as a bearer token.
- Keep the service on localhost, a trusted LAN, or a private overlay network.
- Use HTTPS at the reverse proxy when traffic crosses an untrusted network.
- Environment variables hold server and model credentials. They do not belong
  in source, phone configuration, flow files, events, or logs.
- Sensitive taps and all message sends require explicit confirmation in the
  API contract. Agent integrations must also obtain human approval.
- State-changing actions run once. A failure after the action remains
  uncertain until the phone is inspected.

## Android boundary

ADB access is powerful but finite. ContentSwarm can operate what Android
exposes through accessibility, screenshots, app launch, input, and intents. It
cannot read another app's private storage on an unrooted phone, bypass
encryption or authentication, recover hidden WhatsApp message data, or capture
`FLAG_SECURE` screens. This is visible UI automation, not a privilege bypass.

## Key files

| Path | Purpose |
|---|---|
| `contentswarm_cli.py` | JSON command-line client |
| `phone_agent/api.py` | Authenticated REST routes |
| `phone_agent/bridge.py` | Deterministic UI and communications kernel |
| `phone_agent/phone_pool.py` | Phone registry, locks, and async tasks |
| `phone_agent/flows.py` | Learn and replay engine |
| `phone_agent/runs_index.py` | SQLite replay-health index |
| `phone_agent/agent.py` | Vision-backed phone agent |
| `phone_agent/social_automation.py` | Optional content pipeline |
| `run_server.py` | API and dashboard entry point |
| `orphus/` | Agent skills, operator, and fleet definitions |
| `deploy/` | Systemd deployment assets |
| `tests/` | Deterministic bridge and API contract tests |

## Operating modes

| Mode | Model use | Typical command |
|---|---:|---|
| Inspect or direct action | none | `ui`, `tap`, `type`, `key`, `swipe` |
| Messaging | none | `messages`, `compose`, `send` |
| Known workflow | none | `replay` |
| New reusable workflow | once | `learn` |
| One-off open-ended task | per task | `run` |
| Optional content pipeline | provider-dependent | pipeline API routes |

For installation and command examples, read [README.md](README.md). For remote
deployment, read [deploy/AISERVER_SETUP.md](deploy/AISERVER_SETUP.md).
