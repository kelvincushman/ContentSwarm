#!/usr/bin/env python3
"""
Thread DM Funnel — device-agnostic via device_nav.py.
No hardcoded coordinates. Works on any Android + X app.
"""
import re, time, json, sys, os
sys.path.insert(0, "/home/aiserver/contentswarm")
from phone_agent.posting.device_nav import (
    dump_layout, tap_nav, tap_mentions_tab, check_follows_you,
    check_retweeted_profile, tap_profile_dm_button, get_dm_input_field,
    tap_dm_send_button, type_text, launch_x, open_profile_url, back, tap_bounds
)

DEV     = "RF8M90JL60K"
LOG     = "/home/aiserver/contentswarm/funnel_replied.json"
KEYWORD = "FREE"
THREAD_KEYWORDS = ["aigentis", "comment free", "follow + repost",
                   "books appointments", "7 ai agents", "automated rev"]
OFFER = (sys.argv[1] if len(sys.argv) > 1 else
    "Hey! 👋 Thanks for commenting FREE 🙏\n\n"
    "Tell me your business name + what you do and I will put together "
    "a personalised AiGENTIS breakdown — exactly what the 7 AI agents "
    "could do for your business.\n\nReply here and lets chat 🤙🏻")

def load_log():
    try:    return json.load(open(LOG))
    except: return {}

def save_log(d):
    json.dump(d, open(LOG, "w"), indent=2)

def go_to_mentions():
    launch_x(DEV, wait=5)
    tap_nav(DEV, "Notifications")
    tap_mentions_tab(DEV)

def find_free_replies():
    layout = dump_layout(DEV, "/tmp/mentions_scan.xml")
    found, seen = [], set()
    for m in re.finditer(r'content-desc="([^"]{15,400})"[^>]*bounds="([^"]+)"', layout):
        desc, bounds = m.group(1), m.group(2)
        if KEYWORD.upper() not in desc.upper(): continue
        h = re.search(r'@(\w+)', desc)
        if not h or h.group(1).lower() == "ukkelvinlee": continue
        handle = h.group(1)
        if handle not in seen:
            seen.add(handle)
            found.append((handle, bounds))
            print(f"[funnel] FREE reply: @{handle}")
    return found

def send_dm_via_profile(handle, offer_text):
    open_profile_url(DEV, handle, wait=4)
    if not tap_profile_dm_button(DEV):
        return False
    # Type in message field
    dm_field = get_dm_input_field(DEV)
    if dm_field:
        tap_bounds(DEV, dm_field, delay=0.5)
    type_text(DEV, offer_text, delay=1)
    # Send
    if not tap_dm_send_button(DEV):
        print(f"[funnel] ⚠️ Send button not found — trying last resort")
        from phone_agent.posting.device_nav import adb
        adb(DEV, "shell", "input", "keyevent", "66")  # ENTER as last resort
    time.sleep(2)
    # Verify
    layout = dump_layout(DEV, "/tmp/dm_verify.xml")
    sent = offer_text[:20].lower() not in layout.lower() or "Sent" in layout
    print(f"[funnel] {'✅ DM sent' if sent else '⚠️ DM may have sent'} to @{handle}")
    return True

def run():
    log = load_log()
    replied = []
    print(f"[funnel] ── Starting funnel check (device: {DEV}) ──")
    go_to_mentions()
    replies = find_free_replies()
    if not replies:
        print("[funnel] No FREE replies found"); return []
    for handle, bounds in replies:
        if handle in log:
            print(f"[funnel] @{handle} already DM'd — skip"); continue
        follows = check_follows_you(DEV, handle)
        print(f"[funnel] @{handle} follows @UKKelvinLee: {follows}")
        if not follows:
            print(f"[funnel] @{handle} doesn't follow — skip"); continue
        retweeted = check_retweeted_profile(DEV, handle, THREAD_KEYWORDS)
        print(f"[funnel] @{handle} retweeted: {retweeted}")
        if not retweeted:
            print(f"[funnel] @{handle} hasn't retweeted — skip"); continue
        go_to_mentions()  # re-navigate so next iteration works cleanly
        send_dm_via_profile(handle, OFFER)
        log[handle] = {"ts": time.time(), "ok": True}
        save_log(log)
        replied.append(handle)
        time.sleep(3)
    print(f"[funnel] Done. DM'd: {replied}")
    return replied

if __name__ == "__main__":
    run()
