#!/usr/bin/env python3
"""
X/Twitter Scheduler for Nova — posts from Google Sheets "X Queue" via ContentSwarm API.
Runs 5x daily at 07:43, 11:17, 14:52, 18:33, 21:09 UTC.
"""
import json
import subprocess
import sys
import time
import os
from datetime import datetime, timezone

SPREADSHEET_ID = "1I3bUdlrcFeahUVJmsi-PX7H2LMWxAab_X-iUtsZqR6I"
SHEET_RANGE = "X Queue!A:H"
AI_SERVER = "aiserver@192.168.55.231"
LOG_FILE = "/home/pai-server/logs/x_scheduler.log"
TELEGRAM_TOKEN_FILE = os.path.expanduser("~/.secrets/telegram-bot")

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def send_telegram(msg):
    """Send Telegram notification on failure."""
    if not os.path.exists(TELEGRAM_TOKEN_FILE):
        return
    try:
        token = open(TELEGRAM_TOKEN_FILE).read().strip()
        # Token format: BOT_TOKEN:CHAT_ID
        parts = token.split(":")
        if len(parts) >= 3:
            bot_token = ":".join(parts[:2])
            chat_id = parts[2]
        else:
            return
        subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"https://api.telegram.org/bot{bot_token}/sendMessage",
             "-d", f"chat_id={chat_id}", "-d", f"text={msg}"],
            capture_output=True, timeout=15
        )
    except Exception as e:
        log(f"Telegram notify failed: {e}")

def gws_read_sheet():
    """Read X Queue from Google Sheets."""
    params = json.dumps({"spreadsheetId": SPREADSHEET_ID, "range": SHEET_RANGE})
    result = subprocess.run(
        ["gws", "sheets", "spreadsheets", "values", "get", "--params", params],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"gws read failed: {result.stderr}")
    data = json.loads(result.stdout)
    return data.get("values", [])

def gws_update_row(row_num, values):
    """Update a single row in the X Queue sheet."""
    range_str = f"X Queue!A{row_num}:H{row_num}"
    params = json.dumps({
        "spreadsheetId": SPREADSHEET_ID,
        "range": range_str,
        "valueInputOption": "RAW"
    })
    body = json.dumps({"values": [values]})
    result = subprocess.run(
        ["gws", "sheets", "spreadsheets", "values", "update", "--params", params, "--json", body],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"gws update failed: {result.stderr}")

