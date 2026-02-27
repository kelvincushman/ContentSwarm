# ContentSwarm Phone Control

Control a fleet of up to 20 Android phones via ADB. Each phone runs an AI
vision-language agent that can navigate apps, tap, swipe, type, and complete
multi-step tasks autonomously.

## Configuration

- `CONTENTSWARM_API_URL` — Base URL of ContentSwarm API (default: `http://127.0.0.1:5000/api/v1`)

## Actions

### List all phones
```bash
curl -s "$CONTENTSWARM_API_URL/phones" | jq .
```
Returns each phone's name, device_id, connection status, and tags.

### Get phone details
```bash
curl -s "$CONTENTSWARM_API_URL/phones/{phone_name}" | jq .
```

### Run a task on a phone (async)
```bash
curl -s -X POST "$CONTENTSWARM_API_URL/phones/{phone_name}/task" \
  -H "Content-Type: application/json" \
  -d '{"task": "Open TikTok and scroll through the For You page"}'
```
Returns a `task_id`. The phone agent will autonomously navigate the phone
using screenshot analysis to complete the task.

### Run tasks on multiple phones in parallel
```bash
curl -s -X POST "$CONTENTSWARM_API_URL/phones/batch" \
  -H "Content-Type: application/json" \
  -d '{"tasks": {"phone_01": "Open TikTok", "phone_02": "Open Instagram", "phone_03": "Open YouTube"}}'
```
Returns `task_ids` for each phone. All tasks execute simultaneously.

### Check task status
```bash
curl -s "$CONTENTSWARM_API_URL/tasks/{task_id}" | jq .
```
Status values: `pending`, `running`, `completed`, `failed`.

### List all tasks
```bash
curl -s "$CONTENTSWARM_API_URL/tasks" | jq .
```

## Task Examples

Common tasks the phone agent can handle:
- "Open TikTok and scroll through trending videos"
- "Open Instagram, go to Reels, and like the first 5 videos"
- "Open Chrome and search for 'viral content trends 2026'"
- "Open the camera app and take a photo"
- "Open YouTube Shorts and watch 10 shorts"
- "Open Twitter/X and post: Hello World"

## Notes

- Each phone can only run one task at a time (per-phone locking)
- Tasks can take 5-120+ seconds depending on complexity (max 100 steps)
- The agent uses a vision-language model to analyze screenshots and decide actions
- Supported actions: Launch, Tap, Swipe, Type, Back, Home, Double Tap, Long Press, Wait
