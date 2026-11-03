---
name: contentswarm-phones
description: Control a fleet of Android phones through the ContentSwarm API - list devices, launch apps, run natural-language UI tasks, capture screenshots, and check task results. Use when the user wants to operate mobile devices or drive mobile apps.
---

# ContentSwarm Phone Control

ContentSwarm exposes a fleet of up to 20 Android phones. Each phone runs an AI
vision agent that can navigate apps, tap, swipe, and type to complete
natural-language tasks. You drive it with the `contentswarm` CLI (preferred)
or raw `curl` via the bash tool.

## Setup

Required environment (set on the machine running Orphus):

```bash
export CONTENTSWARM_API_URL="https://<server-domain>/api/v1"   # HTTPS proxy; loopback HTTP is also supported
export CONTENTSWARM_API_TOKEN="<token>"                        # required agent credential
```

If the `contentswarm` command is missing, install it:
`pip install -e /path/to/ContentSwarm` (or `pipx install /path/to/ContentSwarm`).

Never echo or print `CONTENTSWARM_API_TOKEN`.

## Commands

All commands print JSON and exit 0 on success, 1 on failure.

### Check the system

```bash
contentswarm status        # phones online, pipeline state
contentswarm discover      # scan authorized ADB devices and persist new phones
contentswarm phones        # every phone: name, device_id, connected, tags
contentswarm phone phone_01
```

### Deterministic device control (fast, no LLM)

```bash
contentswarm apps                       # apps launchable by name
contentswarm launch phone_01 TikTok     # launch app directly via ADB
contentswarm current phone_01           # foreground app
contentswarm ui phone_01                # UI element tree - text/id/desc/center per element
contentswarm screenshot phone_01 -o screen.png   # see the screen - read the PNG after
contentswarm tap phone_01 --text Continue --confirm
contentswarm tap phone_01 --desc Reply --within "exact post text" --confirm   # one post's control
contentswarm open-url phone_01 https://x.com/UKKelvinLee   # opens in the X app; x.com and linkedin.com only
contentswarm type phone_01 "hello"
contentswarm key phone_01 BACK --confirm
contentswarm swipe phone_01 500 1600 500 500
```

Prefer `ui` over `screenshot` to check what is on screen: it returns every
element's text and position as JSON (grep/jq it), needs no vision model, and
is exact. Use `screenshot` when the tree is thin (games, canvas UIs) or you
need rendered content - see the `contentswarm-bridge` skill.

### Natural-language tasks (vision agent, async)

```bash
# Submit and wait for completion (tasks take 5-120+ seconds):
contentswarm run phone_01 "Open TikTok, search for 'bushcraft', describe the top 3 videos without engaging" --wait

# Fire-and-forget, then poll:
contentswarm run phone_01 "Open Instagram and scroll Reels for a minute"
contentswarm task <task_id>       # status: pending | running | completed | failed | cancelled | timeout
contentswarm tasks                # everything tracked
contentswarm cancel-task <task_id> --confirm  # request stop, not rollback
```

### Parallel across phones

```bash
contentswarm batch \
  -t phone_01="Open TikTok and scroll trending" \
  -t phone_02="Open Instagram Reels" \
  -t phone_03="Open YouTube Shorts" \
  --wait
```

Each phone runs one task at a time (per-phone lock). Submitting to a busy
phone fails - check `contentswarm tasks` first.

## curl fallback

```bash
curl -s -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" "$CONTENTSWARM_API_URL/phones"
curl -s -X POST -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"task": "Open TikTok"}' "$CONTENTSWARM_API_URL/phones/phone_01/task"
```

## Guidance

- Prefer `launch`/`ui`/`current` for simple steps (`screenshot` when you need
  rendered pixels); reserve `run` for multi-step UI work that needs the
  vision agent.
- After a task completes, take a screenshot to verify the outcome before
  reporting success.
- Obtain explicit approval before login, payment, sending, deleting, posting,
  commenting, liking, following, reposting, subscribing, or sharing. Use
  `--confirm` only after approval. Never retry one of these actions without
  inspecting the phone first.
- Background tasks cannot read confirmation/takeover input from a terminal.
  They fail with a human-takeover reason; never bypass login or captcha.
- A running stop returns `cancel_requested: true` and keeps the phone locked
  until acknowledgement. `--wait` timing out does not cancel the task. Poll or
  request a stop; never resubmit an uncertain external action.
- Async phone tasks use a five-minute cooperative deadline and 60-second model
  HTTP timeout. A blocked driver can delay stopping. `completed` and a semantic
  tap are execution results, not independent goal proof (`outcome_verified`
  stays false); inspect the actual final screen before claiming success.
- Phone names come from `contentswarm phones`; never guess them.
- Ordinary ADB cannot bypass app permissions, encryption, `FLAG_SECURE`, or
  private app storage. Report those boundaries rather than attempting a
  workaround.

Discovery event status now matches `/tasks/ID`; if event delivery fails, poll
the task rather than submitting again. Missing typing bridge is an explicit
capability failure, never a successful legacy fallback. Ask for a supported
installation fix; do not bypass the checked path with raw ADB.