def gws_add_calendar_event(tweet_text, posted_time):
    """Add a calendar event for the posted tweet."""
    summary = f"X Post: {tweet_text[:60]}..."
    event = {
        "summary": summary,
        "description": tweet_text,
        "start": {"dateTime": posted_time, "timeZone": "UTC"},
        "end": {"dateTime": posted_time, "timeZone": "UTC"}
    }
    params = json.dumps({"calendarId": "primary"})
    result = subprocess.run(
        ["gws", "calendar", "events", "insert", "--params", params, "--json", json.dumps(event)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log(f"Calendar event failed: {result.stderr[:200]}")
    else:
        log("Calendar event created")

def ssh_post(tweet_text):
    """Post directly via SSH + Python — bypasses Flask API, uses base64 to safely pass text."""
    import base64 as _b64
    b64_text = _b64.b64encode(tweet_text.encode("utf-8")).decode("utf-8")
    cmd = (
        f"source /home/aiserver/miniconda3/bin/activate wan2gp && "
        f"cd /home/aiserver/contentswarm && "
        f"python3 -c \""
        f"import sys, base64; sys.path.insert(0, '.'); "
        f"from phone_agent.posting.twitter import post_to_twitter; "
        f"text = base64.b64decode('{b64_text}').decode('utf-8'); "
        f"result = post_to_twitter('RF8M90JL60K', text); "
        f"print('SUCCESS' if result else 'FAILED'); "
        f"sys.exit(0 if result else 1)"
        f"\" 2>&1"
    )
    result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-T", AI_SERVER, cmd],
        capture_output=True, text=True, timeout=120
    )
    output = result.stdout.strip()
    log(f"SSH post output: {output[-300:] if output else '(empty)'}")
    if result.returncode != 0 or "FAILED" in output:
        raise RuntimeError(f"Post failed: {output}")
    if "SUCCESS" not in output:
        raise RuntimeError(f"Unexpected output: {output}")
    return {"status": "posted", "output": output}

def ssh_check_queue():
    """Placeholder — no longer needed with direct SSH posting."""
    return {"pending_count": 0}

def parse_scheduled_time(sched_str):
    """Parse scheduled time string to datetime."""
    if not sched_str:
        return None
    sched_str = sched_str.strip()
    sched_str = sched_str.replace("Z", "+00:00")
    if "+" not in sched_str[10:] and "-" not in sched_str[11:]:
        sched_str += "+00:00"
    dt = datetime.fromisoformat(sched_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def main():
    log("── X Scheduler run ──")

    try:
        rows = gws_read_sheet()
    except Exception as e:
        log(f"FATAL: Cannot read sheet: {e}")
        sys.exit(1)

    if len(rows) < 2:
        log("No data rows in X Queue")
        sys.exit(0)

    header = rows[0]
    now = datetime.now(timezone.utc)

    # Find pending posts that are due (Scheduled Time <= now)
    due_posts = []
    fallback_post = None  # Next pending post if none are due

    for i, row in enumerate(rows[1:], start=2):
        # Pad row to 8 columns
        while len(row) < 8:
            row.append("")

        status = row[4].strip().lower() if len(row) > 4 else ""
        if status != "pending":
            continue

        sched_str = row[3] if len(row) > 3 else ""
        try:
            sched_dt = parse_scheduled_time(sched_str)
        except Exception:
            sched_dt = None

        if sched_dt and sched_dt <= now:
            due_posts.append((i, row, sched_dt))
        elif fallback_post is None:
            fallback_post = (i, row, sched_dt)

    # If no due posts and no pending posts at all, exit
    if not due_posts and fallback_post is None:
        log("No pending posts in queue")
        sys.exit(0)

    # If no due posts, pick the next pending one (fallback)
    if not due_posts:
        log("No posts due right now — picking next pending post as fallback")
        due_posts = [fallback_post]

    # Sort by scheduled time (oldest first)
    due_posts.sort(key=lambda x: x[2] or now)

    # Post one tweet per run
    row_num, row, sched_dt = due_posts[0]
    tweet_id = row[0]
    tweet_text = row[1]
    log(f"Posting [{tweet_id}]: {tweet_text[:80]}...")

    try:
        # Post directly via SSH (synchronous)
        resp = ssh_post(tweet_text)
        log(f"Post result: {resp}")

        # Update Google Sheet — mark as posted
        posted_at = datetime.now(timezone.utc).isoformat()
        row[4] = "posted"
        row[5] = posted_at
        row[7] = ""
        gws_update_row(row_num, row)
        log(f"Sheet updated: row {row_num} = posted")

        # Add calendar event
        gws_add_calendar_event(tweet_text, posted_at)

        log(f"SUCCESS: [{tweet_id}] posted")

    except Exception as e:
        error_msg = str(e)[:200]
        log(f"FAILED: [{tweet_id}] — {error_msg}")

        # Update sheet with failure
        try:
            row[4] = "failed"
            row[7] = error_msg
            gws_update_row(row_num, row)
        except Exception as ue:
            log(f"Sheet update also failed: {ue}")

        # Send Telegram notification
        send_telegram(f"X Scheduler FAILED: [{tweet_id}] {error_msg}")
        sys.exit(1)

    log("── X Scheduler done ──")
    sys.exit(0)

if __name__ == "__main__":
    main()


def schedule_funnel_after_thread(offer_text=""):
    """Called after a thread is posted — writes schedule file so funnel_cron fires at right intervals."""
    import time as _t
    import os
    os.makedirs("/home/pai-server/marketing", exist_ok=True)
    sched = {
        "posted_at": _t.time(),
        "offer": offer_text or "Hey! 👋 Thanks for the repost 🙏 Tell me your business name + what you do and I'll put together a personalised AiGENTIS breakdown — exactly what the 7 AI agents could do for you. Reply here and let's chat 🤙🏻",
        "fired": []
    }
    import json as _j
    _j.dump(sched, open("/home/pai-server/marketing/funnel_schedule.json", "w"), indent=2)
    log(f"Funnel schedule created — 8 checks: +10m, +20m, +30m, +1h, +2h, +4h, +8h, +12h")
