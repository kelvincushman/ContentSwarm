# Phone Pool Manager - Control 20+ Phones

A comprehensive guide for managing and controlling multiple Android phones with easy switching.

## Overview

The Phone Pool Manager allows you to:
- **Manage 20+ phones** from a single interface
- **Switch between phones instantly** without reconnecting
- **Run different tasks** on different phones
- **Sequential workflows** across multiple devices
- **Single model instance** serves all phones (efficient!)

## Quick Start

### 1. Setup Your Phone Configuration

Create `phones_config.json` with your 20 phones:

```bash
python phone_pool_cli.py --create-sample-config phones_config.json
```

Edit the file with your actual phone IPs:

```json
{
  "phones": [
    {
      "device_id": "192.168.1.100:5555",
      "name": "phone_01",
      "description": "Main testing phone",
      "tags": ["testing", "primary"]
    },
    {
      "device_id": "192.168.1.101:5555",
      "name": "phone_02",
      "description": "Secondary phone",
      "tags": ["testing"]
    }
    // ... add all 20 phones
  ]
}
```

### 2. Connect All Phones via WiFi

For each phone, enable wireless debugging and connect:

```bash
# Phone 1
adb connect 192.168.1.100:5555

# Phone 2
adb connect 192.168.1.101:5555

# ... connect all 20 phones
```

### 3. Start the Model Service

**Option A: Local (RTX 5060 16GB - Optimized)**

```bash
python3 -m vllm.entrypoints.openai.api_server \
  --served-model-name autoglm-phone-9b-multilingual \
  --model zai-org/AutoGLM-Phone-9B-Multilingual \
  --port 8000 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --dtype float16 \
  --allowed-local-media-path / \
  --mm-encoder-tp-mode data \
  --mm_processor_cache_type shm \
  --mm_processor_kwargs '{"max_pixels":3000000}' \
  --chat-template-content-format string \
  --limit-mm-per-prompt '{"image":6}'
```

**Option B: Third-Party API (Recommended for 20 phones)**

No local GPU needed! Use Novita AI, z.ai, or Parasail.

### 4. Launch Phone Pool CLI

```bash
python phone_pool_cli.py --config phones_config.json --lang en
```

## Usage Examples

### Interactive Mode

```bash
python phone_pool_cli.py --config phones_config.json

# In interactive mode:
[None]> list                          # Show all phones
[None]> status                        # Check connection status
[None]> select phone_01               # Select phone 1
[phone_01]> Open Chrome browser       # Run task on current phone
[phone_01]> select phone_02           # Switch to phone 2
[phone_02]> Open Gmail                # Run task on phone 2
```

### Quick Run (No Switching)

```bash
# Run task directly on specific phone
python phone_pool_cli.py --config phones_config.json \
  --phone phone_01 \
  --task "Open Chrome and search for python"
```

### Batch Processing

```bash
# Run different tasks on multiple phones
python phone_pool_cli.py --phone phone_01 --task "Open Chrome"
python phone_pool_cli.py --phone phone_02 --task "Open Gmail"
python phone_pool_cli.py --phone phone_03 --task "Open Maps"
# ... up to phone_20
```

## Python API Usage

### Basic Example

```python
from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager

# Setup
model_config = ModelConfig(
    base_url="http://localhost:8000/v1",
    model_name="autoglm-phone-9b-multilingual"
)

agent_config = AgentConfig(lang="en", verbose=True)

manager = PhonePoolManager(
    model_config=model_config,
    agent_config=agent_config,
    phones_config="phones_config.json"
)

# Use different phones
manager.quick_run("phone_01", "Open Chrome")
manager.quick_run("phone_02", "Open Gmail")
manager.quick_run("phone_03", "Open Maps")
```

### Sequential Workflow

```python
# Define workflow
tasks = [
    ("phone_01", "Open Gmail and check inbox"),
    ("phone_02", "Open Calendar and check today"),
    ("phone_03", "Open Maps and search coffee shops"),
    ("phone_04", "Open Chrome and check news"),
    ("phone_05", "Open YouTube and find music")
]

# Execute sequentially
for phone, task in tasks:
    result = manager.quick_run(phone, task)
    print(f"✅ {phone}: {result}")
```

### With Third-Party API

```python
# No local GPU needed!
model_config = ModelConfig(
    base_url="https://api.novita.ai/openai",
    model_name="zai-org/autoglm-phone-9b-multilingual",
    api_key="your-novita-api-key"
)

manager = PhonePoolManager(
    model_config=model_config,
    agent_config=AgentConfig(lang="en"),
    phones_config="phones_config.json"
)

# Control all 20 phones via API
for i in range(1, 21):
    phone = f"phone_{i:02d}"
    manager.quick_run(phone, f"Open Chrome on phone {i}")
```

## Advanced Features

### Auto-Discover Devices

```python
manager = PhonePoolManager(model_config, agent_config)

# Scan for connected devices
added = manager.scan_and_add_devices()
print(f"Added {added} devices")

# Save configuration
manager.save_phones("discovered_phones.json")
```

### Dynamic Phone Management

```python
# Add phone at runtime
manager.add_phone(
    name="new_phone",
    device_id="192.168.1.200:5555",
    description="Newly added device",
    tags=["testing"]
)

# Remove phone
manager.remove_phone("new_phone")
```

