#!/bin/bash
# ============================================================
# x-phone-poster — setup.sh
# Install YADB and AdbKeyboard on a connected Android device
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

ADB_BIN="${ADB_BIN:-adb}"
DEVICE="${ADB_DEVICE:-$($ADB_BIN devices | awk '/device$/{print $1; exit}')}"
ADB="$ADB_BIN -s $DEVICE"

[ -z "$DEVICE" ] && err "No ADB device found. Ensure USB debugging is enabled and device is connected."
log "Device: $DEVICE"

# ── 1. Download and push YADB ────────────────────────────────
log "Downloading YADB..."
curl -sL "https://github.com/ysbing/YADB/releases/download/v1.0.0/yadb" -o /tmp/yadb
FILE_SIZE=$(stat -c%s /tmp/yadb 2>/dev/null || stat -f%z /tmp/yadb)
[ "$FILE_SIZE" -lt 1000 ] && err "YADB download failed (got $FILE_SIZE bytes). Check network."

log "Pushing YADB to device..."
$ADB push /tmp/yadb /data/local/tmp/yadb
$ADB shell chmod 755 /data/local/tmp/yadb

log "Testing YADB..."
$ADB shell app_process -Djava.class.path=/data/local/tmp/yadb /data/local/tmp com.ysbing.yadb.Main -layout > /dev/null 2>&1
log "YADB working ✅"

# ── 2. Download and install AdbKeyboard ─────────────────────
log "Downloading AdbKeyboard..."
curl -sL "https://github.com/senzhk/ADBKeyBoard/releases/download/v2.0/ADBKeyboard.apk" -o /tmp/ADBKeyboard.apk
APK_SIZE=$(stat -c%s /tmp/ADBKeyboard.apk 2>/dev/null || stat -f%z /tmp/ADBKeyboard.apk)
[ "$APK_SIZE" -lt 10000 ] && err "AdbKeyboard APK download failed. Check network."

log "Installing AdbKeyboard..."
$ADB install -r /tmp/ADBKeyboard.apk

log "Enabling AdbKeyboard..."
$ADB shell ime enable com.android.adbkeyboard/.AdbIME

log "Testing AdbKeyboard..."
$ADB shell pm list packages | grep -q "com.android.adbkeyboard" && log "AdbKeyboard installed ✅" || err "AdbKeyboard install failed."

# ── 3. Keep screen on while plugged in ──────────────────────
log "Setting screen stay-awake while charging..."
$ADB shell settings put global stay_on_while_plugged_in 3
log "Stay-awake set ✅"

# ── 4. Enable USB debugging confirmation ────────────────────
log "Verifying ADB connection..."
$ADB shell echo "ADB OK"

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN} Setup complete! ✅${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "Usage:"
echo "  ./post.sh \"Your tweet text here\""
echo ""
echo "Note: On a new device, run ./calibrate.sh to find correct tap coordinates."
