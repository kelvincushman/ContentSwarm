# ContentSwarm Viral Content Pipeline

Orchestrate the 4-stage viral content pipeline: Discover trending content,
Analyze it, Generate new content, and Post to platforms across multiple phones.

## Configuration

- `CONTENTSWARM_API_URL` — Base URL of ContentSwarm API (default: `http://127.0.0.1:5000/api/v1`)

## Actions

### Run the full pipeline
```bash
curl -s -X POST "$CONTENTSWARM_API_URL/pipeline/run" \
  -H "Content-Type: application/json" \
  -d '{"discovery_limit": 10, "content_to_generate": 3}'
```
Runs all 4 stages automatically: discover → analyze → generate → post.

### Check pipeline status
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/status" | jq .
```
Returns current stage (idle, discovery, analysis, generation, posting),
progress percentage, and cumulative counts.

### Discover trending content
```bash
curl -s -X POST "$CONTENTSWARM_API_URL/pipeline/discover" \
  -H "Content-Type: application/json" \
  -d '{"platform": "tiktok", "phone": "phone_01", "limit": 10}'
```
Supported platforms: `tiktok`, `youtube_shorts`, `instagram_reels`, `twitter`, `facebook`.

### View trending queue
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/trending" | jq .
```

### View generated content queue
```bash
curl -s "$CONTENTSWARM_API_URL/pipeline/content" | jq .
```

### Set phone-to-platform assignments
```bash
curl -s -X POST "$CONTENTSWARM_API_URL/assignments" \
  -H "Content-Type: application/json" \
  -d '{
    "tiktok": ["phone_01", "phone_02", "phone_03"],
    "instagram_reels": ["phone_04", "phone_05"],
    "youtube_shorts": ["phone_06", "phone_07"],
    "twitter": ["phone_08"],
    "facebook": ["phone_09", "phone_10"]
  }'
```

### Get current assignments
```bash
curl -s "$CONTENTSWARM_API_URL/assignments" | jq .
```

## Pipeline Stages

1. **Discovery** — Uses assigned phones to browse each platform's trending/discover section
2. **Analysis** — Analyzes top trending content with 12labs AI (detects objects, actions, mood, style)
3. **Generation** — Creates new content with ComfyUI (local GPU, free) or Veo3 (cloud, paid)
4. **Posting** — Distributes generated content to assigned phones on each platform

## Strategy Tips

- Assign 3-5 phones per platform for resilience
- Run discovery at least 2x/day to catch trends early
- Generate content that matches the platform's dominant style
- Stagger posting across phones to avoid rate limits
- Monitor engagement metrics to refine content strategy
