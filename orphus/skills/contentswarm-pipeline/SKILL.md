---
name: contentswarm-pipeline
description: Drive ContentSwarm's viral-content pipeline - discover trending content, monitor generation, manage phone-to-platform assignments, and read analytics. Use for content strategy work on top of the phone fleet.
---

# ContentSwarm Content Pipeline

Optional layer on top of phone control: a 4-stage pipeline
(discover trending → analyze → generate → post) across TikTok, Instagram
Reels, YouTube Shorts, X, and Facebook. Uses the same environment as the
`contentswarm-phones` skill (`CONTENTSWARM_API_URL`, `CONTENTSWARM_API_TOKEN`).

All endpoints below use the bash tool with `curl`:

```bash
CS() { curl -s -H "Authorization: Bearer $CONTENTSWARM_API_TOKEN" "$@"; }
```

## Pipeline

```bash
# Run the full pipeline (async - returns immediately):
CS -X POST -H "Content-Type: application/json" \
  -d '{"discovery_limit": 10, "content_to_generate": 3}' \
  "$CONTENTSWARM_API_URL/pipeline/run"

# Watch progress (stage: idle|discovery|analysis|generation|posting, progress %):
CS "$CONTENTSWARM_API_URL/pipeline/status"

# Queues:
CS "$CONTENTSWARM_API_URL/pipeline/trending"   # discovered trending items
CS "$CONTENTSWARM_API_URL/pipeline/content"    # generated content awaiting posting
```

## Targeted discovery

```bash
CS -X POST -H "Content-Type: application/json" \
  -d '{"platform": "tiktok", "phone": "phone_01", "limit": 10}' \
  "$CONTENTSWARM_API_URL/pipeline/discover"
```

Platforms: `tiktok`, `youtube_shorts`, `instagram_reels`, `twitter`, `facebook`.

## Phone-to-platform assignments

```bash
CS "$CONTENTSWARM_API_URL/assignments"

CS -X POST -H "Content-Type: application/json" -d '{
  "tiktok": ["phone_01", "phone_02"],
  "instagram_reels": ["phone_03"],
  "youtube_shorts": ["phone_04"]
}' "$CONTENTSWARM_API_URL/assignments"
```

## Analytics

```bash
CS "$CONTENTSWARM_API_URL/analytics"   # totals generated/posted, per-platform
```

## Guidance

- Assign phones before running the pipeline - stages skip platforms with no
  assigned phone.
- Poll `pipeline/status` rather than resubmitting; only one pipeline run
  should be active at a time.
- Stagger posting-heavy work across phones to avoid platform rate limits.
