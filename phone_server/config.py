"""Server configuration, loaded from environment variables."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the phone control server.

    All values come from environment variables so the service can be dropped
    into systemd / docker without code changes.
    """

    # --- Network ---
    host: str = os.environ.get("PHONE_SERVER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("PHONE_SERVER_PORT", "8770"))

    # --- Auth --- (if unset, the server runs OPEN — only do this on a trusted LAN)
    api_key: str | None = os.environ.get("PHONE_API_KEY") or None

    # --- Vision-language model used by the high-level /run endpoints ---
    vlm_base_url: str = os.environ.get("VLM_BASE_URL", "http://localhost:8000/v1")
    vlm_model: str = os.environ.get("VLM_MODEL", "autoglm-phone-9b")
    vlm_api_key: str = os.environ.get("VLM_API_KEY", "EMPTY")

    # --- Agent defaults ---
    default_lang: str = os.environ.get("PHONE_AGENT_LANG", "en")
    default_max_steps: int = int(os.environ.get("PHONE_AGENT_MAX_STEPS", "50"))

    # --- Live stream defaults ---
    default_stream_fps: float = float(os.environ.get("PHONE_STREAM_FPS", "2"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