### Connection Status Checking

```python
# Check which phones are connected
status = manager.check_connections()

for phone_name, is_connected in status.items():
    if is_connected:
        print(f"✅ {phone_name} is connected")
    else:
        print(f"❌ {phone_name} is offline")
```

## Architecture

### How It Works

```
┌─────────────────────────────────────────────────────┐
│  Phone Pool Manager (Your Computer)                 │
│  ┌─────────────────────────────────────────┐       │
│  │  Single Model Instance                   │       │
│  │  (Local vLLM or API Service)            │       │
│  └─────────────────────────────────────────┘       │
│                     ↓                                │
│  ┌─────────────────────────────────────────┐       │
│  │  Phone Pool Manager                      │       │
│  │  - Manages 20 phone connections          │       │
│  │  - Creates agent on-demand               │       │
│  │  - Switches context instantly            │       │
│  └─────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
                      ↓
        ┌─────────────┬─────────────┬─────────────┐
        ↓             ↓             ↓             ↓
    Phone 1       Phone 2       Phone 3     ... Phone 20
  (via WiFi)    (via WiFi)    (via WiFi)     (via WiFi)
```

### Resource Efficiency

**Single Model Instance:**
- One model serves all 20 phones
- Switch between phones without reloading
- Minimal memory overhead

**On-Demand Agent Creation:**
- Agent created only when phone is selected
- Previous agent released from memory
- Efficient for sequential operations

## Configuration Guide

### phones_config.json Structure

```json
{
  "phones": [
    {
      "device_id": "IP:PORT or serial",
      "name": "unique_phone_name",
      "description": "Human-readable description",
      "tags": ["optional", "tags", "for", "filtering"]
    }
  ]
}
```

### Environment Variables

```bash
# Model settings
export PHONE_AGENT_BASE_URL="http://localhost:8000/v1"
export PHONE_AGENT_MODEL="autoglm-phone-9b-multilingual"
export PHONE_AGENT_API_KEY="your-api-key"
export PHONE_AGENT_LANG="en"
```

## Troubleshooting

### Phone Not Connecting

```bash
# Check if phone is visible
adb devices

# Reconnect
adb connect 192.168.1.100:5555

# Check in manager
python phone_pool_cli.py --status
```

### Model Memory Issues (16GB GPU)

If you get OOM errors:

1. Reduce `--max-model-len` to 6144
2. Reduce `--mm_processor_kwargs` max_pixels to 2000000
3. Reduce `--limit-mm-per-prompt` to 4 images
4. Or use third-party API instead!

### Slow Switching

- Expected: ~1-2 seconds per switch
- Agent creation is lightweight
- Most time is in model inference, not switching

## Best Practices

### For 20 Phones

1. **Use Third-Party API**
   - Avoids GPU memory constraints
   - Faster inference
   - No maintenance

2. **WiFi Connection**
   - More reliable than USB for 20 devices
   - Easier cable management
   - Can control remotely

3. **Sequential Processing**
   - One phone at a time
   - Clear task completion
   - Easier debugging

4. **Phone Naming**
   - Use consistent naming: phone_01, phone_02, etc.
   - Add descriptive tags
   - Document purpose in description

### Workflow Organization

```python
# Group phones by purpose
testing_phones = ["phone_01", "phone_02", "phone_03"]
production_phones = ["phone_04", "phone_05", "phone_06"]

# Run tasks by group
for phone in testing_phones:
    manager.quick_run(phone, "Run test suite")

for phone in production_phones:
    manager.quick_run(phone, "Check production status")
```

## Performance

### Single Phone Operation

- **Switch time**: ~1 second
- **Task execution**: Depends on task complexity
- **Model inference**: ~2-5 seconds per step

### 20 Phone Sequential Processing

- **Total time**: ~20 phones × task_time
- **Example**: Simple task (3 sec) × 20 = ~60 seconds
- **Bottleneck**: Model inference, not switching

### Recommended Approach

For 20 phones doing the same task:
```python
phones = [f"phone_{i:02d}" for i in range(1, 21)]
task = "Open Chrome and check status"

for phone in phones:
    result = manager.quick_run(phone, task)
    print(f"{phone}: {result}")
```

## Examples Directory

Check `examples/phone_pool_example.py` for:
- Basic usage
- Batch tasks
- Dynamic management
- Auto-discovery
- API service usage
- Sequential workflows

## FAQ

**Q: Can I control phones in parallel?**
A: Current design is sequential (one at a time). For true parallel control, you'd need multiple model instances.

**Q: What's the limit on number of phones?**
A: No hard limit! Tested with 20, but can handle more.

**Q: Do I need 20 separate model instances?**
A: No! One model instance serves all phones through switching.

**Q: Can I use USB and WiFi simultaneously?**
A: Yes! Mix and match connection types.

**Q: What if a phone disconnects?**
A: Manager will show connection status. Reconnect via ADB.

## Support

For issues or questions:
- Check connection status: `python phone_pool_cli.py --status`
- Review logs when `verbose=True`
- Verify ADB connections: `adb devices`

---

**Happy multi-phone controlling! 📱📱📱**
