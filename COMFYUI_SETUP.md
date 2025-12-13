# ComfyUI Setup for Viral Content Generation

Complete guide for setting up ComfyUI on your RTX 5060 16GB for automated social media content generation.

## Why ComfyUI?

**vs. Veo3 API:**
- ✅ **FREE** - No API costs ($0 vs $10-25 per video)
- ✅ **Privacy** - All generation runs locally
- ✅ **Customizable** - Full control over workflows
- ✅ **Faster** - No API latency
- ✅ **Unlimited** - Generate as much as you want

**With RTX 5060 16GB:**
- Perfect for Stable Diffusion XL (images)
- Can run AnimateDiff (short videos)
- Can run SVD (Stable Video Diffusion)
- Can run FLUX models

## Installation

### 1. Install ComfyUI

```bash
cd ~
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install ComfyUI requirements
pip install -r requirements.txt
```

### 3. Download Models

#### For Images (SDXL - Required)

```bash
cd models/checkpoints/

# Download SDXL base
wget https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors
```

#### For Videos (AnimateDiff - Recommended)

```bash
# Install ComfyUI Manager for easy model downloads
cd ~/ComfyUI/custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager

# Restart ComfyUI and use Manager to install:
# - AnimateDiff
# - AnimateDiff Motion Models
# - Video Helper Suite
```

#### Alternative: Stable Video Diffusion

```bash
cd ~/ComfyUI/models/checkpoints/
wget https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/resolve/main/svd_xt.safetensors
```

### 4. Launch ComfyUI

```bash
cd ~/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

Access at: http://127.0.0.1:8188

## Optimizations for RTX 5060 16GB

### ComfyUI Launch Args

For better performance with 16GB VRAM:

```bash
python main.py \
  --listen 0.0.0.0 \
  --port 8188 \
  --lowvram \
  --normalvram
```

### Model Selection

**Best models for 16GB:**

1. **Images:**
   - SDXL (works great)
   - FLUX.1-schnell (fast, good quality)
   - SD 1.5 (lighter, faster)

2. **Videos:**
   - AnimateDiff + SD 1.5 (recommended)
   - SVD (works but slower)
   - CogVideoX-2B (experimental)

### Memory-Saving Tips

```python
# In your ComfyUI workflow:
# 1. Use tiled VAE for large images
# 2. Lower resolution (768x1024 instead of 1080x1920)
# 3. Fewer frames (16 instead of 48)
# 4. Batch size 1
```

## Creating Workflows for Social Media

### TikTok/Instagram Reels Workflow

1. **Open ComfyUI** (http://127.0.0.1:8188)

2. **Load Example Workflow:**
   - File → Load → Examples → img2vid (for video)
   - OR create from scratch

3. **Configure for Vertical Format:**
   - Resolution: 1080x1920 (vertical)
   - Frames: 16-48 (2-6 seconds)
   - FPS: 8

4. **Export Workflow:**
   - Right-click → Export workflow as JSON
   - Save to `~/Open-AutoGLM/comfyui_workflows/tiktok_video.json`

### Recommended Workflow Structure

```
Input Prompt
    ↓
CLIP Text Encode
    ↓
Model (SDXL/AnimateDiff)
    ↓
KSampler
    ↓
VAE Decode
    ↓
Video Combine (for video)
    ↓
Save Video/Image
```

## Integration with Social Automation

### Basic Usage

```python
from phone_agent.comfyui_integration import (
    ComfyUIClient,
    GenerationRequest,
    ContentType
)

# Initialize client
client = ComfyUIClient("http://127.0.0.1:8188")

# Generate image
request = GenerationRequest(
    prompt="viral tiktok dance, trending, colorful",
    width=1080,
    height=1920,
    content_type=ContentType.IMAGE
)

result = client.generate(request)
print(f"Generated: {result.file_path}")
```

### With Custom Workflow

```python
# Use your exported TikTok workflow
result = client.generate(
    request,
    workflow_path="comfyui_workflows/tiktok_video.json"
)
```

### Integrated with Social Automation

```python
from phone_agent.social_automation import SocialMediaAutomation
from phone_agent.comfyui_integration import ComfyUIClient

# Setup ComfyUI
comfy_client = ComfyUIClient("http://127.0.0.1:8188")

# Use in automation
automation = SocialMediaAutomation(
    phone_manager=manager,
    comfyui_client=comfy_client  # Use ComfyUI instead of Veo3
)

