#!/usr/bin/env python3
"""
Thread Scheduler — posts from 'Thread Queue' sheet tab, Mon/Wed/Fri 07:43 UTC.
After posting, automatically schedules 8 DM funnel checks.
"""
import json, subprocess, sys, time, base64, os
from datetime import datetime, timezone

SPREADSHEET_ID = "1I3bUdlrcFeahUVJmsi-PX7H2LMWxAab_X-iUtsZqR6I"
AI_SERVER = "aiserver@192.168.55.231"
LOG_FILE = "/home/pai-server/logs/thread_scheduler.log"
OFFER = "Hey! 👋 Thanks for the repost 🙏 Tell me your business name + what you do and I'll put together a personalised AiGENTIS breakdown — exactly what the 7 AI agents could do for you. Reply here and let's chat 🤙🏻"

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs("/home/pai-server/logs", exist_ok=True)
    with open(LOG_FILE, "a") as f: f.write(line + "\n")

def gws_read():
    p = json.dumps({"spreadsheetId": SPREADSHEET_ID, "range": "Thread Queue!A:I"})
    r = subprocess.run(["gws", "sheets", "spreadsheets", "values", "get", "--params", p],
                       capture_output=True, text=True, timeout=30)
    d = json.loads(r.stdout)
    return d.get("values", [])

def gws_update(row_num, values):
    rng = f"Thread Queue!A{row_num}:I{row_num}"
    p = json.dumps({"spreadsheetId": SPREADSHEET_ID, "range": rng, "valueInputOption": "RAW"})
    b = json.dumps({"values": [values]})
    subprocess.run(["gws", "sheets", "spreadsheets", "values", "update", "--params", p, "--json", b],
                   capture_output=True, text=True, timeout=30)

def ssh_post_thread(tweets):
    enc_list = json.dumps([base64.b64encode(t.encode()).decode() for t in tweets])
    cmd = (
        f"source /home/aiserver/miniconda3/bin/activate wan2gp && "
        f"cd /home/aiserver/contentswarm && "
        f"python3 -c \""
        f"import sys, base64, json; sys.path.insert(0, '.'); "
        f"from phone_agent.posting.twitter import post_thread_to_twitter; "
        f"tweets = [base64.b64decode(b).decode('utf-8') for b in json.loads('{enc_list.replace(chr(39), chr(34))}')]; "
        f"result = post_thread_to_twitter('RF8M90JL60K', tweets); "
        f"print('SUCCESS' if result else 'FAILED'); sys.exit(0 if result else 1)"
        f"\" 2>&1"
    )
    r = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-T", AI_SERVER, cmd],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout.strip()
    log(f"Thread post output: {out[-300:]}")
    return "SUCCESS" in out

def schedule_funnel():
    sched = {"posted_at": time.time(), "offer": OFFER, "fired": []}
    os.makedirs("/home/pai-server/marketing", exist_ok=True)
    json.dump(sched, open("/home/pai-server/marketing/funnel_schedule.json", "w"), indent=2)
    log("Funnel schedule created: +10m, +20m, +30m, +1h, +2h, +4h, +8h, +12h")

def main():
    log("── Thread Scheduler run ──")
    rows = gws_read()
    if len(rows) < 2:
        log("No threads in queue"); return

    headers = rows[0]
    # Find next pending thread
    pending = None
    for i, row in enumerate(rows[1:], 2):
        while len(row) < 9: row.append("")
        status = row[7] if len(row) > 7 else ""
        if status.lower() == "pending":
            pending = (i, row)
            break

    if not pending:
        log("No pending threads"); return

    row_num, row = pending
    thread_id = row[0]
    tweets = [row[j] for j in range(1, 6) if len(row) > j and row[j].strip()]

    if not tweets:
        log(f"Thread {thread_id} has no tweet content"); return

    log(f"Posting thread {thread_id} ({len(tweets)} tweets)...")

    if ssh_post_thread(tweets):
        # Update sheet
        row[7] = "posted"
        row[8] = datetime.now(timezone.utc).isoformat()
        gws_update(row_num, row)
        log(f"SUCCESS: {thread_id} posted ✅")
        # Schedule funnel checks
        schedule_funnel()
    else:
        row[7] = "failed"
        gws_update(row_num, row)
        log(f"FAILED: {thread_id}")

if __name__ == "__main__":
    main()
