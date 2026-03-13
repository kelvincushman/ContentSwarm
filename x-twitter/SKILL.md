---
name: x-phone-poster
description: Post tweets to X (Twitter) via a USB-connected Android phone using ADB. No API key required. Handles text, emoji, newlines, and image attachments. Use when asked to post a tweet, schedule a post, or automate X content via phone automation. Requires Android phone connected via USB with USB debugging enabled.
---

# x-phone-poster

Post to X (Twitter) via ADB — no API key, no rate limits, no app review. Controls a real Android phone over USB using YADB (UI inspection) and AdbKeyboard (Unicode-safe text input).

## Prerequisites

- Android phone connected via USB with USB debugging enabled
- X (Twitter) app installed and logged in on the phone
- `adb` installed on the host machine
- Run `./setup.sh` once per device before first use

## Quick Setup

```bash
# 1. Clone into your skills directory
cd ~/.openclaw/workspace/skills
git clone https://github.com/kelvincushman/x-phone-poster

# 2. Connect Android phone via USB, enable USB debugging, accept the prompt
# 3. Run one-time setup
cd x-phone-poster && chmod +x *.sh && ./setup.sh

# 4. For a new device model, calibrate tap coordinates
./calibrate.sh
```

## Posting a Tweet (Text Only)

```bash
cd ~/.openclaw/workspace/skills/x-phone-poster

./post.sh "Your tweet text here"

# Multi-line with emoji — use $'...' quoting in bash
./post.sh $'Building in public.\n\nThis is what it looks like. 🛠️\n\n#BuildInPublic'
```

**As an agent:** always shell-escape the tweet text properly. Pass it as a single argument.

## Posting a Tweet with an Image

```bash
./post-with-image.sh /path/to/image.jpg "Your tweet caption"

# Example
./post-with-image.sh /tmp/dashboard.png "The AiGENTIS dashboard. Live. 🚀 #BuildInPublic"
```

The script pushes the image to the phone, opens X via share intent (pre-attaches image), then types the text.

## Post Flow (What Happens Under the Hood)

```
1. am force-stop com.twitter.android        # clean state
2. am start .StartActivity                  # launch to home feed
3. YADB -layout                             # verify home feed loaded
4. input tap FAB (964, 1891)                # open creation menu
5. input tap FAB again                      # select Post → compose screen
6. YADB -layout                             # verify compose screen open
7. AdbKeyboard ADB_INPUT_B64 broadcast      # type tweet (base64, handles emoji/newlines)
8. YADB -layout                             # verify text in field
9. input tap POST (957, 158)                # submit
10. YADB -layout                            # verify compose gone = success
```

## Calibration (New Device)

Default coordinates are for **Samsung Galaxy Note 10 (1080×2340)**. For a different phone:

```bash
./calibrate.sh
# Prints: FAB_X=N; FAB_Y=N; TEXT_X=N; TEXT_Y=N; POST_X=N; POST_Y=N
# Update these values in post.sh config section
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADB_DEVICE` | auto-detected | ADB serial from `adb devices` |
| `ADB_BIN` | `adb` | Path to `adb` binary |

```bash
ADB_DEVICE=RF8M90JL60K ./post.sh "My tweet"
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `YADB not on device` | Run `./setup.sh` |
| `Compose screen did not open` | X opened to wrong screen — script auto force-stops, retry once |
| `Tweet field appears empty` | AdbKeyboard not active IME — run `./setup.sh` |
| `adb: device not found` | Run `adb kill-server && adb start-server && adb devices` |
| Duplicate tweets | Never run two instances on same device simultaneously |

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — agent instructions |
| `README.md` | Human-readable docs |
| `post.sh` | Post text tweet |
| `post-with-image.sh` | Post tweet with image attachment |
| `setup.sh` | One-time device setup |
| `calibrate.sh` | Auto-detect coordinates for any device |
