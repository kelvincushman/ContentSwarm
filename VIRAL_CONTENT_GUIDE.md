# Viral Content Automation - 20 Phone Setup

Complete guide for automating viral content discovery, creation, and distribution across social media platforms.

## Overview

**Your Viral Content Pipeline:**
1. **Discover** trending topics on TikTok, Instagram, YouTube, Twitter, Facebook
2. **Analyze** viral content using 12labs AI
3. **Create** new content using Veo3 (Google's video generation)
4. **Post** automatically to all platforms using 20 phones

## Phone Assignment Strategy

### Recommended Setup (20 Phones)

```
Platform          | Phones     | Purpose
------------------|------------|------------------------------------
TikTok            | 01-05 (5)  | Discovery + Multi-account posting
Instagram Reels   | 06-09 (4)  | Discovery + Posting
YouTube Shorts    | 10-13 (4)  | Discovery + Posting
Twitter/X         | 14-16 (3)  | Trending topics + Posting
Facebook          | 17-20 (4)  | Discovery + Posting
```

### Why This Distribution?

- **TikTok (5 phones)**: Highest viral potential, multi-account strategy
- **Instagram (4 phones)**: Second highest reach, good engagement
- **YouTube (4 phones)**: Longer content lifespan, monetization
- **Twitter (3 phones)**: Trend discovery, topic validation
- **Facebook (4 phones)**: Older demographic, different content style

## Complete Setup Guide

### 1. Install Required Apps on Each Phone

**Phones 1-5 (TikTok):**
- TikTok app
- Logged into different accounts

**Phones 6-9 (Instagram):**
- Instagram app
- Logged into different accounts

**Phones 10-13 (YouTube):**
- YouTube app
- Logged into different accounts

**Phones 14-16 (Twitter/X):**
- X app
- Logged into different accounts

**Phones 17-20 (Facebook):**
- Facebook app
- Logged into different accounts

### 2. Connect All Phones via WiFi

```bash
# Enable wireless debugging on each phone
# Settings → Developer Options → Wireless Debugging

# Connect each phone
adb connect 192.168.1.100:5555  # Phone 01
adb connect 192.168.1.101:5555  # Phone 02
# ... connect all 20 phones

# Verify all connected
adb devices
```

### 3. Configure phones_config.json

```json
{
  "phones": [
    {
      "device_id": "192.168.1.100:5555",
      "name": "phone_01",
      "description": "TikTok Account 1 (@username1)",
      "tags": ["tiktok", "primary"]
    },
    {
      "device_id": "192.168.1.101:5555",
      "name": "phone_02",
      "description": "TikTok Account 2 (@username2)",
      "tags": ["tiktok"]
    }
    // ... add all 20 phones with descriptions
  ]
}
```

### 4. Setup API Keys

**12labs API (Content Analysis):**
- Sign up at https://12labs.io
- Get API key
- Add to your script

**Veo3 API (Video Generation):**
- Sign up at Google AI Studio
- Get Veo3 access
- Add API key

**Model API (Phone Control):**
- **Option A**: Use Novita AI (recommended for 20 phones)
  - Sign up at https://novita.ai
  - No local GPU needed
  - Pay-per-use pricing

- **Option B**: Self-host on RTX 5060 16GB
  - Single phone control at a time
  - Free after initial setup
  - See PHONE_POOL_GUIDE.md for setup

### 5. Install Python Dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

## Usage Examples

### Full Automation Pipeline

```python
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager
from phone_agent.social_automation import SocialMediaAutomation, Platform

# Setup
model_config = ModelConfig(
    base_url="https://api.novita.ai/openai",
    model_name="zai-org/autoglm-phone-9b-multilingual",
    api_key="your-novita-api-key"
)

agent_config = AgentConfig(lang="en", verbose=False)

phone_manager = PhonePoolManager(
    model_config=model_config,
    agent_config=agent_config,
    phones_config="phones_config.json"
)

automation = SocialMediaAutomation(
    phone_manager=phone_manager,
    labs_12_api_key="your-12labs-key",
    veo3_api_key="your-veo3-key"
)

# Assign phones to platforms
automation.assign_phones({
    Platform.TIKTOK: ["phone_01", "phone_02", "phone_03", "phone_04", "phone_05"],
    Platform.INSTAGRAM_REELS: ["phone_06", "phone_07", "phone_08", "phone_09"],
    Platform.YOUTUBE_SHORTS: ["phone_10", "phone_11", "phone_12", "phone_13"],
    Platform.TWITTER: ["phone_14", "phone_15", "phone_16"],
    Platform.FACEBOOK: ["phone_17", "phone_18", "phone_19", "phone_20"]
})

# Run complete pipeline
automation.run_viral_pipeline(
    discovery_limit=10,  # Find 10 trending items per platform
    content_to_generate=5  # Create 5 new videos
)
```

### Quick Start Script

```bash
# Run full automation
python examples/viral_content_automation.py
# Choose option 1 for full pipeline
```

## Workflow Details

### Phase 1: Trending Discovery (30-60 mins)

```python
# Phone 01 monitors TikTok trending
trending = automation.discover_trending(Platform.TIKTOK, "phone_01", limit=10)

# Phone 06 monitors Instagram Reels
trending = automation.discover_trending(Platform.INSTAGRAM_REELS, "phone_06", limit=10)

# Etc for all platforms...
```

**What It Does:**
- Opens each app
- Navigates to trending/discover section
- Scrolls through top content
- Captures URLs, views, engagement metrics

### Phase 2: Content Analysis (10-20 mins)

```python
# Analyze top trending content
for content in top_trending:
    analysis = automation.analyze_with_12labs(content)
```

**12labs Analysis Provides:**
- Visual elements (objects, scenes, colors)
- Audio features (music type, sound effects)
- Actions and movements
- Mood and style
- Key moments timeline
- Recreation suggestions

### Phase 3: Content Generation (5-15 mins per video)

```python
# Generate new content based on analysis
generated = automation.generate_with_veo3(analysis, original_content)
```

**Veo3 Generates:**
- 15-60 second videos
- High quality (up to 4K)
- Matches viral style
- Original content (not copies)
- Platform-optimized format

### Phase 4: Multi-Platform Posting (30-60 mins)

```python
# Post to all platforms
for platform in platforms:
    phone = get_phone_for_platform(platform)
    automation.post_content(generated_content, platform, phone)
```

**Posting Workflow:**
1. Opens app on designated phone
2. Navigates to upload/create
3. Selects generated video
4. Adds caption + hashtags
5. Posts/publishes
6. Verifies success

## Advanced Strategies

### Strategy 1: Multi-Account Amplification

Post the same viral content to multiple accounts on the same platform:

```python
# Use all 5 TikTok phones to post same video
tiktok_phones = ["phone_01", "phone_02", "phone_03", "phone_04", "phone_05"]

for phone in tiktok_phones:
    automation.post_content(viral_content, Platform.TIKTOK, phone)
    time.sleep(30)  # Avoid rate limiting
```

**Benefits:**
- 5x reach on TikTok
- Increased viral probability
- Cross-account engagement boost

### Strategy 2: Platform-Specific Variations

Generate different versions for each platform:

```python
# TikTok version: 15s, vertical, trending audio
tiktok_video = generate_veo3(prompt + "TikTok style, 15 seconds")

# YouTube version: 60s, higher quality
youtube_video = generate_veo3(prompt + "YouTube Shorts style, 60 seconds")

# Instagram version: 30s, aesthetic focus
instagram_video = generate_veo3(prompt + "Instagram Reels style, 30 seconds")
```

### Strategy 3: Continuous Monitoring

Run automation 24/7 to catch trending topics early:

```python
# examples/viral_content_automation.py - Mode 4
python examples/viral_content_automation.py
# Choose option 4 for continuous monitoring
```

**Cycle:**
1. Check trending every hour
2. Generate content for top 3 trends
3. Post immediately
4. Repeat forever

### Strategy 4: Niche Targeting

Assign phones to specific niches:

```python
assignments = {
    Platform.TIKTOK: {
        "phone_01": "fitness",
        "phone_02": "cooking",
        "phone_03": "comedy",
        "phone_04": "education",
        "phone_05": "music"
    }
}
```

## Performance Expectations

### Time Estimates

| Phase | Duration | Details |
|-------|----------|---------|
| Discovery (5 platforms) | 30-60 min | 10 items per platform |
| Analysis (50 items) | 10-20 min | 12labs API processing |
| Generation (5 videos) | 25-75 min | 5-15 min per video |
| Posting (5 platforms) | 30-60 min | All 20 phones |
| **Total Cycle** | **2-4 hours** | Full pipeline |

### Cost Estimates (Using APIs)

**Per Cycle:**
- Phone Control (Novita AI): $0.50-1.00
- 12labs Analysis: $5-10
- Veo3 Generation (5 videos): $10-25
- **Total: $15-36 per cycle**

**Monthly (1 cycle/day):**
- **~$450-1,080/month**

**ROI Considerations:**
- If even 1 video goes viral (1M+ views)
- Typical sponsorship: $500-5,000
- Break even with 1 viral video/month

## Troubleshooting

### Issue: Phone Disconnects

```bash
# Check connections
python phone_pool_cli.py --status

# Reconnect
adb connect 192.168.1.100:5555

# Or reconnect all
for i in {100..119}; do
    adb connect 192.168.1.$i:5555
done
```

### Issue: App Login Required

**Solution:**
1. Manually log into apps on each phone
2. Enable "Remember Me" / "Stay Logged In"
3. Disable 2FA or use app-specific passwords
4. Keep phones charging and awake

### Issue: Rate Limiting

**Solution:**
- Add delays between posts: `time.sleep(60)`
- Rotate accounts
- Post at different times
- Use different IP addresses per phone (mobile data)

### Issue: Content Gets Flagged

**Solution:**
- Review generated content before posting
- Add human review step
- Use different captions per account
- Add slight variations to videos
- Don't post same content too frequently

## Best Practices

### Content Strategy

1. **Diversity**: Don't post only one niche
2. **Timing**: Post during platform-specific peak hours
3. **Quality**: Review generated content manually
4. **Engagement**: Respond to comments (can automate)
5. **Analytics**: Track which content performs best

### Account Safety

1. **Use Different IPs**: Mobile data or VPN per phone
2. **Vary Posting Times**: Don't all post at once
3. **Gradual Ramp-up**: Start with 1-2 posts/day per account
4. **Authentic Activity**: Like, comment, follow between posts
5. **Age Accounts**: Older accounts = more trust

### Technical Setup

1. **Redundancy**: Have backup phones ready
2. **Monitoring**: Set up alerts for disconnections
3. **Backups**: Save all generated content
4. **Logging**: Track successful/failed posts
5. **Testing**: Test workflow on 1-2 phones first

## Sample Workflow Schedule

### Daily Automation Schedule

```
06:00 - Cycle 1 (Morning trends)
  - Discover trending content
  - Analyze & generate
  - Post to all platforms

12:00 - Cycle 2 (Midday trends)
  - Discover trending content
  - Analyze & generate
  - Post to all platforms

18:00 - Cycle 3 (Evening trends)
  - Discover trending content
  - Analyze & generate
  - Post to all platforms

00:00 - Cycle 4 (Late night trends)
  - Discover trending content
  - Analyze & generate
  - Post to all platforms
```

### Weekly Tasks

- Monday: Review analytics, adjust strategy
- Wednesday: Update captions/hashtags
- Friday: Test new content types
- Sunday: Account maintenance, re-login if needed

## Next Steps

1. **Setup Phones**: Connect and configure all 20 phones
2. **Create Accounts**: 4-5 accounts per platform
3. **Test Pipeline**: Run with 1-2 phones first
4. **Scale Up**: Gradually add more phones
5. **Optimize**: Track metrics, improve content

## Resources

- **12labs Documentation**: https://12labs.io/docs
- **Veo3 API**: https://ai.google.dev/veo
- **Phone Pool Guide**: See PHONE_POOL_GUIDE.md
- **Example Scripts**: See examples/viral_content_automation.py

---

**🚀 Start creating viral content at scale!**
