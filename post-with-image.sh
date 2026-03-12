#!/bin/bash
# ============================================================
# x-phone-poster — post-with-image.sh
# Post a tweet with an image attachment via ADB
# Usage: ./post-with-image.sh /path/to/image.jpg "Tweet text"
# ============================================================

set -e

# ── Config ──────────────────────────────────────────────────
DEVICE="${ADB_DEVICE:-$(adb devices | awk '/device$/{print $1; exit}')}"
ADB_BIN="${ADB_BIN:-adb}"
ADB="$ADB_BIN -s $DEVICE"
YADB_REMOTE="/data/local/tmp/yadb"
YADB_CMD="$ADB shell app_process -Djava.class.path=$YADB_REMOTE /data/local/tmp com.ysbing.yadb.Main"
TWITTER_PKG="com.twitter.android"

# Composer toolbar POST button — same for all X versions on this device
POST_X=957; POST_Y=158
TEXT_X=600; TEXT_Y=419
# ────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

IMAGE_PATH="$1"
TWEET_TEXT="$2"

[ -z "$IMAGE_PATH" ] && err "Usage: $0 /path/to/image.jpg \"Tweet text\""
[ -z "$TWEET_TEXT" ] && err "Usage: $0 /path/to/image.jpg \"Tweet text\""
[ ! -f "$IMAGE_PATH" ] && err "Image not found: $IMAGE_PATH"

# ── Preflight ────────────────────────────────────────────────
log "Device: $DEVICE"
[ -z "$DEVICE" ] && err "No ADB device found."
$ADB shell ls "$YADB_REMOTE" &>/dev/null || err "YADB not on device. Run ./setup.sh first."
$ADB shell pm list packages | grep -q "com.android.adbkeyboard" || err "AdbKeyboard not installed. Run ./setup.sh first."

# ── Step 1: Push image to phone ──────────────────────────────
FILENAME=$(basename "$IMAGE_PATH")
REMOTE_PATH="/sdcard/Pictures/xpost_$FILENAME"

log "Pushing image to device..."
$ADB push "$IMAGE_PATH" "$REMOTE_PATH"

# Trigger media scanner so gallery sees the file
$ADB shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
    -d "file://$REMOTE_PATH" > /dev/null 2>&1
sleep 1

# ── Step 2: Open X compose with image via share intent ───────
log "Opening X compose with image attached..."
$ADB shell am force-stop "$TWITTER_PKG"
sleep 1

# Detect MIME type
MIME="image/jpeg"
case "${FILENAME,,}" in
    *.png)  MIME="image/png" ;;
    *.gif)  MIME="image/gif" ;;
    *.webp) MIME="image/webp" ;;
esac

# Use Android share intent — opens X's compose screen with image pre-attached
$ADB shell am start \
    -a android.intent.action.SEND \
    -t "$MIME" \
    --eu android.intent.extra.STREAM "file://$REMOTE_PATH" \
    -p "$TWITTER_PKG"
sleep 3

# ── Step 3: Verify compose is open ───────────────────────────
log "Verifying compose screen..."
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_img_layout.xml > /dev/null 2>&1

if ! grep -q "tweet_text\|composer" /tmp/xpost_img_layout.xml; then
    warn "Share intent didn't open compose directly. Trying fallback..."
    # Fallback: tap the "Post" option if a chooser appeared
    $YADB_CMD -layout > /dev/null 2>&1
    $ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_img2.xml > /dev/null 2>&1
    grep -i "twitter\|post\|tweet" /tmp/xpost_img2.xml | head -3
    sleep 2
    $YADB_CMD -layout > /dev/null 2>&1
    $ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_img3.xml > /dev/null 2>&1
    grep -q "tweet_text\|composer" /tmp/xpost_img3.xml || err "Could not open compose screen with image. Check device state."
fi
log "Compose screen with image confirmed ✅"

# ── Step 4: Type tweet text ───────────────────────────────────
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

# ── Step 5: Verify text ──────────────────────────────────────
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_img_typed.xml > /dev/null 2>&1
FIELD_TEXT=$(grep 'tweet_text' /tmp/xpost_img_typed.xml | sed 's/.*text="\([^"]*\)".*/\1/')
[ -z "$FIELD_TEXT" ] && err "Tweet field appears empty after typing. Aborting."
log "Text confirmed: \"${FIELD_TEXT:0:50}...\""

# ── Step 6: Tap POST ─────────────────────────────────────────
log "Posting..."
$ADB shell input tap $POST_X $POST_Y
sleep 3

# ── Step 7: Verify ───────────────────────────────────────────
$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/xpost_img_result.xml > /dev/null 2>&1
$ADB shell screencap -p /data/local/tmp/xpost_img_result.png
$ADB pull /data/local/tmp/xpost_img_result.png /tmp/xpost_img_result.png > /dev/null 2>&1

if ! grep -q "tweet_text" /tmp/xpost_img_result.xml; then
    log "Tweet with image posted successfully ✅"
    echo "Screenshot saved to /tmp/xpost_img_result.png"

    # Cleanup image from phone
    $ADB shell rm "$REMOTE_PATH" 2>/dev/null || true
    exit 0
else
    warn "Compose screen still visible — POST may not have worked."
    warn "Check /tmp/xpost_img_result.png for details."
    exit 1
fi
