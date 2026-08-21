# Quick Start Guide - Viral Content Automation

Complete setup guide for automating viral content creation and distribution across social media platforms using 20 phones.

## 🎯 What You'll Build

A fully automated system that:
1. **Discovers** trending content on TikTok, Instagram, YouTube, Twitter, Facebook
2. **Analyzes** viral videos using 12labs AI
3. **Generates** new content via your chosen generation API (e.g. Kie.ai, Veo3)
4. **Posts** automatically to all platforms using 20 phones
5. **Monitors** everything via a beautiful web dashboard

## 📋 Prerequisites

### Hardware
- **Android phones** (1-20, connected via USB or WiFi)
- **PC/Server** to run the system (GPU optional, for local vision-model serving)

### Software
- Python 3.8+
- ADB (Android Debug Bridge)
- Git

### Accounts
- Social media accounts for each platform (TikTok, Instagram, YouTube, Twitter, Facebook)
- Optional: 12labs API key (for advanced analysis)

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd ContentSwarm
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
pip install -e .

# Install dashboard dependencies
cd dashboard
pip install -r requirements.txt
cd ..
```

### 3. Content generation (optional)

Content generation is external — bring your own generation API (e.g. Kie.ai
or Veo3) and wire it into the pipeline's generate stage. It is not required
for phone control.

### 4. Setup Phone Control Model

**Option A: Use Novita AI (Recommended for 20 phones)**

```bash
# Sign up at https://novita.ai
# Get API key
# Configure in your scripts (see step 6)
```

**Option B: Self-host on RTX 5060 16GB (Single phone at a time)**

```bash
# Clone model repository
cd ~
git clone https://huggingface.co/zai-org/AutoGLM-Phone-9B-Multilingual
cd AutoGLM-Phone-9B-Multilingual

# Install vLLM
pip install vllm

# Start model server (optimized for 16GB)
vllm serve zai-org/AutoGLM-Phone-9B-Multilingual \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.85 \
    --enable-prefix-caching
```

### 5. Connect Your 20 Phones

```bash
# Enable wireless debugging on each phone:
# Settings → Developer Options → Wireless Debugging

# Connect each phone via ADB
adb connect 192.168.1.100:5555  # Phone 01
adb connect 192.168.1.101:5555  # Phone 02
# ... connect all 20 phones

# Verify all connected
adb devices
```

### 6. Configure Phones

Create `phones_config.json` in the project root:

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
    // ... add all 20 phones
  ]
}
```

**Recommended distribution:**
- Phones 01-05: TikTok (5 phones)
- Phones 06-09: Instagram Reels (4 phones)
- Phones 10-13: YouTube Shorts (4 phones)
- Phones 14-16: Twitter/X (3 phones)
- Phones 17-20: Facebook (4 phones)

See `PHONE_POOL_GUIDE.md` for complete configuration guide.

## 🎬 Usage

### Option 1: Web Dashboard (Recommended)

The easiest way to manage everything!

```bash
cd dashboard
python app.py
```

Open http://localhost:5000 in your browser.

**Dashboard Features:**
- 📱 **Overview Tab**: Quick stats and phone grid
- 🎮 **Phones Tab**: Select and control any of 20 phones
- 🚀 **Automation Tab**: Run full viral pipeline
- 📊 **Analytics Tab**: Track performance metrics
- 📝 **Logs Tab**: Real-time system events

**Quick Workflow:**
1. Go to Overview → verify all phones are connected
2. Go to Generation → enter prompt → click Generate
3. Go to Automation → click "Start Pipeline"
4. Monitor progress in real-time!

### Option 2: Python Script (Advanced)

#### Test Single Phone Control

```python
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager

# Setup model (Novita AI)
model_config = ModelConfig(
    base_url="https://api.novita.ai/openai",
    model_name="zai-org/autoglm-phone-9b-multilingual",
    api_key="your-novita-api-key"
)

# Or self-hosted
# model_config = ModelConfig(
#     base_url="http://localhost:8000/v1",
#     model_name="autoglm-phone-9b-multilingual"
# )

agent_config = AgentConfig(lang="en", verbose=True)

# Initialize phone manager
manager = PhonePoolManager(
    model_config=model_config,
    agent_config=agent_config,
    phones_config="phones_config.json"
)

# Select and control a phone
manager.select_phone("phone_01")
result = manager.run_task("Open TikTok and scroll through For You page")
print(result)
```

#### Run Full Automation Pipeline

```bash
python examples/viral_content_automation.py
```

Full pipeline:
1. Discovers trending content
2. Analyzes with 12labs (or mock analysis)
3. Generates content via your external generation API
4. Posts to all platforms

### Option 3: Interactive CLI

```bash
python phone_pool_cli.py
```

Menu options:
1. List all phones
2. Select phone
3. Run task
4. Phone status
5. Exit

## 📊 Workflow Examples

### Example 1: Post a Video to TikTok

```python
# Video must already be on the phone (gallery / camera roll)
manager.select_phone("phone_01")
manager.run_task("Open TikTok, upload the newest video from the gallery, add caption 'viral content' and post")
```

### Example 2: Multi-Platform Posting

```python
from phone_agent.social_automation import SocialMediaAutomation, Platform

# Setup automation
automation = SocialMediaAutomation(
    phone_manager=manager,
    labs_12_api_key="your-12labs-key",  # Optional
)

# Assign phones to platforms
automation.assign_phones({
    Platform.TIKTOK: ["phone_01", "phone_02", "phone_03"],
    Platform.INSTAGRAM_REELS: ["phone_06", "phone_07"],
    Platform.YOUTUBE_SHORTS: ["phone_10", "phone_11"],
    Platform.TWITTER: ["phone_14"],
    Platform.FACEBOOK: ["phone_17"]
})

# Run full pipeline
automation.run_free_pipeline(
    discovery_limit=10,  # Find 10 trending items per platform
    content_to_generate=3  # Create 3 videos
)
```

