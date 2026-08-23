# ContentSwarm System Overview

**The mobile phone interface for AI agents** — multi-device control and app
control across a fleet of up to 20 Android phones. Developed by Kelvin Lee.

## Architecture

```text
Orphus / Pi agents (the brain — strategy, deliberation)
   └─ bash → contentswarm CLI ──HTTP──▶ ContentSwarm server :5000
                                          ├─ /api/v1  REST API (bearer token)
                                          ├─ Web dashboard + screen streaming
                                          ├─ PhonePoolManager (parallel, per-phone locks)
                                          ├─ Flow engine: learn (LLM) / replay (element-targeted presses)
                                          ├─ Semantic bridge: UI element tree, element taps, instant text
                                          ├─ Run reports + SQLite health index (verified-rate per flow)
                                          ├─ PhoneAgent (vision model, learning only)
                                          └─ ADB ──USB / TCP──▶ phones
```

| Layer | Component | Role |
|---|---|---|
| Brain | [Orphus](https://github.com/kelvincushman/orphus) or Pi | Decides WHAT to do; drives everything via the CLI |
| Interface | `contentswarm` CLI + `/api/v1` | The contract between brain and phones |
| Orchestration | `PhonePoolManager` | Parallel task execution, per-phone locking, task tracking |
| Learning | `PhoneAgent` + `FlowRecorder` | Vision model drives an app once; every action recorded with the element under each tap |
| Execution | `FlowReplayer` + `ActionHandler` | Deterministic replay — element-targeted presses (coordinate fallback), no LLM; each replay writes a run report |
| Sensing | `phone_agent/bridge.py` + [adb-agent-bridge](https://github.com/kelvincushman/adb-agent-bridge) | UI element tree over plain ADB (`contentswarm ui`), semantic taps, ~100ms text |
| Devices | ADB (USB or TCP) | Screenshots, taps, swipes, typing, app launch |

## The core pattern: learn once, replay forever

1. **Discover** — `contentswarm installed phone_01` lists apps on the device
2. **Learn** — `contentswarm learn phone_01 "<task>" --name <flow>`: the
   vision-language model figures out the app while each successful action is
   recorded with resolution-independent press points (0-1000 space)
3. **Replay** — `contentswarm replay <any-phone> <flow>`: the deterministic
   driver taps the recorded element wherever it now sits, falling back to the
   recorded coordinates. Fast, repeatable, zero model cost.
4. **Verify** — every replay writes a run report (`contentswarm runs <flow>`):
   per step, did it succeed and did it hit the intended element. Reports are
   indexed into SQLite; `contentswarm health <flow>` shows the verified-rate
   trend — when it drops after an app update, re-learn before it misclicks.

Flows are JSON files under `CONTENTSWARM_FLOWS_DIR` (default `flows/`); run
reports and the health index live under `<flows_dir>/runs/`.

## Key modules

| Path | Purpose |
|---|---|
| `contentswarm_cli.py` | Agent-native CLI (JSON out, exit codes) |
| `phone_agent/api.py` | REST API blueprint (`/api/v1`), bearer-token auth |
| `phone_agent/phone_pool.py` | Pool manager: `async_run`, `async_learn`, `async_replay`, batch |
| `phone_agent/flows.py` | Flow record/replay engine, run reports, app discovery |
| `phone_agent/bridge.py` | Semantic UI bridge: element taps, instant text, UI dumps (auto-fallback) |
| `phone_agent/runs_index.py` | SQLite health index over run reports (`/flows/health`) |
| `phone_agent/agent.py` | Vision-agent loop (screenshot → model → action) |
| `phone_agent/actions/handler.py` | Action execution (tap/swipe/type/launch/…) |
| `phone_agent/adb/` | Device I/O: screenshots, input, connection |
| `phone_agent/social_automation.py` | Optional pipeline: discover → analyze → generate → post |
| `dashboard/` | Web UI: monitoring, control, live screen streaming |
| `run_server.py` | Server entry point (API + dashboard) |
| `orphus/` | Skills, agents, fleet blueprint for the Orphus/Pi harness |
| `deploy/` | systemd unit, installer, AI-server setup guide |

## Content generation

External by design — bring your own generation API (e.g. Kie.ai, Veo3) and
wire it into the pipeline's generate stage. ContentSwarm itself only handles
the phones.

## Vision model (learning only)

The `learn` path needs an AutoGLM-compatible vision model at
`PHONE_AGENT_BASE_URL` — hosted (z.ai, Novita, Parasail) or self-hosted
(vLLM/SGLang on a local GPU). Replays never touch the model.

## Security & process

- `/api/v1` requires `Authorization: Bearer $CONTENTSWARM_API_TOKEN` when the
  server sets that env var; production serves via eventlet, and the Werkzeug
  dev fallback binds to localhost only
- Every change to this repo goes through the review gate: CodeRabbit review,
  then **GPT Sol as the final gate** — see [CLAUDE.md](CLAUDE.md)

## Further reading

- [README.md](README.md) — quick starts and feature overview
- [orphus/README.md](orphus/README.md) — driving the fleet from Orphus/Pi, model routing
- [deploy/AISERVER_SETUP.md](deploy/AISERVER_SETUP.md) — home-server install runbook
- [PHONE_POOL_GUIDE.md](PHONE_POOL_GUIDE.md) — multi-phone management
- [VIRAL_CONTENT_GUIDE.md](VIRAL_CONTENT_GUIDE.md) — optional content pipeline strategy
