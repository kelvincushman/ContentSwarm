"""
Zara Scheduler — reads queue, SSHes to Lenovo, runs posts at the right time.

Posting schedule (UK time, BST = UTC+1, GMT = UTC):
  TikTok:    Tue 18:00, Thu 17:00, Sat 11:00 UK
  Instagram: Wed 19:00, Sun 12:00 UK
  Twitter:   daily 07:43, 12:17, 19:52 UK

This scheduler is intended to be run as a long-running daemon on pai-server,
or alternatively the cron-based zara-post.py approach handles the same logic.
Use this file for manual schedule checks or daemon mode.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import pytz
    TZ_UK = pytz.timezone("Europe/London")
except ImportError:
    TZ_UK = None

QUEUE_DIR = Path("/home/pai-server/marketing/zara/queue")
LENOVO_HOST = "192.168.55.124"
LENOVO_USER = "lenovo"
LENOVO_PASS = "Mercia2025.!"
LENOVO_RUN_POST = "/home/lenovo/contentswarm/agents/zara/run_post.py"

TELEGRAM_BOT_TOKEN_FILE = "/home/pai-server/.secrets/telegram-signals-bot"
KELVIN_CHAT_ID = "1486798034"

# Schedule: (weekday 0=Mon, hour_utc, minute_utc, platform)
# UK BST (summer, UTC+1): subtract 1 for UTC
# UK GMT (winter, UTC+0): same
# Using UTC-1 approximation (BST) for summer schedule
SCHEDULE = [
    # TikTok: Tue 18:00 UK → 17:00 UTC (BST)
    (1, 17, 0, "tiktok"),
    # TikTok: Thu 17:00 UK → 16:00 UTC (BST)
    (3, 16, 0, "tiktok"),
    # TikTok: Sat 11:00 UK → 10:00 UTC (BST)
    (5, 10, 0, "tiktok"),
    # Instagram: Wed 19:00 UK → 18:00 UTC (BST)
    (2, 18, 0, "instagram"),
    # Instagram: Sun 12:00 UK → 11:00 UTC (BST)
    (6, 11, 0, "instagram"),
    # Twitter: 07:43, 12:17, 19:52 UK → 06:43, 11:17, 18:52 UTC (BST)
    (-1, 6, 43, "twitter"),   # -1 = every day
    (-1, 11, 17, "twitter"),
    (-1, 18, 52, "twitter"),
]


def _send_telegram(message: str) -> None:
    """Send Telegram notification to Kelvin."""
    try:
        bot_token = open(TELEGRAM_BOT_TOKEN_FILE).read().strip()
        import urllib.request
        data = json.dumps({"chat_id": KELVIN_CHAT_ID, "text": message}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"⚠️  Telegram notification failed: {e}")


def get_next_post(platform: str) -> Optional[dict]:
    """
    Get the next pending post from the queue for the given platform.

    Returns:
        Post dict with keys: platform, text, media, status
        or None if no pending posts.
    """
    queue_file = QUEUE_DIR / "queue.json"
    if not queue_file.exists():
        return None

    posts = json.loads(queue_file.read_text())
    for post in posts:
        if post.get("platform") == platform and post.get("status") == "pending":
            return post
    return None


def mark_post_sent(post_id: str, platform: str) -> None:
    """Mark a post as sent in the queue file."""
    queue_file = QUEUE_DIR / "queue.json"
    if not queue_file.exists():
        return

    posts = json.loads(queue_file.read_text())
    for post in posts:
        if post.get("id") == post_id and post.get("platform") == platform:
            post["status"] = "sent"
            post["sent_at"] = datetime.now(timezone.utc).isoformat()
            break

    queue_file.write_text(json.dumps(posts, indent=2, ensure_ascii=False))


def ssh_run_post(platform: str, text: str, media: str = "") -> str:
    """
    SSH to Lenovo and run run_post.py with the given args.

    Returns:
        Output from the remote command.
    """
    try:
        import paramiko
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            LENOVO_HOST,
            username=LENOVO_USER,
            password=LENOVO_PASS,
            timeout=30,
        )
        cmd = (
            f"cd /home/lenovo/ContentSwarm && "
            f"python3 agents/zara/run_post.py "
            f"--platform {platform} "
            f"--text {json.dumps(text)} "
        )
        if media:
            cmd += f"--media {json.dumps(media)} "

        stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
        output = stdout.read().decode()
        errors = stderr.read().decode()
        client.close()

        if errors:
            print(f"⚠️  SSH stderr: {errors}")
        return output

    except ImportError:
        # Fallback: subprocess ssh (requires passwordless key or sshpass)
        cmd = [
            "sshpass", "-p", LENOVO_PASS,
            "ssh", "-o", "StrictHostKeyChecking=no",
            f"{LENOVO_USER}@{LENOVO_HOST}",
            f"cd /home/lenovo/ContentSwarm && python3 agents/zara/run_post.py "
            f"--platform {platform} --text {json.dumps(text)}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"SSH failed: {result.stderr}")
        return result.stdout


def run_scheduled_post(platform: str) -> bool:
    """
    Fetch the next pending post for a platform and execute it.

    Returns:
        True if post was sent, False if nothing to post.
    """
    post = get_next_post(platform)
    if not post:
        print(f"📭 No pending {platform} posts in queue.")
        return False

    text = post.get("text", "")
    media = post.get("media", "")
    post_id = post.get("id", "")

    print(f"\n📤 Running scheduled {platform} post: {text[:80]}...")

    try:
        result = ssh_run_post(platform, text, media)
        print(f"✅ Post result: {result}")
        mark_post_sent(post_id, platform)
        _send_telegram(
            f"✅ Zara posted to {platform.title()}: {text[:50]}..."
        )
        return True
    except Exception as e:
        print(f"❌ Post failed: {e}")
        _send_telegram(f"❌ Zara failed to post to {platform.title()}: {e}")
        return False


def daemon_loop() -> None:
    """
    Run as a daemon, checking schedule every minute.
    Not needed if using cron — but available for manual daemon mode.
    """
    print("🕐 Zara scheduler daemon started.")
    fired = set()

    while True:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Mon
        hour = now.hour
        minute = now.minute
        slot_key = f"{weekday}-{hour}-{minute}"

        for (sched_day, sched_hour, sched_min, platform) in SCHEDULE:
            matches_day = (sched_day == -1) or (sched_day == weekday)
            matches_time = (sched_hour == hour) and (sched_min == minute)

            if matches_day and matches_time and slot_key not in fired:
                print(f"\n⏰ Schedule hit: {platform} at {now.isoformat()}")
                run_scheduled_post(platform)
                fired.add(slot_key)

        # Prune fired set every hour to allow re-firing next week
        if minute == 0 and len(fired) > 100:
            fired.clear()

        time.sleep(30)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Zara Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--post", choices=["twitter", "tiktok", "instagram"],
                        help="Post immediately to platform")
    args = parser.parse_args()

    if args.daemon:
        daemon_loop()
    elif args.post:
        run_scheduled_post(args.post)
    else:
        parser.print_help()
