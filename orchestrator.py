#!/usr/bin/env python3
"""
orchestrator.py — Phone Farm Orchestrator
Manages up to 10 Android phones for parallel social media automation.

Usage:
  python3 orchestrator.py post        # Post next queued tweet on all active phones
  python3 orchestrator.py thread      # Post next thread on all active phones
  python3 orchestrator.py funnel      # Run DM funnel check on all active phones
  python3 orchestrator.py health      # Check which phones are connected
  python3 orchestrator.py list        # List all registered phones + status
"""
import json, sys, os, time, subprocess, threading, fcntl, traceback
from pathlib import Path
from datetime import datetime, timezone

CONTENTSWARM  = "/home/aiserver/contentswarm"
DEVICES_FILE  = f"{CONTENTSWARM}/devices.json"
LOCKS_DIR     = "/tmp/phone_locks"
LOGS_DIR      = f"{CONTENTSWARM}/logs"
ADB           = "/usr/bin/adb"

os.makedirs(LOCKS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

sys.path.insert(0, CONTENTSWARM)

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def log(device_serial, msg):
    line = f"[{ts()}] [{device_serial[:8]}] {msg}"
    print(line)
    log_file = f"{LOGS_DIR}/{device_serial}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")

def load_devices():
    return json.load(open(DEVICES_FILE))

def save_devices(devices):
    json.dump(devices, open(DEVICES_FILE, "w"), indent=2)

def is_connected(serial):
    """Check if ADB device is connected and authorised."""
    r = subprocess.run([ADB, "-s", serial, "shell", "echo", "ok"],
                       capture_output=True, text=True, timeout=5)
    return r.stdout.strip() == "ok"

def health_check():
    """Check all registered phones. Returns dict of serial → connected."""
    devices = load_devices()
    results = {}
    print(f"\n{'─'*50}")
    print(f"  Phone Farm Health Check  [{ts()}]")
    print(f"{'─'*50}")
    for d in devices:
        serial = d["serial"]
        connected = is_connected(serial)
        results[serial] = connected
        status_icon = "✅" if connected else "❌"
        print(f"  {status_icon} {serial[:12]}  @{d['account']:<20} {d['platform']:<8} {d['status']}")
    # Check for unlisted connected devices
    r = subprocess.run([ADB, "devices"], capture_output=True, text=True)
    known = {d["serial"] for d in devices}
    for line in r.stdout.strip().split("\n")[1:]:
        if "\tdevice" in line:
            serial = line.split("\t")[0]
            if serial not in known:
                print(f"  ⚠️  {serial}  ← connected but NOT in devices.json")
    print(f"{'─'*50}\n")
    return results

def acquire_lock(serial, timeout=30):
    """Acquire a per-device lock to prevent concurrent ADB ops."""
    lock_file = f"{LOCKS_DIR}/{serial}.lock"
    f = open(lock_file, "w")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except IOError:
            time.sleep(0.5)
    f.close()
    raise TimeoutError(f"Could not acquire lock for {serial} within {timeout}s")

def release_lock(lock_f):
    fcntl.flock(lock_f, fcntl.LOCK_UN)
    lock_f.close()

def run_task_on_device(device, task, **kwargs):
    """Run a task on one device with lock protection."""
    serial  = device["serial"]
    account = device["account"]
    lock_f  = None
    try:
        log(serial, f"Starting task: {task}")
        lock_f = acquire_lock(serial)
        if not is_connected(serial):
            log(serial, f"❌ Device not connected — skipping")
            return {"serial": serial, "task": task, "ok": False, "error": "not connected"}
        result = _dispatch(task, device, **kwargs)
        log(serial, f"✅ Task {task} complete: {result}")
        return {"serial": serial, "task": task, "ok": True, "result": result}
    except Exception as e:
        log(serial, f"❌ Task {task} failed: {e}")
        traceback.print_exc()
        return {"serial": serial, "task": task, "ok": False, "error": str(e)}
    finally:
        if lock_f: release_lock(lock_f)

def _dispatch(task, device, **kwargs):
    """Route task to the right function."""
    serial = device["serial"]
    env = os.environ.copy()

    if task == "post":
        # Pull next tweet from this device's queue sheet tab
        from phone_agent.posting.twitter import post_to_twitter
        tweet_text = kwargs.get("tweet_text", "")
        if not tweet_text:
            return "no tweet text provided"
        return post_to_twitter(serial, tweet_text)

    elif task == "thread":
        from phone_agent.posting.twitter import post_thread_to_twitter
        tweets = kwargs.get("tweets", [])
        if not tweets:
            return "no tweets provided"
        return post_thread_to_twitter(serial, tweets)

    elif task == "funnel":
        # Run per-account funnel (each account has its own replied log)
        log_path = f"{CONTENTSWARM}/funnel_replied_{serial}.json"
        cmd = (
            f"source /home/aiserver/miniconda3/bin/activate wan2gp && "
            f"cd {CONTENTSWARM} && "
            f"python3 thread_dm_funnel.py 2>&1"
        )
        # Temporarily override the DEV and LOG in funnel
        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True, timeout=300,
            env={**env, "FUNNEL_DEV": serial, "FUNNEL_LOG": log_path}
        )
        return r.stdout[-500:] if r.stdout else r.stderr[-200:]

    else:
        return f"unknown task: {task}"

def run_parallel(task, devices=None, **kwargs):
    """Run task on all active phones in parallel."""
    if devices is None:
        devices = [d for d in load_devices() if d["status"] == "active"]
    if not devices:
        print("[orchestrator] No active devices found")
        return []
    print(f"[orchestrator] Running '{task}' on {len(devices)} device(s) in parallel...")
    results = [None] * len(devices)
    threads = []
    def worker(i, device):
        results[i] = run_task_on_device(device, task, **kwargs)
    for i, device in enumerate(devices):
        t = threading.Thread(target=worker, args=(i, device))
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=360)
    return results

def add_phone(serial, account, platform, persona, notes=""):
    """Add a new phone to the registry."""
    devices = load_devices()
    if any(d["serial"] == serial for d in devices):
        print(f"⚠️  {serial} already in registry")
        return
    devices.append({
        "serial": serial, "account": account, "platform": platform,
        "persona": persona, "status": "active", "notes": notes
    })
    save_devices(devices)
    print(f"✅ Added {serial} (@{account}) to phone farm")

def remove_phone(serial):
    devices = load_devices()
    devices = [d for d in devices if d["serial"] != serial]
    save_devices(devices)
    print(f"Removed {serial}")

def list_phones():
    devices = load_devices()
    health = health_check()
    return devices

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "health":
        health_check()
    elif cmd == "list":
        list_phones()
    elif cmd == "post":
        tweet = sys.argv[2] if len(sys.argv) > 2 else ""
        results = run_parallel("post", tweet_text=tweet)
        print(results)
    elif cmd == "thread":
        tweets = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
        results = run_parallel("thread", tweets=tweets)
        print(results)
    elif cmd == "funnel":
        results = run_parallel("funnel")
        print(results)
    elif cmd == "add":
        # orchestrator.py add <serial> <account> <platform> <persona>
        add_phone(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                  sys.argv[6] if len(sys.argv) > 6 else "")
    else:
        print(__doc__)
