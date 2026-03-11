"""
Zara Agent — Phone 1 social media automation.
Persona: @ZaraMitchellAI — AI/tech content, London-based young woman.
Platforms: Twitter/X, TikTok, Instagram
Device: Samsung Note 10, ADB ID RF8M90JL60K (connected to Lenovo 192.168.55.124)
"""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add ContentSwarm root to path when running standalone
_repo_root = Path(__file__).parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.model.client import ModelConfig

# ── Config ──────────────────────────────────────────────────────────────────

DEVICE_ID = "RF8M90JL60K"
SCREENSHOT_DIR = "/tmp"

# OpenAI key: env var takes priority, then secrets file
def _get_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    secrets_path = Path.home() / ".secrets" / "openai-api"
    if secrets_path.exists():
        return secrets_path.read_text().strip()
    raise RuntimeError(
        "No OpenAI API key found. Set OPENAI_API_KEY env var or create ~/.secrets/openai-api"
    )


def _build_agent() -> PhoneAgent:
    """Create a PhoneAgent configured for Zara."""
    model_config = ModelConfig(
        base_url="https://api.openai.com/v1",
        api_key=_get_openai_key(),
        model_name="gpt-4o-mini",
        max_tokens=1000,
        temperature=0.1,
        top_p=0.9,
        frequency_penalty=0.0,
    )
    agent_config = AgentConfig(
        device_id=DEVICE_ID,
        lang="en",
        max_steps=20,
        verbose=True,
    )
    return PhoneAgent(model_config=model_config, agent_config=agent_config)


# ── ADB helpers (clipboard + input fallbacks) ────────────────────────────────

def _adb(*args) -> str:
    """Run adb command, return stdout."""
    cmd = ["adb", "-s", DEVICE_ID] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def _clipboard_paste(text: str) -> None:
    """Set clipboard via Android clipper broadcast, then paste."""
    # Escape single quotes for shell
    safe = text.replace("'", "\\'").replace('"', '\\"')
    _adb("shell", "am", "broadcast", "-a", "clipper.set", "-e", "text", safe)
    time.sleep(0.5)
    # Paste: Ctrl+V keyevent
    _adb("shell", "input", "keyevent", "KEYCODE_PASTE")
    time.sleep(0.3)


def _type_text_safe(text: str) -> None:
    """
    Type text onto device. Uses clipboard for multi-word text to avoid
    special char issues with 'adb shell input text'.
    """
    # Try clipper broadcast method first (handles spaces, emojis)
    _clipboard_paste(text)


# ── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot(filename: str | None = None) -> str:
    """
    Capture the current Note 10 screen.

    Args:
        filename: Optional filename (default: zara_screen_<timestamp>.png)

    Returns:
        Local path to the saved PNG.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = filename or f"zara_screen_{ts}.png"
    local_path = os.path.join(SCREENSHOT_DIR, fname)

    remote_path = f"/sdcard/{fname}"
    _adb("shell", "screencap", "-p", remote_path)
    time.sleep(0.5)
    _adb("pull", remote_path, local_path)
    _adb("shell", "rm", remote_path)

    print(f"📸 Screenshot saved: {local_path}")
    return local_path


# ── Platform tasks ────────────────────────────────────────────────────────────

def post_tweet(text: str) -> str:
    """
    Open Twitter/X, compose a tweet with the given text, and post it.

    Args:
        text: Tweet content (max 280 chars recommended).

    Returns:
        Result message from the agent.
    """
    print(f"\n🐦 Zara posting to Twitter: {text[:60]}...")
    agent = _build_agent()
    task = (
        f"Open the Twitter (X) app. Tap the compose/new tweet button (the + or pencil icon). "
        f"Wait for the tweet compose screen. Clear any existing text in the input field. "
        f"Type the following tweet text exactly: {text!r}. "
        f"Then tap the Post or Tweet button to publish. "
        f"Confirm the tweet was posted successfully."
    )
    return agent.run(task)


def post_tiktok_caption(text: str) -> str:
    """
    Open TikTok and add a caption to the most recent draft/upload in progress.
    If TikTok is already on an upload/caption screen, fills in the caption.

    Args:
        text: Caption text.

    Returns:
        Result message from the agent.
    """
    print(f"\n🎵 Zara updating TikTok caption: {text[:60]}...")
    agent = _build_agent()
    task = (
        f"Open TikTok. Navigate to the upload or caption screen for a new post. "
        f"Find the caption/description input field. "
        f"Clear any placeholder text and type this caption exactly: {text!r}. "
        f"Add relevant hashtags if possible. "
        f"Do NOT post — just fill in the caption and confirm it is typed correctly."
    )
    return agent.run(task)


def post_instagram_story(text: str) -> str:
    """
    Open Instagram and create a text story with the given content.

    Args:
        text: Story text content.

    Returns:
        Result message from the agent.
    """
    print(f"\n📸 Zara posting Instagram story: {text[:60]}...")
    agent = _build_agent()
    task = (
        f"Open Instagram. Tap the + or camera icon to create a new story. "
        f"Select the text story option (Aa or text tool). "
        f"Type the following text exactly: {text!r}. "
        f"Choose a nice background colour. "
        f"Then tap 'Your Story' to share it to Zara's story. "
        f"Confirm the story was shared successfully."
    )
    return agent.run(task)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Zara Agent — direct task runner")
    parser.add_argument("--task", choices=["tweet", "tiktok", "instagram", "screenshot"])
    parser.add_argument("--text", default="")
    args = parser.parse_args()

    if args.task == "screenshot":
        path = take_screenshot()
        print(f"Screenshot: {path}")
    elif args.task == "tweet":
        result = post_tweet(args.text)
        print(f"Result: {result}")
    elif args.task == "tiktok":
        result = post_tiktok_caption(args.text)
        print(f"Result: {result}")
    elif args.task == "instagram":
        result = post_instagram_story(args.text)
        print(f"Result: {result}")
    else:
        parser.print_help()