## 💰 Cost Comparison

### With ComfyUI (FREE!)
- **Hardware**: RTX 5060 16GB (already have)
- **Electricity**: ~$0.10 per 100 generations
- **Phone Control**:
  - Novita AI: ~$0.50-1.00 per cycle
  - Self-hosted: FREE
- **Total**: ~$0-1 per cycle

### With Paid APIs (Veo3)
- **Phone Control**: $0.50-1.00 per cycle
- **Video Generation**: $5-10 per video × 5 videos = $25-50
- **Total**: ~$25-51 per cycle

**Savings with ComfyUI: $25-50 per cycle!**

If you run 1 cycle per day:
- **Monthly savings: $750-1,500**
- **Yearly savings: $9,000-18,000**

## 🎨 Content Generation Performance

### RTX 5060 16GB Benchmarks

**Images (SDXL):**
- 1080×1920: ~15 seconds
- Quality: Excellent
- VRAM: ~10GB

**Videos (AnimateDiff + SD 1.5):**
- 16 frames (2 seconds): ~60 seconds
- 48 frames (6 seconds): ~180 seconds (3 minutes)
- Quality: Good
- VRAM: ~12GB

**Comparison:**
- ComfyUI: 3 minutes per video, FREE
- Veo3 API: 5-15 minutes per video, $5-10 cost

## 📱 Phone Management Tips

### Connection Stability

```bash
# Keep phones connected - create a script
# save as reconnect_phones.sh
#!/bin/bash
for i in {100..119}; do
    adb connect 192.168.1.$i:5555
done

# Run every hour via cron
# crontab -e
# 0 * * * * /path/to/reconnect_phones.sh
```

### Account Safety

1. **Use different IPs**: Mobile data or VPN per phone
2. **Vary posting times**: Don't post all at once
3. **Gradual ramp-up**: Start with 1-2 posts/day per account
4. **Authentic activity**: Like, comment, follow between posts

### Rate Limiting

```python
import time

# Post with delays
for phone in tiktok_phones:
    automation.post_content(content, Platform.TIKTOK, phone)
    time.sleep(60)  # 1 minute delay between posts
```

## 🐛 Troubleshooting

### ComfyUI Not Starting

```bash
# Check if port 8188 is in use
lsof -i :8188

# Kill process if needed
kill -9 <PID>

# Restart ComfyUI
cd ~/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

### Phone Disconnects

```bash
# Check connection
adb devices

# Reconnect
adb connect 192.168.1.100:5555

# Check if wireless debugging is still enabled on phone
```

### Model API Issues

```bash
# Test Novita AI connection
curl -X POST https://api.novita.ai/openai/v1/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "zai-org/autoglm-phone-9b-multilingual", "prompt": "test"}'

# Test self-hosted model
curl http://localhost:8000/v1/models
```

### Dashboard Not Loading

```bash
# Check if Flask is running
lsof -i :5000

# Check logs
cd dashboard
python app.py
# Look for errors in output
```

## 📚 Documentation

- **Phone Pool Guide**: `PHONE_POOL_GUIDE.md` - Complete multi-phone control
- **Viral Content Guide**: `VIRAL_CONTENT_GUIDE.md` - Social media automation strategy
- **ComfyUI Setup**: `COMFYUI_SETUP.md` - Installation for RTX 5060 16GB
- **Dashboard Guide**: `dashboard/README.md` - Web dashboard documentation

## 🎯 Next Steps

### Immediate (First Day)
1. ✅ Setup ComfyUI and test generation
2. ✅ Connect all 20 phones via ADB
3. ✅ Configure `phones_config.json`
4. ✅ Start dashboard and verify phones show up
5. ✅ Test single phone control

### Week 1
1. Install social media apps on all phones
2. Create accounts for each platform
3. Test content generation with ComfyUI
4. Run test automation on 1-2 phones
5. Verify posting workflow

### Week 2-4
1. Create custom ComfyUI workflows for each platform
2. Set up scheduled automation (daily cycles)
3. Monitor analytics and optimize
4. Scale up to all 20 phones
5. Track viral content success

### Advanced
1. Add authentication to dashboard
2. Implement scheduled posting
3. Create analytics dashboards
4. Add phone screen mirroring
5. Implement engagement automation (like, comment, follow)

## 💡 Pro Tips

1. **Start Small**: Test with 1-2 phones before scaling to 20
2. **Review Content**: Manually review generated content before posting
3. **Diversify**: Don't post only one type of content
4. **Timing**: Post during platform-specific peak hours
5. **Analytics**: Track which content performs best and optimize
6. **Account Age**: Older accounts have more trust
7. **Engagement**: Respond to comments (can be automated later)

## 🚀 Ready to Go Viral!

You now have everything you need to:
- ✅ Control 20 phones from one system
- ✅ Generate unlimited content for FREE with ComfyUI
- ✅ Automate discovery, creation, and posting
- ✅ Monitor everything via web dashboard
- ✅ Save $750-1,500 per month vs paid APIs

**Start the dashboard:**
```bash
cd dashboard
python app.py
```

**Open**: http://localhost:5000

**Begin your viral content empire!** 🎉

---

**Questions or Issues?**
- Check troubleshooting section above
- Review relevant documentation
- Check dashboard logs tab
- Verify all services are running (ComfyUI, model API, phones connected)
