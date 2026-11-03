# ContentSwarm for Orphus and Pi

Use the [social review skill](skills/contentswarm-social-review/SKILL.md) for
X, LinkedIn, Facebook and Instagram replies. It includes Humanizer 3.0.0 and documents
`reviews`, `review-add`, and `review-action` for the human-reviewed handoff.

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
export CONTENTSWARM_API_URL="https://<server>/api/v1"
export CONTENTSWARM_API_TOKEN="<server token>"
contentswarm status
```

Use HTTPS for remote API access. HTTP is only for a loopback endpoint, including
the local end of an encrypted tunnel. The installer defaults to `~/.orphus/agent`.
Plain Pi uses the same artifacts:

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

1. `discover`, `phones`, `installed`, `current`, or `ui` to enroll and sense structured state.
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
BODY_FILE=$(mktemp)
TOKEN_FILE=$(mktemp)
trap 'rm -f "$BODY_FILE" "$TOKEN_FILE"' EXIT
printf '%s' 'I will arrive at 09:00.' >"$BODY_FILE"
contentswarm compose primary whatsapp +447700900123 \
  --body-file "$BODY_FILE" --token-file "$TOKEN_FILE"

# Show the exact recipient/body and obtain user approval here.
contentswarm send primary whatsapp +447700900123 \
  --expect-body-file "$BODY_FILE" --prepared-token-file "$TOKEN_FILE" --confirm
contentswarm messages primary whatsapp
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
# Account context and scheduled social work

Use `contentswarm social accounts`, `social context --account ID --query WORDS`,
`social remember --account ID --file FILE`, `social schedules`, `social jobs`
and `social tick`. All use the REST boundary. Account identity and recurrence
are edited by the owner in the console; agents append untrusted observations.
Read [the social guide](../dashboard/SOCIAL.md) and the
`contentswarm-social-review` skill before drafting or delivering.

Owner-created social jobs and schedules support `kind: "reply"` with `source_url`,
`author`, and `original`. These fields survive scheduling and model drafting into
the pending review; the model cannot replace the recipient/source metadata.
See [contextual reply drafts](../dashboard/SOCIAL.md#contextual-reply-drafts).

Semantic phone taps support labels nested inside enabled clickable controls.
The API's UI elements expose dump-local `parent_index` values from the ADB bridge.
Use semantic selectors as before; do not convert parent indices into cached
coordinates, infer parents from overlap, or treat a tap result as delivery proof.

Owner account configuration can select `delivery_adapter: "x-accessibility-v1"`
for an X profile. The timer then uses deterministic phone calls for approved
original text posts, retaining review leases and the global delivery opt-in.
With that adapter, approved X replies are delivered too: the worker finds the
comment under Mentions by its exact author and text and checks the reply
composer before one send. `delivery_adapter: "linkedin-accessibility-v1"` does
the same for original LinkedIn text posts, with the member name as the handle.
Media and LinkedIn replies are not automated. Semantic taps accept `within`
(the exact text of one element) to pick one post's control in a list. See
[the supported X screens and verification](../dashboard/SOCIAL.md#x-accessibility-adapter).

For device-local time, use `contentswarm clock PHONE` (GET
`/api/v1/phones/PHONE/clock`): returns ISO time with UTC offset and epoch.
X's experimental publication fallback uses blind tool-free screenshot reading
when accessibility omits post content. The kernel checks exact account/text
(whitespace wrapping folded) and matches the visible timestamp against device
time. It never retries Send; uncertain outcomes require inspection. New-post
publication has not yet been validated live; keep automatic delivery disabled.

`contentswarm current PHONE` / GET `/api/v1/phones/PHONE/current_app` includes `package`:
the exact focused Android package, or null during missing focus. It never reports
an underlying activity as the focused app. X verification prefers metadata from
the native Android share preview and returns without choosing a recipient; image
reading is a fallback only when metadata is absent, never when it mismatches.

Instagram profiles support scoped soul/knowledge, scheduled caption or reply drafting, and owner review. Source links must use instagram.com. Media selection/upload and automatic comment delivery are not yet implemented; the legacy text-only delivery loop rejects Instagram before opening the app. Review approval alone does not publish anything.

## Task outcomes and stops

`run`, `learn` and `replay` report `pending`, `running`, `completed`, `failed`,
`cancelled` or `timeout`. Failures keep a reason. The CLI `--wait` exits nonzero
for failed/cancelled/timed-out tasks. `outcome_verified: false` means the worker
has not independently proved the user's goal: inspect fresh `ui` and screenshot
output. Replay's `verified` count measures matched input targets, not publication
or business outcomes.

- `contentswarm cancel-task TASK_ID --confirm` requests a cooperative stop
  (`POST /api/v1/tasks/TASK_ID/cancel`, body `{"confirm":true}`).
- A running cancellation returns `cancel_requested: true`; it retains the phone
  lock until the running operation returns and checks the stop. It cannot undo
  any input already sent. Never restart an uncertain send.
- Async phone tasks have a five-minute deadline by default (manager constructor
  `task_timeout`, seconds, including queue time). Checks occur before model/input
  steps and after model responses, not by killing threads mid-action. Model HTTP
  requests use `ModelConfig.request_timeout` (60 seconds) with no SDK retries.
  These are cooperative bounds: blocked drivers and an active stream can delay
  acknowledgement. No hard cancellation guarantee is made.
- Background sensitive confirmations fail closed instead of waiting on stdin;
  human takeover/choice requests become actionable failures. Replays never grant
  sensitive-action approval, and stop on the first failed step. Failed/empty
  learning is not saved as a reusable flow. Missing semantic targets do not
  fall back to old coordinates. Missing/protected screenshots stop input.
- `POST /api/v1/pipeline/discover` now returns `task_id`. Poll `/tasks/ID` or list
  `/tasks` for its result/error. Discovery cancellation is not implemented and
  returns 409. Task history is process-local, not durable across server restart.

The definitions here are shipped repo configuration, not evidence that the live
Phone bot loaded them. The host agent's tool/policy config may be stricter.
Social approval belongs to an exact reviewed item and the approved sender path;
it is not a general grant for a navigation bot to tap Post. Read
[the social handoff](skills/contentswarm-social-review/SKILL.md). Keep a stricter
host prohibition intact and report the review ID/status to the sender instead
of repeatedly composing, re-approving or bypassing it.

Screen capture failures (including nonzero ADB capture/pull exits) return an
error, not a successful black screenshot. Ambiguous/disabled semantic targets
are rejected. A response lost after typing/tapping is terminal, with no legacy
fallback retry. Recorded confirmation markers survive learning and are denied
on replay; older flows whose markers were stripped need manual inspection or
re-learning. Semantic Double Tap/Long Press is unsupported and fails closed.
Known remaining limit: the recorder's asynchronous UI prefetch is not a full
before/after outcome proof; existing coordinate-only flows can become stale.

### Reviewed reliability release

Discovery lifecycle events now include the same `status` and
`outcome_verified` fields as polling. A broken event transport cannot corrupt
the actual operation result. Missing typing bridge now returns a terminal
capability error without unchecked legacy IME input. See the
[review/rollout/rollback gate](../deploy/PHONE_RELIABILITY_ROLLOUT.md) before
updating a running installation. No definition is installed or authority
expanded merely by changing this checkout.
