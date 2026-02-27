# ContentSwarm Analytics & Status

Monitor the ContentSwarm system: phone fleet status, pipeline progress,
generation stats, and posting history.

## Configuration

- `CONTENTSWARM_API_URL` — Base URL of ContentSwarm API (default: `http://127.0.0.1:5000/api/v1`)

## Actions

### System overview
```bash
curl -s "$CONTENTSWARM_API_URL/status" | jq .
```
Returns phone count, connection status, pipeline state, and OpenClaw bridge status.

### Analytics data
```bash
curl -s "$CONTENTSWARM_API_URL/analytics" | jq .
```
Returns total generated, total posted, and per-platform breakdown.

### Phone fleet status
```bash
curl -s "$CONTENTSWARM_API_URL/phones" | jq .
```

### Pipeline progress
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/status" | jq .
```

### Trending queue size
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/trending" | jq '.trending | length'
```

### Content queue size
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/content" | jq '.content | length'
```

### All running/completed tasks
```bash
curl -s "$CONTENTSWARM_API_URL/tasks" | jq .
```

## Metrics to Monitor

- **Phone connectivity** — How many of 20 phones are online
- **Pipeline stage** — Current stage and progress percentage
- **Content velocity** — How many pieces discovered/generated/posted per run
- **Task success rate** — Completed vs failed phone tasks
- **Queue depths** — Trending and content queue sizes

## Decision Inputs

Use these metrics to make strategic decisions:
- Low connectivity → investigate ADB connections, potentially restart devices
- Stalled pipeline → check which stage is blocking
- Low engagement → adjust content strategy, target different trends
- Queue overflow → increase posting frequency or reduce discovery rate
