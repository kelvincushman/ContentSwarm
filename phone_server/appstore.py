"""Persistence for onboarded app profiles.

Each app is one JSON file under `profiles_dir/<app>.json`, with reference
screenshots under `profiles_dir/<app>/screens/`. The store is intentionally
simple (files on disk) so profiles are easy to inspect, diff, and commit.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from phone_server.config import get_settings
from phone_server.models import AppProfile

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-") or "app"


class AppStore:
    """Load / save / list :class:`AppProfile` objects on disk."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or get_settings().profiles_dir
        os.makedirs(self.root, exist_ok=True)

    # --- paths ---
    def _path(self, app: str) -> str:
        return os.path.join(self.root, f"{slugify(app)}.json")

    def screens_dir(self, app: str) -> str:
        d = os.path.join(self.root, slugify(app), "screens")
        os.makedirs(d, exist_ok=True)
        return d

    # --- crud ---
    def exists(self, app: str) -> bool:
        return os.path.exists(self._path(slugify(app)))

    def list_apps(self) -> list[str]:
        return sorted(
            f[:-5] for f in os.listdir(self.root) if f.endswith(".json")
        )

    def load(self, app: str) -> Optional[AppProfile]:
        path = self._path(app)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return AppProfile.model_validate(json.load(f))

    def save(self, profile: AppProfile) -> str:
        profile.app = slugify(profile.app)
        path = self._path(profile.app)
        with open(path, "w") as f:
            json.dump(profile.model_dump(), f, indent=2, ensure_ascii=False)
        return path

    def delete(self, app: str) -> bool:
        path = self._path(app)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def save_screenshot(self, app: str, name: str, png_bytes: bytes) -> str:
        """Persist a reference screenshot; returns the stored filename."""
        fname = f"{slugify(name)}.png"
        with open(os.path.join(self.screens_dir(app), fname), "wb") as f:
            f.write(png_bytes)
        return fname


# Module-level singleton shared by routers.
STORE = AppStore()
