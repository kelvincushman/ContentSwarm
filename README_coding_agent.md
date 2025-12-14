# ContentSwarm Quick Start for Coding Agent

<div align="center">
<img src=resources/logo.svg width="20%"/>
</div>

> **This document is designed for AI assistants (such as Claude Code) to automate the deployment of ContentSwarm.**
>
> If you are a human reader, you can skip this document and follow the README.md instructions instead.

---

# Quick Start Guide

## Prerequisites

### 1. Python Environment

Python 3.10 or higher is required.

### 2. ADB (Android Debug Bridge)

1. Download the official ADB [installation package](https://developer.android.com/tools/releases/platform-tools)
2. Extract and configure environment variables:

**macOS:**

```bash
# Assuming extracted to ~/Downloads/platform-tools
export PATH=${PATH}:~/Downloads/platform-tools
```

**Windows:** Add the extracted folder path to your system PATH. Refer to [this tutorial](https://blog.csdn.net/x2584179909/article/details/108319973) if needed.

### 3. Android Device Setup

Requirements:
- Android 7.0+ device or emulator
- Developer Mode enabled
- USB Debugging enabled

**Enable Developer Mode:**
1. Go to `Settings > About Phone > Build Number`
2. Tap rapidly about 10 times until "Developer mode enabled" appears

**Enable USB Debugging:**
1. Go to `Settings > Developer Options > USB Debugging`
2. Enable the toggle
3. Some devices may require a restart

**Important permissions to check:**

![Permissions](resources/screenshot-20251210-120416.png)

### 4. Install ADB Keyboard

Download and install [ADB Keyboard APK](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk) on your device.

After installation, enable it in `Settings > Input Method` or `Settings > Keyboard List`.

---

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install package
pip install -e .
```

---

## ADB Configuration

**Ensure your USB cable supports data transfer (not charging only).**

### Verify Connection

```bash
# Check connected devices
adb devices

# Expected output:
# List of devices attached
# emulator-5554   device
```

### Remote Debugging (WiFi)

Ensure your phone and computer are on the same WiFi network.

![Enable Wireless Debugging](resources/screenshot-20251210-120630.png)

```bash
# Connect via WiFi (replace with your phone's IP and port)
adb connect 192.168.1.100:5555

# Verify connection
adb devices
```

### Device Management

```bash
# List all devices
adb devices

# Connect remote device
adb connect <ip>:<port>

# Disconnect device
adb disconnect <ip>:<port>
```

---

## Usage

### Command Line

```bash
# Interactive mode
python main.py --base-url <MODEL_API_URL> --model <MODEL_NAME>

# Execute specific task
python main.py --base-url <MODEL_API_URL> "Open Chrome browser"

# Use API key authentication
python main.py --apikey sk-xxxxx

# English system prompt
python main.py --lang en --base-url <MODEL_API_URL> "Open Chrome browser"

# List supported apps
python main.py --list-apps

# Specify device
python main.py --device-id 192.168.1.100:5555 --base-url <MODEL_API_URL> "Open TikTok"
```

### Python API

```python
from phone_agent import PhoneAgent
from phone_agent.model import ModelConfig

# Configure model
model_config = ModelConfig(
    base_url="<MODEL_API_URL>",
    model_name="<MODEL_NAME>",
)

# Create Agent
agent = PhoneAgent(model_config=model_config)

# Execute task
result = agent.run("Open eBay and search for wireless earbuds")
print(result)
```

---

## Environment Variables

| Variable                  | Description               | Default                      |
|---------------------------|---------------------------|------------------------------|
| `PHONE_AGENT_BASE_URL`    | Model API URL             | `http://localhost:8000/v1`   |
| `PHONE_AGENT_MODEL`       | Model name                | `autoglm-phone-9b`           |
| `PHONE_AGENT_API_KEY`     | API key                   | `EMPTY`                      |
| `PHONE_AGENT_MAX_STEPS`   | Max steps per task        | `100`                        |
| `PHONE_AGENT_DEVICE_ID`   | ADB device ID             | (auto-detect)                |
| `PHONE_AGENT_LANG`        | Language (`cn`/`en`)      | `cn`                         |

---

## Troubleshooting

### Device Not Found

```bash
adb kill-server
adb start-server
adb devices
```

Check:
1. USB debugging enabled
2. USB cable supports data transfer
3. Authorization popup approved on phone
4. Try different USB port/cable

### Can Open Apps but Cannot Tap

Enable both in `Settings > Developer Options`:
- **USB Debugging**
- **USB Debugging (Security Settings)**

### Text Input Not Working

1. Ensure ADB Keyboard is installed
2. Enable in `Settings > System > Language & Input > Virtual Keyboard`

### Windows Encoding Issues

Add environment variable before running:

```bash
PYTHONIOENCODING=utf-8 python main.py ...
```

---
