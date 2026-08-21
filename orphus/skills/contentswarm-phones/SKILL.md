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
export CONTENTSWARM_API_URL="http://<server-ip>:5000/api/v1"   # ContentSwarm server
export CONTENTSWARM_API_TOKEN="<token>"                        # only if the server sets one
```

If the `contentswarm` command is missing, install it:
`pip install -e /path/to/ContentSwarm` (or `pipx install /path/to/ContentSwarm`).

Never echo or print `CONTENTSWARM_API_TOKEN`.

## Commands

All commands print JSON and exit 0 on success, 1 on failure.

### Check the system

```bash
contentswarm status        # phones online, pipeline state
contentswarm phones        # every phone: name, device_id, connected, tags
contentswarm phone phone_01
```

### Deterministic device control (fast, no LLM)

```bash
contentswarm apps                       # apps launchable by name
contentswarm launch phone_01 TikTok     # launch app directly via ADB
contentswarm current phone_01           # foreground app
contentswarm screenshot phone_01 -o screen.png   # see the screen - read the PNG after
```

Use `launch` + `screenshot` for simple, predictable steps. Read the saved
screenshot with your `read` tool to verify what is actually on screen.

### Natural-language tasks (vision agent, async)

```bash
# Submit and wait for completion (tasks take 5-120+ seconds):
contentswarm run phone_01 "Open TikTok, search for 'bushcraft', like the top 3 videos" --wait

# Fire-and-forget, then poll:
contentswarm run phone_01 "Open Instagram and scroll Reels for a minute"
contentswarm task <task_id>       # status: pending | running | completed | failed
contentswarm tasks                # everything tracked
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

- Prefer `launch`/`screenshot`/`current` for simple steps; reserve `run` for
  multi-step UI work that needs the vision agent.
- After a task completes, take a screenshot to verify the outcome before
  reporting success.
- Tasks that hit login walls or captchas pause for human takeover - if a task
  seems stuck in `running` far past its expected duration, report it rather
  than resubmitting.
- Phone names come from `contentswarm phones`; never guess them.
