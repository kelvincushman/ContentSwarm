#!/bin/bash
# ============================================================
# x-phone-poster — post.sh
# Post a tweet to X via ADB + YADB + AdbKeyboard
# Usage: ./post.sh "Your tweet text here"
# ============================================================

set -e

# ── Config ──────────────────────────────────────────────────
DEVICE="${ADB_DEVICE:-$(adb devices | awk '/device$/{print $1; exit}')}"
ADB_BIN="${ADB_BIN:-adb}"
ADB="$ADB_BIN -s $DEVICE"
YADB_REMOTE="/data/local/tmp/yadb"
YADB_CMD="$ADB shell app_process -Djava.class.path=$YADB_REMOTE /data/local/tmp com.ysbing.yadb.Main"
TWITTER_PKG="com.twitter.android"
TWITTER_ACTIVITY="$TWITTER_PKG/.StartActivity"

# Confirmed coordinates for Samsung Galaxy Note 10 (1080×2340)
# Run ./calibrate.sh on a different device to get new values
FAB_X=964; FAB_Y=1891        # "New post" FAB button
TEXT_X=600; TEXT_Y=419       # Tweet compose text field
POST_X=957; POST_Y=158       # POST button in composer toolbar

SLEEP_LAUNCH=3               # seconds to wait after app launch
SLEEP_FAB=1.5                # seconds to wait after FAB tap
SLEEP_COMPOSE=2              # seconds to wait for compose screen
SLEEP_AFTER_POST=3           # seconds to wait after tapping POST
# ────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

TWEET_TEXT="$1"
[ -z "$TWEET_TEXT" ] && err "Usage: $0 \"Your tweet text\""

# ── Preflight ────────────────────────────────────────────────
log "Device: $DEVICE"
[ -z "$DEVICE" ] && err "No ADB device found. Connect via USB or set ADB_DEVICE."
$ADB shell ls "$YADB_REMOTE" &>/dev/null || err "YADB not on device. Run ./setup.sh first."
$ADB shell pm list packages | grep -q "com.android.adbkeyboard" || err "AdbKeyboard not installed. Run ./setup.sh first."
$ADB shell pm list packages | grep -q "$TWITTER_PKG" || err "X (Twitter) app not installed on device."

# ── Step 1: Fresh launch ─────────────────────────────────────
log "Launching X..."
$ADB shell am force-stop "$TWITTER_PKG"
sleep 1
$ADB shell am start -n "$TWITTER_ACTIVITY"
sleep $SLEEP_LAUNCH

# ── Step 2: Open compose via FAB (tap twice — first opens menu, second selects Post) ──
log "Opening compose screen..."
$ADB shell input tap $FAB_X $FAB_Y
sleep $SLEEP_FAB
$ADB shell input tap $FAB_X $FAB_Y
sleep $SLEEP_COMPOSE

# ── Step 3: Verify compose screen is open ────────────────────
log "Verifying compose screen..."
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_layout.xml > /dev/null 2>&1
if ! grep -q "tweet_text" /tmp/xpost_layout.xml; then
    err "Compose screen did not open. Check device state and retry."
fi
log "Compose screen confirmed ✅"

# ── Step 4: Type tweet text via AdbKeyboard (base64) ─────────
log "Setting input method..."
$ADB shell ime set com.android.adbkeyboard/.AdbIME > /dev/null
$ADB shell settings put secure default_input_method com.android.adbkeyboard/.AdbIME
sleep 0.5

log "Tapping text field..."
$ADB shell input tap $TEXT_X $TEXT_Y
sleep 0.5

log "Typing tweet text..."
B64=$(echo -n "$TWEET_TEXT" | base64 -w0)
$ADB shell am broadcast -a ADB_INPUT_B64 --es msg "$B64" > /dev/null
sleep 1

# ── Step 5: Verify text was entered ─────────────────────────
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_typed.xml > /dev/null 2>&1
FIELD_TEXT=$(grep 'tweet_text' /tmp/xpost_typed.xml | sed 's/.*text="\([^"]*\)".*/\1/')
if [ -z "$FIELD_TEXT" ]; then
    err "Tweet field appears empty after typing. Aborting."
fi
log "Text confirmed in field: \"${FIELD_TEXT:0:50}...\""

# ── Step 6: Tap POST ─────────────────────────────────────────
log "Posting..."
$ADB shell input tap $POST_X $POST_Y
sleep $SLEEP_AFTER_POST

# ── Step 7: Verify success ───────────────────────────────────
$ADB shell screencap -p /data/local/tmp/xpost_result.png
$ADB pull /data/local/tmp/xpost_result.png /tmp/xpost_result.png > /dev/null 2>&1
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_result_layout.xml > /dev/null 2>&1

# Check for home feed (composer gone = success)
if ! grep -q "tweet_text" /tmp/xpost_result_layout.xml; then
    log "Tweet posted successfully ✅"
    echo "Screenshot saved to /tmp/xpost_result.png"
    exit 0
else
    warn "Compose screen still visible — POST may not have worked."
    warn "Check /tmp/xpost_result.png for details."
    exit 1
fi
