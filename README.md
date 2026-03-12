# x-phone-poster

> Post to X (Twitter) via a USB-connected Android phone — no API key, no rate limits, no app review.

An OpenClaw skill + standalone shell toolkit that automates posting to X by controlling a real Android phone over USB. Uses [YADB](https://github.com/ysbing/YADB) for reliable UI inspection and [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) for Unicode-safe text input.

Supports **text tweets**, **image tweets**, and runs happily from a cron job or an AI agent.

---

## Why

X's v2 API requires your app to be attached to a **Project** in the developer portal. Write access on the free tier is limited to 17 posts/day, costs $100/month for anything meaningful, and apps frequently get rejected.

This bypasses all of that — it posts exactly like a human would, through the actual X app, on a real phone connected via USB. **No credentials stored anywhere. No API. No rate limits beyond what a human would hit.**

---

## How it works

```
Host machine (ADB)
  └─ force-stop X → fresh launch → home feed
       └─ tap FAB (compose button) → creation menu opens
            └─ tap FAB again → compose screen
                 └─ YADB -layout → verify compose is open   ← this is the key step
                      └─ AdbKeyboard base64 broadcast → types tweet (emoji + newlines safe)
                           └─ tap POST button
                                └─ YADB -layout → verify compose gone = success ✅
```

### Why YADB?

`adb shell uiautomator dump` silently fails on X's compose screen in certain states — returns empty or partial XML. YADB's `app_process`-based layout extractor bypasses this and reliably returns the full UI tree. It's what tells us "compose screen is actually open" before we attempt to type anything.

### Why AdbKeyboard (base64 broadcast)?

`adb shell input text` splits on spaces (shell argument parsing) and silently drops emoji, newlines, hashtags and most special characters.

AdbKeyboard's `ADB_INPUT_B64` broadcast receives a **single base64-encoded string** that the IME decodes and injects as keyboard input — full Unicode, emoji, multi-line, everything.

---

## Requirements

- **Android phone** — any model, Android 8+
- **USB debugging enabled** on the phone
- **X (Twitter) app** installed and logged in
- **ADB** on your host machine:
  - macOS: `brew install android-platform-tools`
  - Ubuntu/Debian: `apt install adb`
  - Windows: [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)

---

## Installation

### As an OpenClaw skill (recommended)

```bash
cd ~/.openclaw/workspace/skills
git clone https://github.com/kelvincushman/x-phone-poster
cd x-phone-poster && chmod +x *.sh
./setup.sh
```

Once installed, your OpenClaw agent can post tweets on your behalf using natural language — just ask it to post.

### Standalone

```bash
git clone https://github.com/kelvincushman/x-phone-poster
cd x-phone-poster && chmod +x *.sh
./setup.sh
```

---

## Setup

```bash
# Connect your Android phone via USB
# On the phone: enable USB debugging (Settings → Developer Options → USB Debugging)
# Accept the "Allow USB debugging from this computer?" prompt

./setup.sh
```

This will:
1. Download and push **YADB** to `/data/local/tmp/yadb` on the device
2. Download and install **AdbKeyboard** APK
3. Enable AdbKeyboard as an available IME
4. Set screen stay-awake while charging (prevents auto-lock mid-post)

---

## Usage

### Post a text tweet

```bash
./post.sh "Your tweet text here"
```

Multi-line tweet with emoji:

```bash
./post.sh $'Building in public.\n\nNo copy-paste. Just described what I wanted.\n\nThis is what building feels like now. 🛠️\n\n#BuildInPublic #UKtech'
```

### Post a tweet with an image

```bash
./post-with-image.sh /path/to/image.jpg "Your tweet caption here"
```

---

## Calibration (different device)

The default tap coordinates in `post.sh` are for a **Samsung Galaxy Note 10 (1080×2340)**. If you're using a different phone, run:

```bash
./calibrate.sh
```

This launches X, uses YADB to find the FAB, compose field and POST button by resource ID, and prints the coordinates to paste into `post.sh`:

```
FAB_X=964; FAB_Y=1891
TEXT_X=600; TEXT_Y=419
POST_X=957; POST_Y=158
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADB_DEVICE` | auto-detected | ADB serial (`adb devices`) |
| `ADB_BIN` | `adb` | Path to `adb` binary |

```bash
# Multiple devices? Target one explicitly
ADB_DEVICE=RF8M90JL60K ./post.sh "My tweet"
```

---

## Running on a server / headless

The phone just needs to be **physically connected via USB** — it doesn't need to be on the same desk. Works fine from a Linux server (Ubuntu, Raspberry Pi, etc.) as long as:

1. USB is connected
2. The ADB daemon is running (`adb start-server`)
3. The phone screen stays on (handled by `setup.sh` via `stay_on_while_plugged_in=3`)

Cron example (post every 3 hours from a queue file):

```bash
# crontab -e
0 7,12,18 * * * cd /path/to/x-phone-poster && ./post.sh "$(head -1 ~/queue.txt)" && sed -i '1d' ~/queue.txt
```

---

## OpenClaw integration

After installing as a skill, your agent will automatically discover it from `SKILL.md`. You can then say things like:

> "Post the next tweet from the queue"
> "Post a tweet with a screenshot of the dashboard"
> "Schedule today's 3 posts"

The agent reads `SKILL.md` to understand how to call the scripts correctly.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `YADB not on device` | Run `./setup.sh` |
| `Compose screen did not open` | X launched to wrong screen — script force-stops first, retry |
| `Tweet field appears empty after typing` | AdbKeyboard not active — run `./setup.sh` again or set it manually in phone keyboard settings |
| `adb: device not found` | `adb kill-server && adb start-server && adb devices` |
| Duplicate tweets | Never run two instances in parallel on the same device |
| Phone screen locks mid-post | Run `./setup.sh` — sets stay-awake while charging |

---

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | OpenClaw agent instructions |
| `README.md` | This file |
| `post.sh` | Post a text tweet |
| `post-with-image.sh` | Post a tweet with image attachment |
| `setup.sh` | One-time device setup (YADB + AdbKeyboard) |
| `calibrate.sh` | Auto-detect tap coordinates for any Android device |

---

## Tested on

- Samsung Galaxy Note 10 (SM-N970F), Android 12, X app v10.x
- Host: Ubuntu 24.04, ADB 34.0.5

---

## Credits

- [YADB](https://github.com/ysbing/YADB) by [@ysbing](https://github.com/ysbing)
- [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) by [@senzhk](https://github.com/senzhk)

---

## Licence

MIT
