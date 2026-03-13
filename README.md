# X Phone Poster

**Automated X (Twitter) posting, threading, DM funnels, and phone farm orchestration — zero API, pure Android ADB.**

Built and battle-tested as part of the [OpenClaw](https://openclaw.ai) agentic automation stack. No Twitter/X API keys required. All actions are performed via real Android devices using ADB + YADB UI automation — indistinguishable from a human using the app.

---

## Why No API?

X's API is expensive, heavily rate-limited, and increasingly restricted. This project takes a different approach:

- **Real Android phone** connected via USB → **ADB**
- **YADB** parses the live UI layout (device-agnostic, no coordinates)
- **AdbKeyboard** inputs Unicode/emoji text reliably
- **ContentSwarm** orchestrates multi-step flows (compose → thread → DM funnel)

The result: post tweets, schedule threads, run DM funnels, and scale to a 10-phone farm — all without touching the X API.

---

## Features

| Feature | Status |
|---|---|
| Single tweet posting | ✅ |
| Thread posting (multi-tweet) | ✅ |
| Scheduled posting (5x/day cron) | ✅ |
| Thread scheduler (Mon/Wed/Fri) | ✅ |
| DM funnel (comment FREE → follow → repost → auto-DM) | ✅ |
| Device-agnostic navigation (any Android) | ✅ |
| Phone farm orchestration (up to 10 devices) | ✅ |
| Google Sheets queue integration | ✅ |
| Per-device locking (prevents collision) | ✅ |
| Duplicate DM prevention | ✅ |
| OpenClaw skill integration | ✅ |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Android automation | [ADB](https://developer.android.com/tools/adb) + [YADB](https://github.com/ysbing/YADB) |
| Unicode/emoji input | [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) |
| AI vision (optional) | [AutoGLM-Phone-9B](https://novita.ai) via Novita serverless |
| Queue management | Google Sheets (via [gws CLI](https://www.npmjs.com/package/@googleworkspace/cli)) |
| Scheduler | Python cron on Linux server |
| Orchestration | Custom `orchestrator.py` with threading + file locks |
| OpenClaw integration | Skill discovery via `SKILL.md` |
| Language | Python 3.10+ |
| Deployment | Linux server (pai-server) → SSH → Android device (ai-server) |

---

## Architecture

```
pai-server (OpenClaw / scheduler)
    │
    ├── x_scheduler.py          # 5x/day tweet scheduler (reads Google Sheet queue)
    ├── thread_scheduler.py     # Mon/Wed/Fri thread poster
    ├── funnel_cron.py          # Every 5 min: check if funnel checks need to fire
    │
    └── SSH → ai-server (ADB host)
            │
            ├── orchestrator.py             # Phone farm manager (parallel, locked)
            ├── devices.json                # Phone registry
            ├── thread_dm_funnel.py         # DM funnel: detect FREE → DM offer
            │
            └── phone_agent/posting/
                    ├── device_nav.py       # Device-agnostic YADB navigation
                    ├── twitter.py          # post_to_twitter(), post_thread_to_twitter()
                    └── dm_handler.py       # DM inbox scanner + auto-reply
```

### DM Funnel Flow

```
Thread posted (Mon/Wed/Fri 07:43 UTC)
    │
    └── 8 funnel checks scheduled: +10m, +20m, +30m, +1h, +2h, +4h, +8h, +12h
            │
            └── For each check:
                    1. Navigate to Notifications → Mentions
                    2. Find replies containing "FREE"
                    3. Check commenter follows @account
                    4. Check commenter retweeted thread
                    5. Both pass? → DM personalised offer
                    6. Log to funnel_replied.json (no double-DMs)
```

---

## Hardware Requirements

- **Android phone** running X (Twitter) app, USB debugging enabled
- **Linux server** with ADB installed (`sudo apt install adb`)
- **USB cable** (or USB hub for phone farm)
- Phone connected to the ADB host machine (not the scheduler machine — they can be different servers connected via SSH)

### Phone Farm (up to 10 devices)

```
ADB Host Machine
    │
    ├── USB Hub (powered, 10-port)
    │       ├── Phone 1 (serial: XXXX) — @Account1
    │       ├── Phone 2 (serial: YYYY) — @Account2
    │       └── ... up to Phone 10
    │
    └── orchestrator.py fans out tasks in parallel threads
        with per-device file locks to prevent collision
```

---

## Prerequisites

### On the Android Phone

1. Enable **Developer Options** → **USB Debugging**
2. Install **X (Twitter)** app and log into your account
3. Install **AdbKeyboard** APK:
   ```bash
   # Download from: https://github.com/senzhk/ADBKeyBoard/releases
   adb install ADBKeyboard.apk
   adb shell ime enable com.android.adbkeyboard/.AdbIME
   ```
4. Install **YADB**:
   ```bash
   adb push yadb /data/local/tmp/yadb
   adb shell chmod +x /data/local/tmp/yadb
   # Download from: https://github.com/ysbing/YADB/releases/download/v1.0.0/yadb
   ```

### On the ADB Host Machine (ai-server)

```bash
# ADB
sudo apt install adb

# Python dependencies
pip install -r requirements.txt

# Verify phone is connected
adb devices
# Should show: RF8M90JL60K    device
```

### On the Scheduler Machine (pai-server / OpenClaw host)

```bash
# Google Workspace CLI (for Sheets queue)
npm install -g @googleworkspace/cli

# Python 3.10+
python3 --version
```

---

## Installation

```bash
git clone https://github.com/kelvincushman/x-phone-poster.git
cd x-phone-poster
pip install -r requirements.txt
```

### Configuration

**1. Register your phone(s):**

```bash
# Copy the example
cp devices.json.example devices.json

# Edit devices.json:
[
  {
    "serial":   "YOUR_DEVICE_SERIAL",
    "account":  "YourXHandle",
    "platform": "x",
    "persona":  "yourpersona",
    "status":   "active",
    "notes":    "Samsung Note 10 — primary account"
  }
]

# Get your device serial:
adb devices
```

**2. Configure Google Sheets queue (optional but recommended):**

```bash
# Auth gws CLI
gws auth login

# Set your spreadsheet ID in x_scheduler.py:
SPREADSHEET_ID = "your-google-sheet-id"
```

Your sheet needs these tabs:
- **ContentSwarm** — main tweet queue (columns: ID, Tweet, Status, Posted At, Platform, Persona, Handle, Image URL)
- **Thread Queue** — thread queue (columns: ID, Tweet1, Tweet2, Tweet3, Tweet4, Tweet5, Schedule, Status, Posted At)

**3. Set SSH config (if scheduler and ADB host are different machines):**

```bash
# In x_scheduler.py / thread_scheduler.py:
AI_SERVER = "user@your-adb-host-ip"
```

**4. Set up cron jobs on scheduler machine:**

```bash
crontab -e

# Add these lines:
# Tweet scheduler — 5x daily
43 7  * * * /usr/bin/python3 /path/to/x_scheduler.py >> /path/to/logs/x_scheduler.log 2>&1
17 11 * * * /usr/bin/python3 /path/to/x_scheduler.py >> /path/to/logs/x_scheduler.log 2>&1
52 14 * * * /usr/bin/python3 /path/to/x_scheduler.py >> /path/to/logs/x_scheduler.log 2>&1
33 18 * * * /usr/bin/python3 /path/to/x_scheduler.py >> /path/to/logs/x_scheduler.log 2>&1
09 21 * * * /usr/bin/python3 /path/to/x_scheduler.py >> /path/to/logs/x_scheduler.log 2>&1

# Thread scheduler — Mon/Wed/Fri 07:43
43 7 * * 1,3,5 /usr/bin/python3 /path/to/thread_scheduler.py >> /path/to/logs/thread_scheduler.log 2>&1

# DM funnel cron — every 5 min (fires at scheduled intervals after thread posts)
*/5 * * * * /usr/bin/python3 /path/to/funnel_cron.py >> /path/to/logs/funnel_cron.log 2>&1
```

---

## Usage

### Post a Single Tweet

```python
# On the ADB host machine
import sys
sys.path.insert(0, '/path/to/x-phone-poster')
from phone_agent.posting.twitter import post_to_twitter

result = post_to_twitter("YOUR_DEVICE_SERIAL", "Your tweet text here 🚀")
print("Posted!" if result else "Failed")
```

### Post a Thread

```python
from phone_agent.posting.twitter import post_thread_to_twitter

tweets = [
    "Hook: the attention-grabbing opening tweet",
    "Body: the insight, proof, or story",
    "CTA: comment FREE below + follow + repost and I will DM you a personalised breakdown\n\n#AI #AiGENTIS"
]

result = post_thread_to_twitter("YOUR_DEVICE_SERIAL", tweets)
```

### Run the DM Funnel Manually

```bash
# On the ADB host machine
cd /path/to/x-phone-poster
python3 thread_dm_funnel.py
# Optionally pass custom offer text:
python3 thread_dm_funnel.py "Hey! Here's your personalised breakdown..."
```

### Phone Farm — Health Check

```bash
python3 orchestrator.py health
```

Output:
```
──────────────────────────────────────────────────
  Phone Farm Health Check  [2026-03-13 18:45:32 UTC]
──────────────────────────────────────────────────
  ✅ RF8M90JL60K  @UKKelvinLee          x        active
  ✅ ABC123DEF    @KelvinCushman         x        active
  ❌ DEF456GHI    @Zara_AI               x        active  ← disconnected
──────────────────────────────────────────────────
```

### Phone Farm — Add a New Phone

```bash
python3 orchestrator.py add DEF456GHI YourHandle x yourpersona "iPhone 13 — second account"
```

### Phone Farm — Run Funnel on All Phones in Parallel

```bash
python3 orchestrator.py funnel
```

---

## DM Funnel — Full Setup

The DM funnel converts thread engagement into direct conversations using the **FREE comment gate**:

**Your thread CTA (final tweet):**
```
comment FREE below + follow + repost and I will DM you a personalised breakdown

follow for more 👇 #AI #YourBrand
```

**Automation flow:**
1. User comments "FREE", follows your account, reposts the thread
2. Funnel detects the comment in Mentions tab
3. Checks "Follows you" on their profile
4. Checks your thread appears on their timeline (repost confirmed)
5. All three pass → sends personalised DM offer automatically

**Configure your offer in `thread_dm_funnel.py`:**
```python
OFFER = (
    "Hey! 👋 Thanks for commenting FREE 🙏\n\n"
    "Tell me your business name + what you do and I'll put together "
    "a personalised breakdown — exactly what [YOUR SERVICE] could do "
    "for your business.\n\nReply here and let's chat 🤙🏻"
)
```

---

## Google Sheets Queue

The queue sheet drives everything. You write tweets into the sheet; the scheduler picks them up automatically.

**ContentSwarm tab columns:**
| Column | Description |
|---|---|
| A | ID (e.g. xq-001) |
| B | Tweet text |
| C | Status (`pending` / `posted` / `failed`) |
| D | Posted timestamp |
| E | Platform (`x`) |
| F | Persona |
| G | Handle |
| H | Image URL (optional) |

**Thread Queue tab columns:**
| Column | Description |
|---|---|
| A | Thread ID |
| B–F | Tweet 1–5 |
| G | Schedule date |
| H | Status (`pending` / `posted`) |
| I | Posted timestamp |

---

## Using With OpenClaw

This project ships as an OpenClaw skill. Once installed, your OpenClaw agent can post tweets, manage threads, and run the DM funnel by natural language instruction.

### Install as OpenClaw Skill

```bash
# From your OpenClaw workspace skills directory
git clone https://github.com/kelvincushman/x-phone-poster.git skills/x-phone-poster
```

The `SKILL.md` at the root provides OpenClaw with:
- Tool descriptions for each capability
- Device configuration instructions
- Example prompts

### Starter Prompt for OpenClaw Agent

Copy this prompt to configure your OpenClaw agent to use x-phone-poster:

```
You are managing X (Twitter) automation for @[YOUR_HANDLE] via x-phone-poster.

Setup:
- ADB host: [YOUR_ADB_HOST_IP] (SSH user: [USER])
- Device serial: [YOUR_DEVICE_SERIAL]
- ContentSwarm path: /path/to/x-phone-poster
- Conda env: [YOUR_CONDA_ENV] (activate before running Python)
- Google Sheet ID: [YOUR_SHEET_ID] (ContentSwarm + Thread Queue tabs)
- Scheduler on: [YOUR_SCHEDULER_HOST]

Capabilities:
1. POST TWEET: SSH to ADB host → activate conda → run post_to_twitter(serial, text)
2. POST THREAD: SSH to ADB host → run post_thread_to_twitter(serial, [tweets])
3. RUN FUNNEL: SSH to ADB host → python3 thread_dm_funnel.py
4. FARM HEALTH: SSH to ADB host → python3 orchestrator.py health
5. ADD PHONE: SSH to ADB host → python3 orchestrator.py add [serial] [handle] x [persona]
6. QUEUE TWEET: Use gws sheets to write to ContentSwarm tab with status "pending"
7. QUEUE THREAD: Use gws sheets to write to Thread Queue tab with status "pending"

Rules:
- Never run two ADB operations on the same device simultaneously
- Always use base64 encoding for tweet text (handled by twitter.py automatically)
- Check orchestrator.py health before batch operations
- The DM funnel requires: comment "FREE" + follow + repost (all three gates)
- funnel_replied_[serial].json prevents double-DMs per device

Thread format (5 tweets):
1. Hook — bold claim or provocative question
2. Problem — what pain point / what's broken
3. Insight — your unique take or solution
4. Proof — result, stat, or story
5. CTA — "comment FREE below + follow + repost and I will DM you [OFFER]"

Posting schedule (UTC): 07:43, 11:17, 14:52, 18:33, 21:09
Thread schedule: Mon/Wed/Fri 07:43
Funnel checks after thread: +10m, +20m, +30m, +1h, +2h, +4h, +8h, +12h
```

---

## Troubleshooting

### Phone not detected

```bash
adb devices
# If empty: check USB cable, enable USB debugging, accept the ADB prompt on phone
# If "unauthorized": tap "Allow" on the phone screen
```

### AdbKeyboard not inputting text

```bash
adb shell ime list -a | grep adbkeyboard
# Should show: com.android.adbkeyboard/.AdbIME
# If missing: adb install ADBKeyboard.apk
```

### POST button not found

The `device_nav.py` module finds all buttons by YADB XML layout — no coordinates. If X updates its UI:
```bash
# Dump current layout to inspect
adb shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -layout
adb pull /data/local/tmp/yadb_layout_dump.xml /tmp/layout.xml
cat /tmp/layout.xml | grep -i "post\|compose"
# Update find_by_text() / find_by_content_desc() in device_nav.py if needed
```

### Thread tweets stacking in slot 1

Caused by focus tap interfering with X's auto-focus on new thread slots. Solution: `add_tweet_to_thread()` in `twitter.py` removes the focus tap and relies on X's native auto-focus. Do not re-add it.

### DM funnel not finding FREE replies

```bash
# Check Mentions tab manually
python3 -c "
import sys; sys.path.insert(0,'.')
from phone_agent.posting.device_nav import dump_layout, tap_nav, tap_mentions_tab
DEV = 'YOUR_SERIAL'
from phone_agent.posting.device_nav import launch_x
launch_x(DEV)
tap_nav(DEV, 'Notifications')
tap_mentions_tab(DEV)
layout = dump_layout(DEV, '/tmp/check.xml')
print(layout[:2000])
"
```

### Funnel says 'already DM'd' but no message was sent

The `funnel_replied.json` log got written before the DM actually sent. Clear it:
```bash
# Clear a specific handle
python3 -c "
import json
log = json.load(open('funnel_replied.json'))
del log['HandleToClear']
json.dump(log, open('funnel_replied.json','w'), indent=2)
"
```

---

## Project Structure

```
x-phone-poster/
├── README.md                    # This file
├── SKILL.md                     # OpenClaw skill definition
├── requirements.txt             # Python dependencies
├── devices.json.example         # Phone registry template
├── .gitignore
│
├── orchestrator.py              # Phone farm manager — parallel execution
├── thread_dm_funnel.py          # DM funnel: FREE comment → DM offer
├── x_scheduler.py               # Tweet scheduler (reads Google Sheet)
├── thread_scheduler.py          # Thread scheduler (Mon/Wed/Fri)
├── funnel_cron.py               # Funnel timing cron (fires interval checks)
│
├── phone_agent/
│   └── posting/
│       ├── device_nav.py        # ★ Device-agnostic YADB navigation (no hardcoded coords)
│       ├── twitter.py           # post_to_twitter() + post_thread_to_twitter()
│       └── dm_handler.py        # DM inbox scanner + keyword auto-reply
│
├── x-twitter/
│   ├── post.sh                  # Shell wrapper for single tweet
│   └── calibrate.sh             # Maps device UI for first-time setup
│
└── examples/
    └── basic_usage.py
```

---

## Key Design Decisions

**Why YADB over UIAutomator?**
UIAutomator crashes intermittently on X's compose screen (app state conflicts). YADB uses `app_process` directly — more reliable and doesn't require UIAutomator service to be running.

**Why AdbKeyboard over `input text`?**
`adb shell input text` mangles Unicode, emoji, and newlines. AdbKeyboard broadcasts base64-encoded text via Android intent — perfectly handles all characters.

**Why no hardcoded coordinates?**
Different phones have different screen sizes and densities. `device_nav.py` finds every element by `content-desc`, `resource-id`, or `text` from the YADB XML layout — works identically on a Note 10, a Pixel 9, or any other Android phone.

**Why a file lock per device?**
The `orchestrator.py` runs all phones in parallel threads. Without locks, two threads could both try to ADB into the same device simultaneously, causing corrupted UI state. Each device gets its own `/tmp/phone_locks/[serial].lock`.

**Why base64 for tweet text in Python?**
SSH passes command strings through multiple shell layers. Base64 encoding the tweet text prevents special characters, newlines, emoji, and quotes from breaking the command chain.

---

## Roadmap

- [ ] Image attachment support (Drive → download → attach in compose)
- [ ] Engagement cron (auto-like/reply to mentions)
- [ ] Follow/unfollow list management
- [ ] LinkedIn phone automation (same architecture)
- [ ] Instagram/TikTok support (phone 2+)
- [ ] Telegram failure alerts
- [ ] Web dashboard (phone farm status)
- [ ] Auto thread generation via LLM

---

## Contributing

PRs welcome. Keep changes device-agnostic — no hardcoded pixel coordinates. All navigation must go through `device_nav.py`.

---

## Licence

MIT — see `LICENSE`

---

## Built With

- [OpenClaw](https://openclaw.ai) — personal AI agent framework
- [YADB](https://github.com/ysbing/YADB) — Android UI automation
- [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) — reliable text input
- [gws CLI](https://www.npmjs.com/package/@googleworkspace/cli) — Google Workspace automation
