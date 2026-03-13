#!/bin/bash
# ============================================================
# x-phone-poster — calibrate.sh
# Find the correct tap coordinates for your specific device
# Run this once when setting up on a new phone
# ============================================================

ADB_BIN="${ADB_BIN:-adb}"
DEVICE="${ADB_DEVICE:-$($ADB_BIN devices | awk '/device$/{print $1; exit}')}"
ADB="$ADB_BIN -s $DEVICE"
YADB_CMD="$ADB shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }

log "Device: $DEVICE"
log "Resolution: $($ADB shell wm size)"
echo ""

# ── Step 1: Home feed → find FAB ────────────────────────────
log "Launching X and finding FAB (composer_write)..."
$ADB shell am force-stop com.twitter.android
sleep 1
$ADB shell am start -n com.twitter.android/.StartActivity
sleep 3

$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/cal_home.xml > /dev/null 2>&1

FAB_BOUNDS=$(grep 'composer_write' /tmp/cal_home.xml | sed 's/.*bounds="\([^"]*\)".*/\1/')
if [ -n "$FAB_BOUNDS" ]; then
    FAB_X=$(echo "$FAB_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($1+$3)/2)}')
    FAB_Y=$(echo "$FAB_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($2+$4)/2)}')
    log "FAB found: bounds=$FAB_BOUNDS → center=($FAB_X, $FAB_Y)"
else
    warn "FAB not found — X may not be on home feed. Try again."
    exit 1
fi

# ── Step 2: Open compose → find tweet_text and button_tweet ─
log "Opening compose screen..."
$ADB shell input tap $FAB_X $FAB_Y
sleep 1.5
$ADB shell input tap $FAB_X $FAB_Y
sleep 2

$YADB_CMD -layout > /dev/null 2>&1
$ADB pull /data/local/tmp/yadb_layout_dump.xml /tmp/cal_compose.xml > /dev/null 2>&1

TEXT_BOUNDS=$(grep 'tweet_text' /tmp/cal_compose.xml | sed 's/.*bounds="\([^"]*\)".*/\1/')
POST_BOUNDS=$(grep 'button_tweet' /tmp/cal_compose.xml | sed 's/.*bounds="\([^"]*\)".*/\1/')

if [ -n "$TEXT_BOUNDS" ]; then
    TEXT_X=$(echo "$TEXT_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($1+$3)/2)}')
    TEXT_Y=$(echo "$TEXT_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($2+$4)/2)}')
    log "Text field: bounds=$TEXT_BOUNDS → center=($TEXT_X, $TEXT_Y)"
else
    warn "Tweet text field not found"
fi

if [ -n "$POST_BOUNDS" ]; then
    POST_X=$(echo "$POST_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($1+$3)/2)}')
    POST_Y=$(echo "$POST_BOUNDS" | sed 's/\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]/\1 \2 \3 \4/' | awk '{print int(($2+$4)/2)}')
    log "POST button: bounds=$POST_BOUNDS → center=($POST_X, $POST_Y)"
else
    warn "POST button not found"
fi

# ── Output ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}Add these to post.sh:${NC}"
echo "FAB_X=$FAB_X; FAB_Y=$FAB_Y"
echo "TEXT_X=$TEXT_X; TEXT_Y=$TEXT_Y"
echo "POST_X=$POST_X; POST_Y=$POST_Y"

# Press back to dismiss compose
$ADB shell input keyevent 4
