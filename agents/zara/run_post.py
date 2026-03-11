"""
run_post.py — runs ON the Lenovo server (192.168.55.124).

Usage:
    python3 run_post.py --platform twitter --text "Hello world!"
    python3 run_post.py --platform tiktok  --text "Check this out #AI"
    python3 run_post.py --platform instagram --text "Good morning ✨"
    python3 run_post.py --platform instagram --text "Story text" --media /path/to/image.jpg

This script instantiates a ZaraAgent/PhoneAgent on the Lenovo machine (which has
the Note 10 attached via ADB) and executes the task.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ContentSwarm root on Lenovo
_repo_root = Path(__file__).parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.model.client import ModelConfig

DEVICE_ID = "RF8M90JL60K"


def _get_openai_key() -> str:
    """Resolve OpenAI API key from env or secrets file."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    for path in [
        Path.home() / ".secrets" / "openai-api",
        Path("/home/pai-server/.secrets/openai-api"),
        Path("/root/.secrets/openai-api"),
    ]:
        if path.exists():
            return path.read_text().strip()
    raise RuntimeError("No OpenAI API key found. Set OPENAI_API_KEY env var.")


def build_agent(max_steps: int = 20) -> PhoneAgent:
    """Instantiate a PhoneAgent with Zara's config."""
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
        max_steps=max_steps,
        verbose=True,
    )
    return PhoneAgent(model_config=model_config, agent_config=agent_config)


def run_twitter(text: str, media: str = "") -> str:
    """Post a tweet."""
    agent = build_agent()
    task = (
        f"Open the Twitter (X) app on this Android phone. "
        f"Tap the compose button (+ or pencil icon). "
        f"When the tweet compose screen appears, clear any existing text. "
        f"Type this tweet text exactly: {text!r}. "
        f"Tap the 'Post' or 'Tweet' button to publish. "
        f"Wait for confirmation that the tweet was posted. "
        f"Report success when the tweet is live."
    )
    return agent.run(task)


def run_tiktok(text: str, media: str = "") -> str:
    """Add caption to TikTok upload."""
    agent = build_agent()
    task = (
        f"Open TikTok on this Android phone. "
        f"Find the caption or description field for a new post. "
        f"Clear existing text and type this caption: {text!r}. "
        f"Confirm the caption is entered. "
        f"If on an upload screen, tap Next or Post to proceed. "
        f"Report the result."
    )
    return agent.run(task)


def run_instagram(text: str, media: str = "") -> str:
    """Post an Instagram story with text."""
    agent = build_agent()
    task = (
        f"Open Instagram on this Android phone. "
        f"Tap the + or camera icon to create a new story. "
        f"Select text/Aa option. "
        f"Type this text exactly: {text!r}. "
        f"Choose a nice background. "
        f"Tap 'Your Story' to share. "
        f"Confirm the story was shared successfully."
    )
    return agent.run(task)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zara run_post — executes phone posts")
    parser.add_argument("--platform", required=True,
                        choices=["twitter", "tiktok", "instagram", "x"],
                        help="Social platform to post to")
    parser.add_argument("--text", required=True, help="Post text content")
    parser.add_argument("--media", default="", help="Optional media file path")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print task without executing")
    args = parser.parse_args()

    platform = args.platform.lower()
    text = args.text
    media = args.media

    if args.dry_run:
        print(f"[DRY RUN] Would post to {platform}: {text[:80]}...")
        sys.exit(0)

    print(f"\n🚀 Zara run_post: {platform} | {text[:60]}...")

    try:
        if platform in ("twitter", "x"):
            result = run_twitter(text, media)
        elif platform == "tiktok":
            result = run_tiktok(text, media)
        elif platform == "instagram":
            result = run_instagram(text, media)
        else:
            print(f"❌ Unknown platform: {platform}")
            sys.exit(1)

        print(f"\n✅ Done: {result}")
        # Output JSON result for easy parsing by caller
        print(json.dumps({"success": True, "platform": platform, "result": result}))

    except Exception as e:
        print(f"\n❌ Post failed: {e}")
        print(json.dumps({"success": False, "platform": platform, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
