# x-phone-poster

> Post to X (Twitter) via ADB — no API key, no rate limits, no app review.

Automates posting tweets through a physical Android phone connected via USB. Uses [YADB](https://github.com/ysbing/YADB) for reliable UI inspection and [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) for Unicode-safe text input (including emoji and newlines).

---

## Why

X's API requires your app to be attached to a **Project** in the developer portal. Approved write access is rate-limited to 17 tweets/day on the free tier, and $100/month for anything serious.

This bypasses all of that by controlling a real phone over USB — the same way a human would post.

**Works with any Android phone.** Tested on Samsung Galaxy Note 10 (Android 12).

---

## How it works

```
ADB (USB)
  └── force-stop X → fresh launch → home feed
        └── tap FAB (compose button) → opens creation menu
              └── tap FAB again → opens compose screen
                    └── YADB -layout → verify compose is actually open
                          └── AdbKeyboard broadcast → types tweet (base64, handles emoji/newlines)
                                └── tap POST button → tweet sent
                                      └── YADB -layout → verify compose is gone (success)
```

### Key components

| Tool | What it does | Why not the alternative? |
|------|-------------|--------------------------|
| [YADB](https://github.com/ysbing/YADB) | UI layout dump via `app_process` | `uiautomator dump` fails on X's compose screen |
| [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) | Text input via base64 broadcast | `adb shell input text` breaks on emoji, newlines, special chars |
| `adb input tap` | Navigate the UI | Good enough for known coordinates |

---

## Requirements

- Android phone with **USB debugging enabled**
- ADB installed on your machine (`brew install android-platform-tools` / `apt install adb`)
- X (Twitter) app installed and **logged in** on the phone
- USB cable connecting phone to machine

---

## Setup

```bash
git clone https://github.com/kelvincushman/x-phone-poster
cd x-phone-poster
chmod +x *.sh

# Connect phone via USB, accept the "Allow USB debugging" prompt, then:
./setup.sh
```

This will:
1. Download and push **YADB** to `/data/local/tmp/yadb` on the device
2. Download and install **AdbKeyboard** APK
3. Set screen stay-awake while charging (prevents auto-lock mid-post)

---

## Usage

```bash
# Post a single tweet
./post.sh "Your tweet text here"

# Multi-line tweet with emoji
./post.sh "Building in public day 47.

No prompting. No copy-paste. Just described what I wanted and watched it happen.

This is what building feels like now. 🛠️

#BuildInPublic #UKtech"
```

### From a script / cron

```bash
#!/bin/bash
TWEET=$(cat queue.txt | head -1)
./post.sh "$TWEET" && sed -i '1d' queue.txt  # remove first line after posting
```

---

## Different device? Run calibration

The tap coordinates in `post.sh` are calibrated for a **Samsung Galaxy Note 10 (1080×2340)**. If you're using a different phone:

```bash
./calibrate.sh
```

This automatically finds the correct coordinates using YADB's layout dump and prints the values to paste into `post.sh`.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADB_DEVICE` | auto-detected | ADB device serial (from `adb devices`) |
| `ADB_BIN` | `adb` | Path to `adb` binary |

```bash
# Multiple devices connected? Target a specific one:
ADB_DEVICE=RF8M90JL60K ./post.sh "My tweet"
```

---

## Troubleshooting

**`YADB not on device`** — Run `./setup.sh`

**`Compose screen did not open`** — X may have launched to a DM or post detail instead of the home feed. The script does `am force-stop` before each run to ensure a clean state. If it still fails, check if X shows an account selection or onboarding screen.

**`Tweet field appears empty after typing`** — AdbKeyboard might not be set as the active IME. Run `./setup.sh` again, or manually go to: *Settings → General Management → Keyboard → Default keyboard → ADB Keyboard*.

**`adb: device not found`** — Restart the ADB daemon:
```bash
adb kill-server && adb start-server && adb devices
```

**Duplicate tweets** — Never run two instances of `post.sh` in parallel on the same device. The scripts share the compose screen.

---

## Architecture notes

### Why two FAB taps?

In newer versions of X, tapping the compose FAB (floating action button) opens a **creation menu** with four options: Go Live, Spaces, Photos, Post. The Post option is the same FAB button. Tapping it a second time selects Post and opens the compose screen.

This is confirmed by inspecting the UI with `yadb -layout` — the `composer_write` resource ID at center `(964, 1891)` is both the FAB and the Post selector in the expanded menu.

### Why YADB instead of uiautomator?

`adb shell uiautomator dump` fails to capture X's compose screen elements in certain states — it returns an empty or partial XML. YADB's `app_process`-based approach bypasses this limitation and reliably returns the full UI tree.

### Why base64 for text input?

`adb shell input text` splits on spaces (shell argument parsing) and silently drops emoji, newlines, and special characters. AdbKeyboard's `ADB_INPUT_B64` broadcast receives a single base64-encoded string that the IME decodes and types in full — including emoji, newlines, hashtags, and any Unicode character.

---

## Tested on

- Samsung Galaxy Note 10 (SM-N970F), Android 12, X app v10.x
- ai-server Ubuntu 24.04, ADB 34.0.5

---

## Credits

- [YADB](https://github.com/ysbing/YADB) by [@ysbing](https://github.com/ysbing) — Android utility extending ADB
- [AdbKeyboard](https://github.com/senzhk/ADBKeyBoard) by [@senzhk](https://github.com/senzhk) — ADB-based keyboard IME

---

## Licence

MIT
