# ContentSwarm for Orphus and Pi

Orphus or Pi is the brain; ContentSwarm is the Android execution layer. Agents
use the `contentswarm` JSON CLI, which talks to the authenticated REST API.
They never import ContentSwarm modules or invoke raw ADB.

```text
request
  └─ Orphus/Pi phone-operator
       ├─ skill: choose safe command and approval boundary
       └─ bash: contentswarm … ─HTTP─▶ ContentSwarm ─ADB─▶ phone
```

## Included integration

| Path | Purpose |
|---|---|
| `skills/contentswarm-phones/` | Fleet discovery, app launch, screenshots, and tasks |
| `skills/contentswarm-bridge/` | Semantic UI sensing and direct deterministic actions |
| `skills/contentswarm-communications/` | SMS/WhatsApp inspect, compose, approve, send, verify |
| `skills/contentswarm-flow-learning/` | Teach once, replay without a model |
| `skills/contentswarm-app-*/` | TikTok, Instagram, YouTube, X, Facebook, and LinkedIn guidance |
| `skills/contentswarm-skill-maker/` | Explore a new app and create a reusable skill |
| `agents/phone-operator.md` | Dedicated constrained phone operator |
| `agents/worker.md` | Repository implementation worker |
| `agents/final-gate.md` | GPT Sol review gate |
| `fleets/contentswarm.fleet.yaml` | Multi-phone planning and execution fleet |
| `install.sh` | User-level installer |

## Install

From the ContentSwarm checkout:

```bash
./orphus/install.sh
python -m pip install -e .
export CONTENTSWARM_API_URL="http://<server>:5000/api/v1"
export CONTENTSWARM_API_TOKEN="<server token>"
contentswarm status
```

The installer defaults to `~/.orphus/agent`. Plain Pi uses the same artifacts:

```bash
ORPHUS_CODING_AGENT_DIR="$HOME/.pi/agent" ./orphus/install.sh
```

ContentSwarm can also expose its skill directory as an Orphus package by adding
the checkout to the harness settings:

```json
{ "packages": ["/path/to/ContentSwarm"] }
```

The copy installer is still required for the agent and fleet definitions.

## Operating ladder

The phone operator should choose the first rung that can complete the task:

1. `phones`, `installed`, `current`, or `ui` to sense structured state.
2. `launch`, `tap`, `type`, `key`, or `swipe` for one constrained action.
3. `messages`, `compose`, and approved `send` for SMS or WhatsApp.
4. `replay` for an existing healthy flow.
5. `learn` for a new workflow that will recur.
6. `run` for a one-off task that needs visual reasoning.
7. A screenshot for rendered evidence or when accessibility data is thin.

This order keeps routine execution cheap, inspectable, and repeatable. The
vision model is a teacher and fallback, rather than the default actuator.

## Approval boundaries

The agent must stop and obtain explicit approval immediately before:

- login or submitting multi-factor authentication;
- payment or purchase;
- sending SMS, WhatsApp, email, or another external message;
- posting, commenting, liking, following, subscribing, sharing, or reposting;
- deleting or removing content or data.

The user should see the account or recipient, action, and content before
approval. After approval, execute once and verify through a fresh UI dump or
screenshot. A timeout after an action is uncertainty; inspect before retrying.

For messages, `compose` cannot send and the API independently requires
`confirm: true` for `send`. For social flows, learn and replay up to the final
commit control and use one confirmed semantic tap for the commit.

## Example: WhatsApp

```bash
contentswarm phones
contentswarm messages primary whatsapp

umask 077
printf '%s' 'I will arrive at 09:00.' >/tmp/approved-message.txt
contentswarm compose primary whatsapp +447700900123 \
  --body-file /tmp/approved-message.txt

# Show the exact recipient/body and obtain user approval here.
contentswarm send primary whatsapp \
  --expect-body-file /tmp/approved-message.txt --confirm
contentswarm messages primary whatsapp
rm -f /tmp/approved-message.txt
```

Only report a send when the JSON result has `"verified": true`. A cleared
composer proves UI submission, not network delivery or recipient receipt.

## Example: reusable social post

```bash
contentswarm flows
contentswarm learn primary \
  "Open Instagram, select the newest image, reach the caption screen, then stop" \
  --name instagram-prepare-post --wait
contentswarm replay primary instagram-prepare-post --wait
contentswarm type primary "Final approved caption"

# Obtain approval, then:
contentswarm tap primary --text Share --confirm
contentswarm ui primary
contentswarm screenshot primary -o /tmp/instagram-result.png
```

Do not record Share inside the reusable flow.

## Model routing

| Role | Primary | Fallbacks |
|---|---|---|
| Main coding worker | `openai-codex/gpt-5.6-terra:max` | `gpt-5.6-luna:max` → `zai/glm-5.2` → `moonshot/kimi-k3` |
| Phone operator | `openai-codex/gpt-5.6-terra:medium` | `gpt-5.6-luna:medium` → `zai/glm-5.2` → `moonshot/kimi-k3` |
| Final gate | `openai-codex/gpt-5.6-sol:max` | `gpt-5.6-terra:max` → `zai/glm-5.2` |

The phone vision model configured in ContentSwarm is separate. It is called by
`learn` and `run`, while direct actions, communication operations, and replay
use no model.

## Repository review pipeline

Every change follows this sequence:

1. feature or fix branch;
2. implementation and synchronized docs/skills;
3. pull request into `main`;
4. CodeRabbit review;
5. GPT Sol final gate;
6. merge only after both approve.

The authoritative rules are in [../CLAUDE.md](../CLAUDE.md).

## Android limits

The operator sees only what normal ADB, accessibility, screenshots, and Android
intents expose. It cannot bypass app sandboxes, end-to-end encryption,
authentication, captchas, or protected screenshots. A user may need to unlock
the phone, grant a permission, or complete a login directly on the device.
