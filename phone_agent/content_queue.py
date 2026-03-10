"""File-based content queue for routing posts to persona phones."""

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Default directory for x-posts JSON files
X_POSTS_DIR = Path("/home/pai-server/.openclaw/workspace/marketing/x-posts")

# Queue state file — lives next to phones_config.json
QUEUE_STATE_PATH = Path(__file__).parent.parent / "content_queue_state.json"


@dataclass
class QueuedPost:
    post_id: str
    persona: str
    platform: str
    text: str
    media_path: str | None = None
    status: str = "pending"  # pending | sent | failed
    created_at: float = field(default_factory=time.time)
    sent_at: float | None = None


def _load_state() -> list[dict]:
    if QUEUE_STATE_PATH.exists():
        with open(QUEUE_STATE_PATH) as f:
            return json.load(f)
    return []


def _save_state(posts: list[dict]) -> None:
    QUEUE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_STATE_PATH, "w") as f:
        json.dump(posts, f, indent=2)


def queue_post(
    persona: str,
    platform: str,
    text: str,
    media_path: str | None = None,
) -> str:
    """Add a post to the queue.

    Args:
        persona: Target persona name (zara, marcus, jay).
        platform: Target platform (twitter, tiktok, instagram, etc.).
        text: Post text content.
        media_path: Optional path to media file.

    Returns:
        The generated post_id.
    """
    post = QueuedPost(
        post_id=str(uuid.uuid4())[:8],
        persona=persona.lower(),
        platform=platform.lower(),
        text=text,
        media_path=media_path,
    )
    posts = _load_state()
    posts.append(asdict(post))
    _save_state(posts)
    print(f"[queue] Queued post {post.post_id} for {persona}/{platform}")
    return post.post_id


def get_next(persona: str, platform: str) -> dict | None:
    """Get the next pending post for a persona+platform combo.

    Returns:
        Post dict or None if queue is empty for that combo.
    """
    posts = _load_state()
    for post in posts:
        if (
            post["persona"] == persona.lower()
            and post["platform"] == platform.lower()
            and post["status"] == "pending"
        ):
            return post
    return None


def mark_sent(post_id: str) -> bool:
    """Mark a post as sent with timestamp.

    Returns:
        True if post was found and updated.
    """
    posts = _load_state()
    for post in posts:
        if post["post_id"] == post_id:
            post["status"] = "sent"
            post["sent_at"] = time.time()
            _save_state(posts)
            print(f"[queue] Marked {post_id} as sent")
            return True
    return False


def mark_failed(post_id: str) -> bool:
    """Mark a post as failed."""
    posts = _load_state()
    for post in posts:
        if post["post_id"] == post_id:
            post["status"] = "failed"
            _save_state(posts)
            print(f"[queue] Marked {post_id} as failed")
            return True
    return False


def get_pending(persona: str | None = None) -> list[dict]:
    """Get all pending posts, optionally filtered by persona."""
    posts = _load_state()
    pending = [p for p in posts if p["status"] == "pending"]
    if persona:
        pending = [p for p in pending if p["persona"] == persona.lower()]
    return pending


def get_all() -> list[dict]:
    """Get the full queue state."""
    return _load_state()


def ingest_x_posts(directory: Path | None = None) -> int:
    """Read JSON files from x-posts directory and queue them.

    Expected JSON format per file:
        {"persona": "...", "platform": "...", "text": "...", "media_path": "..."}
    or a list of such objects.

    Files are renamed to .ingested after processing.

    Returns:
        Number of posts ingested.
    """
    src = directory or X_POSTS_DIR
    if not src.exists():
        print(f"[queue] x-posts directory not found: {src}")
        return 0

    count = 0
    for fpath in sorted(src.glob("*.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[queue] Skipping {fpath.name}: {e}")
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            persona = item.get("persona", "").lower()
            platform = item.get("platform", "").lower()
            text = item.get("text", "")
            media = item.get("media_path")
            if persona and platform and text:
                queue_post(persona, platform, text, media)
                count += 1

        # Rename to avoid re-ingestion
        ingested_path = fpath.with_suffix(".ingested")
        os.rename(fpath, ingested_path)
        print(f"[queue] Ingested {fpath.name} -> {ingested_path.name}")

    return count
