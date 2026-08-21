# Driving ContentSwarm from Orphus

[Orphus](https://github.com/kelvincushman/orphus) is the main driver: its
agents control the ContentSwarm phone fleet through the `contentswarm` CLI.
ContentSwarm's only job here is the mobile phone interface — multi-device
control and app control.

```
Orphus agents (phone-operator, fleets)
   └─ bash → contentswarm CLI ──HTTP──▶ ContentSwarm API :5000/api/v1
                                            └─ PhoneAgent (vision) ─ADB─▶ phones
```

## What's in this directory

| Path | Purpose |
|---|---|
| `skills/contentswarm-phones/` | Agent Skill: device + app control via the CLI |
| `skills/contentswarm-pipeline/` | Agent Skill: optional content-pipeline control |
| `skills/contentswarm-app-{tiktok,instagram,youtube,twitter,facebook}/` | Per-app skills with verified flows — load only when that app is involved |
| `skills/contentswarm-skill-maker/` | Skill generator: explores an unfamiliar app on a real phone and writes a new `contentswarm-app-<name>` skill |
| `agents/phone-operator.md` | Orphus agent definition for phone work |
| `fleets/contentswarm.fleet.yaml` | Fleet blueprint: strategy huddle → parallel execution |
| `install.sh` | Copies the above into `~/.orphus/agent/` |

Skills are on-demand by design: only each skill's one-line description sits in
the agent's context; the body loads only when the agent actually works with
that app. New apps get covered by running the skill-maker once
("make a skill for the Reddit app") — it explores the app with screenshots and
writes a new skill from its template.

## Install — option A: user-level copy

```bash
./orphus/install.sh
```

Copies skills, the agent, and the fleet into `~/.orphus/agent/{skills,agents,fleets}/`
so every Orphus session can use them.

## Install — option B: load ContentSwarm as an Orphus package

The repo root has a `package.json` with an `orphus` manifest key exposing the
skills. Add the checkout path to your Orphus `settings.json`:

```json
{ "packages": ["/path/to/ContentSwarm"] }
```

(Skills load this way; the agent and fleet still need copying into
`.orphus/agents/` and `.orphus/fleets/` — `install.sh` does both.)

## Configure the Orphus machine

```bash
# The ContentSwarm server (your AI server's LAN IP, or however you reach it):
export CONTENTSWARM_API_URL="http://<server-ip>:5000/api/v1"
export CONTENTSWARM_API_TOKEN="<token>"     # if the server sets one

# Install the CLI:
pip install -e /path/to/ContentSwarm        # provides the `contentswarm` command
contentswarm status                         # smoke test
```

## Use it

- Any Orphus session with the skills installed can drive phones directly:
  the model reads `contentswarm-phones` and calls the CLI via bash.
- Dispatch the dedicated agent: `subagent({ agent: "phone-operator", task: "…" })`.
- Run the fleet for multi-phone campaigns: `/fleet contentswarm <request>` —
  a deliberation team agrees a per-phone plan, then three phone-operators
  execute it in parallel.
