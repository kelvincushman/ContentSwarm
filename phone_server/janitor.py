"""Background janitor: keep temp screenshots from accumulating.

The screenshot path already cleans up after itself, but this is defense in
depth — it sweeps any stale `screenshot_*.png` left in the temp dir (e.g. from
a hard crash) on startup and periodically. Zero external cron required.
"""

from __future__ import annotations

import asyncio
import glob
import os
import tempfile
import time

_PATTERN = os.path.join(tempfile.gettempdir(), "screenshot_*.png")


def sweep(max_age_sec: float = 300.0) -> int:
    """Delete temp screenshots older than max_age_sec. Returns count removed."""
    now = time.time()
    removed = 0
    for path in glob.glob(_PATTERN):
        try:
            if now - os.path.getmtime(path) > max_age_sec:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


async def run_periodic(interval_sec: float = 300.0, max_age_sec: float = 300.0) -> None:
    """Sweep now, then every interval_sec. Launched as a background task."""
    while True:
        try:
            n = sweep(max_age_sec)
            if n:
                print(f"[janitor] removed {n} stale temp screenshot(s)")
        except Exception as e:  # noqa: BLE001
            print(f"[janitor] error: {e}")
        await asyncio.sleep(interval_sec)
