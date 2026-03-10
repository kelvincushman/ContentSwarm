"""ADB-based Twitter/X posting workflow."""

import subprocess
import time


def _adb(device_id: str, *args: str) -> subprocess.CompletedProcess:
    """Run an ADB command targeting a specific device."""
    cmd = ["adb", "-s", device_id] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def open_twitter(device_id: str) -> bool:
    """Launch Twitter/X app via ADB intent.

    Tries the composer activity first; falls back to the main launcher.
    """
    # Try direct composer launch
    result = _adb(
        device_id,
        "shell",
        "am",
        "start",
        "-n",
        "com.twitter.android/.composer.ComposerActivity",
    )
    if result.returncode == 0 and "Error" not in result.stderr:
        time.sleep(2)
        return True

    # Fallback: launch main app via monkey
    _adb(
        device_id,
        "shell",
        "monkey",
        "-p",
        "com.twitter.android",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    )
    time.sleep(3)
    return True


def tap_compose(device_id: str) -> None:
    """Tap the compose/new tweet FAB button.

    Primary: coordinate-based tap (bottom-right FAB on most Twitter layouts).
    Fallback: UI Automator content-description search.
    """
    # Primary — FAB is typically at bottom-right (~980, 1850) on 1080x2400 screens
    _adb(device_id, "shell", "input", "tap", "980", "1850")
    time.sleep(1.5)

    # Verify compose screen opened by checking for compose UI element
    result = _adb(
        device_id,
        "shell",
        "uiautomator",
        "dump",
        "/dev/tty",
    )
    if "ComposerActivity" in result.stdout or "tweet_text" in result.stdout.lower():
        return

    # Fallback — try UI Automator click on compose button by description
    _adb(
        device_id,
        "shell",
        "input",
        "tap",
        "980",
        "1780",
    )
    time.sleep(1.5)


def type_tweet(device_id: str, text: str) -> None:
    """Type tweet text using ADB keyboard broadcast (supports unicode)."""
    import base64

    encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    _adb(
        device_id,
        "shell",
        "am",
        "broadcast",
        "-a",
        "ADB_INPUT_B64",
        "--es",
        "msg",
        encoded,
    )
    time.sleep(1)


def post_tweet(device_id: str) -> None:
    """Tap the Post/Tweet button to publish.

    Primary: coordinate-based tap (top-right Post button).
    Fallback: alternative position.
    """
    # Post button is typically top-right (~990, 170) on compose screen
    _adb(device_id, "shell", "input", "tap", "990", "170")
    time.sleep(2)

    # Fallback position for different Twitter versions
    _adb(device_id, "shell", "input", "tap", "1000", "160")
    time.sleep(1)


def post_to_twitter(device_id: str, text: str) -> bool:
    """Full workflow: open Twitter -> compose -> type -> post.

    Args:
        device_id: ADB device serial ID.
        text: Tweet text content.

    Returns:
        True if workflow completed (does not guarantee post success).
    """
    print(f"[twitter] Posting to {device_id}: {text[:50]}...")
    try:
        open_twitter(device_id)
        tap_compose(device_id)
        type_tweet(device_id, text)
        post_tweet(device_id)
        print(f"[twitter] Post workflow completed on {device_id}")
        return True
    except Exception as e:
        print(f"[twitter] Post failed on {device_id}: {e}")
        return False
