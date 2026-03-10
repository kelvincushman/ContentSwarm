"""ADB-based TikTok posting workflow."""

import subprocess
import time


def _adb(device_id: str, *args: str) -> subprocess.CompletedProcess:
    """Run an ADB command targeting a specific device."""
    cmd = ["adb", "-s", device_id] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def open_tiktok(device_id: str) -> bool:
    """Launch TikTok app."""
    _adb(
        device_id,
        "shell",
        "monkey",
        "-p",
        "com.zhiliaoapp.musically",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    )
    time.sleep(3)
    return True


def tap_upload(device_id: str) -> None:
    """Tap the center '+' create/upload button.

    On most TikTok layouts, the create button is bottom-center (~540, 2280)
    on a 1080x2400 screen.
    """
    # Primary — center bottom '+' button
    _adb(device_id, "shell", "input", "tap", "540", "2280")
    time.sleep(2)

    # Fallback position (slightly higher for different screen ratios)
    result = _adb(device_id, "shell", "dumpsys", "window")
    if "com.zhiliaoapp.musically" in result.stdout:
        _adb(device_id, "shell", "input", "tap", "540", "2200")
        time.sleep(2)


def tap_upload_video(device_id: str) -> None:
    """From the create screen, tap 'Upload' to pick a video from gallery."""
    # Upload button is typically bottom-right on the camera/create screen
    _adb(device_id, "shell", "input", "tap", "980", "2280")
    time.sleep(2)


def select_first_video(device_id: str) -> None:
    """Select the first video in the gallery grid."""
    # First thumbnail in gallery is typically around (200, 600)
    _adb(device_id, "shell", "input", "tap", "200", "600")
    time.sleep(1)

    # Tap Next/Confirm button (bottom-right)
    _adb(device_id, "shell", "input", "tap", "980", "2280")
    time.sleep(2)


def tap_next(device_id: str) -> None:
    """Tap Next on the editing screen to get to the caption screen."""
    # Next button is typically top-right or bottom-right
    _adb(device_id, "shell", "input", "tap", "980", "2280")
    time.sleep(2)


def type_caption(device_id: str, text: str) -> None:
    """Type caption text. Taps the caption field first, then types."""
    import base64

    # Tap caption/description field (usually near top of post screen)
    _adb(device_id, "shell", "input", "tap", "540", "400")
    time.sleep(1)

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


def tap_post(device_id: str) -> None:
    """Tap the Post button to publish the TikTok."""
    # Post button is typically bottom-center on the final screen
    _adb(device_id, "shell", "input", "tap", "540", "2280")
    time.sleep(3)


def push_video_to_device(device_id: str, local_path: str) -> str:
    """Push a local video file to the device's DCIM folder.

    Returns:
        Remote path on the device.
    """
    remote_path = f"/sdcard/DCIM/{local_path.split('/')[-1]}"
    _adb(device_id, "push", local_path, remote_path)
    time.sleep(1)

    # Trigger media scanner so TikTok can see the file
    _adb(
        device_id,
        "shell",
        "am",
        "broadcast",
        "-a",
        "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
        "-d",
        f"file://{remote_path}",
    )
    time.sleep(2)
    return remote_path


def post_to_tiktok(
    device_id: str,
    caption: str,
    video_path: str | None = None,
) -> bool:
    """Full workflow: open TikTok -> upload video -> add caption -> post.

    Args:
        device_id: ADB device serial ID.
        caption: Post caption/description text.
        video_path: Optional local path to video file. If provided, pushes to
            device first. If None, selects the first video from gallery.

    Returns:
        True if workflow completed.
    """
    print(f"[tiktok] Posting to {device_id}: {caption[:50]}...")
    try:
        if video_path:
            push_video_to_device(device_id, video_path)

        open_tiktok(device_id)
        tap_upload(device_id)
        tap_upload_video(device_id)
        select_first_video(device_id)
        tap_next(device_id)
        type_caption(device_id, caption)
        tap_post(device_id)
        print(f"[tiktok] Post workflow completed on {device_id}")
        return True
    except Exception as e:
        print(f"[tiktok] Post failed on {device_id}: {e}")
        return False
