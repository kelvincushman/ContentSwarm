#!/usr/bin/env python3
"""
Funnel cron — reads funnel_schedule.json, checks if elapsed time matches
a scheduled check interval, and fires the phone funnel if so.

Runs every 5 minutes via cron. Fires at: +10, +20, +30, +60, +120, +240, +480, +720 min
"""
import json, os, time, subprocess
from datetime import datetime, timezone

SCHEDULE_FILE = "/home/pai-server/marketing/funnel_schedule.json"
AI_SERVER = "aiserver@192.168.55.231"
INTERVALS = [10, 20, 30, 60, 120, 240, 480, 720]  # minutes after thread post
TOLERANCE = 6  # fire if within ±6 min of target

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open("/home/pai-server/logs/funnel_cron.log", "a") as f:
        f.write(line + "\n")

def load_schedule():
    try:    return json.load(open(SCHEDULE_FILE))
    except: return None

def mark_fired(data, interval):
    data["fired"].append(interval)
    json.dump(data, open(SCHEDULE_FILE, "w"), indent=2)

def run_funnel_on_aiserver(offer):
    cmd = (
        "source /home/aiserver/miniconda3/bin/activate wan2gp && "
        "cd /home/aiserver/contentswarm && "
        "python3 thread_dm_funnel.py >> /home/aiserver/contentswarm/funnel_run.log 2>&1"
    )
    result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-T", AI_SERVER, cmd],
        capture_output=True, text=True, timeout=300
    )
    log(f"Funnel run exit code: {result.returncode}")
    return result.returncode == 0

def main():
    sched = load_schedule()
    if not sched:
        return  # No active thread

    thread_time = sched.get("posted_at", 0)
    fired = sched.get("fired", [])
    now = time.time()
    elapsed_min = (now - thread_time) / 60

    for interval in INTERVALS:
        if interval in fired:
            continue
        # Check if we're within tolerance of this interval
        diff = abs(elapsed_min - interval)
        if diff <= TOLERANCE:
            log(f"Firing funnel check at +{interval}min (elapsed={elapsed_min:.1f}min)")
            run_funnel_on_aiserver(sched.get("offer", ""))
            mark_fired(sched, interval)
            log(f"Funnel check +{interval}min complete ✅")
            break

    # Clean up if all intervals fired
    if all(i in sched.get("fired", []) for i in INTERVALS):
        log("All 8 funnel intervals complete — clearing schedule")
        os.remove(SCHEDULE_FILE)

if __name__ == "__main__":
    main()