# Run pipeline
automation.run_viral_pipeline()
```

## Example Workflows

### 1. Image Generation (Instagram Post)

Create file: `comfyui_workflows/instagram_post.json`

```json
{
  "prompt": "professional photo, aesthetic, trending",
  "negative_prompt": "ugly, blurry, low quality",
  "width": 1080,
  "height": 1080,
  "steps": 25,
  "cfg": 7.5,
  "model": "sd_xl_base_1.0.safetensors"
}
```

### 2. Video Generation (TikTok)

Create file: `comfyui_workflows/tiktok_video.json`

Workflow nodes:
- Text Prompt
- AnimateDiff Model
- Motion Model (optional)
- Video Output (1080x1920, 16 frames)

### 3. Batch Generation

```python
# Generate 10 variations
requests = [
    GenerationRequest(
        prompt=f"viral content variation {i}",
        width=1080,
        height=1920,
        seed=i  # Different seed each time
    )
    for i in range(10)
]

results = client.batch_generate(requests)
```

## Performance Benchmarks (RTX 5060 16GB)

### Images (SDXL)

| Resolution | Steps | Time | VRAM |
|------------|-------|------|------|
| 1024x1024 | 20 | ~10s | 8GB |
| 1080x1920 | 20 | ~15s | 10GB |
| 1536x2048 | 20 | ~25s | 14GB |

### Videos (AnimateDiff + SD 1.5)

| Frames | Resolution | Time | VRAM |
|--------|------------|------|------|
| 16 | 512x512 | ~30s | 6GB |
| 16 | 768x1024 | ~60s | 10GB |
| 48 | 512x512 | ~90s | 8GB |
| 48 | 768x1024 | ~180s | 12GB |

## Troubleshooting

### Out of Memory

**Solution 1: Reduce Resolution**
```python
# Instead of 1080x1920
width=768, height=1024
```

**Solution 2: Fewer Frames**
```python
# Instead of 48 frames
num_frames=16
```

**Solution 3: Use --lowvram**
```bash
python main.py --lowvram
```

### Slow Generation

**Solution 1: Use Faster Models**
- FLUX.1-schnell (image)
- SD 1.5 instead of SDXL
- Fewer sampling steps (15 instead of 25)

**Solution 2: xFormers**
```bash
pip install xformers
# Restart ComfyUI
```

### Connection Failed

```bash
# Check if ComfyUI is running
curl http://127.0.0.1:8188/system_stats

# Test from Python
python -c "from phone_agent.comfyui_integration import test_comfyui_connection; test_comfyui_connection()"
```

## Recommended Workflows by Platform

### TikTok
- **Format**: 1080x1920 vertical
- **Duration**: 15-60 seconds (48 frames @ 8fps)
- **Style**: Energetic, colorful, fast cuts
- **Model**: AnimateDiff + motion models

### Instagram Reels
- **Format**: 1080x1920 vertical
- **Duration**: 15-90 seconds
- **Style**: Aesthetic, smooth, polished
- **Model**: SVD or AnimateDiff

### YouTube Shorts
- **Format**: 1080x1920 vertical
- **Duration**: Up to 60 seconds
- **Style**: High quality, informative
- **Model**: SDXL + AnimateDiff

### Twitter/X
- **Format**: 1200x675 horizontal (image)
- **Style**: Eye-catching, simple
- **Model**: SDXL or FLUX

## Cost Comparison

### With ComfyUI (FREE):
- Hardware: RTX 5060 16GB (already have)
- Electricity: ~$0.10 per 100 generations
- **Total: ~$0 per month**

### With Veo3 API:
- $5-10 per video
- 20 videos/day × 30 days = 600 videos
- **Total: $3,000-6,000 per month**

**Savings: $3,000-6,000/month!**

## Next Steps

1. **Install ComfyUI** following steps above
2. **Download base models** (SDXL + AnimateDiff)
3. **Create workflows** for each platform
4. **Test generation** with example prompts
5. **Integrate with automation** script

## Resources

- **ComfyUI Documentation**: https://github.com/comfyanonymous/ComfyUI
- **ComfyUI Workflows**: https://comfyworkflows.com
- **AnimateDiff**: https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved
- **Video Models**: https://github.com/Fannovel16/ComfyUI-Frame-Interpolation

---

**🎨 Start generating unlimited viral content for FREE!**
