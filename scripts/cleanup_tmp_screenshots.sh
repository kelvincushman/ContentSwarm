#!/usr/bin/env bash
# Remove stale phone-server temp screenshots. Safe to run anytime.
# The server already self-cleans (built-in janitor); this is an optional
# OS-level belt-and-suspenders.
#
# Cron example (every 15 min):
#   */15 * * * * /home/lenovo/contentswarm/scripts/cleanup_tmp_screenshots.sh
#
# Age threshold in minutes (default 10); override: MINUTES=30 ./cleanup...sh
set -euo pipefail
MINUTES="${MINUTES:-10}"
TMPDIR="${TMPDIR:-/tmp}"

removed=$(find "$TMPDIR" -maxdepth 1 -name 'screenshot_*.png' -mmin "+${MINUTES}" -print -delete 2>/dev/null | wc -l)
echo "[cleanup] removed ${removed} temp screenshot(s) older than ${MINUTES}m from ${TMPDIR}"
