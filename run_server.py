#!/usr/bin/env python3
"""
ContentSwarm server entry point.

Wires up the phone pool and automation, then starts the
dashboard (web UI + /api/v1 REST API) so an external agent harness such as
Orphus can drive the phone fleet.

Environment variables:
    CONTENTSWARM_HOST          Bind address (default: 0.0.0.0)
    CONTENTSWARM_PORT          Port (default: 5000)
    CONTENTSWARM_PHONES_CONFIG Path to phones config JSON (default: phones_config.json)
    CONTENTSWARM_API_TOKEN     If set, /api/v1 requires this bearer token
    PHONE_AGENT_BASE_URL       Vision model API URL (default: http://localhost:8000/v1)
    PHONE_AGENT_MODEL          Vision model name (default: autoglm-phone-9b)
    PHONE_AGENT_API_KEY        Vision model API key (default: EMPTY)
    PHONE_AGENT_MAX_STEPS      Max steps per phone task (default: 100)
    PHONE_AGENT_LANG           Prompt language, cn or en (default: en)

Usage:
    python run_server.py
"""

import os
import sys
from pathlib import Path

from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig
from phone_agent.phone_pool import PhonePoolManager
from phone_agent.social_automation import SocialMediaAutomation

sys.path.insert(0, str(Path(__file__).parent / "dashboard"))
from app import init_dashboard  # noqa: E402


def main() -> None:
    host = os.environ.get("CONTENTSWARM_HOST", "0.0.0.0")
    port = int(os.environ.get("CONTENTSWARM_PORT", "5000"))
    phones_config = os.environ.get("CONTENTSWARM_PHONES_CONFIG", "phones_config.json")

    model_config = ModelConfig(
        base_url=os.environ.get("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        model_name=os.environ.get("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
        api_key=os.environ.get("PHONE_AGENT_API_KEY", "EMPTY"),
    )
    agent_config = AgentConfig(
        max_steps=int(os.environ.get("PHONE_AGENT_MAX_STEPS", "100")),
        lang=os.environ.get("PHONE_AGENT_LANG", "en"),
        verbose=False,
    )

    phone_manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config=phones_config if Path(phones_config).exists() else None,
    )
    if not phone_manager.phones:
        print(f"⚠️  No phones loaded ({phones_config} missing or empty) - "
              "API starts anyway; add phones and restart, or use auto-discovery.")

    automation = SocialMediaAutomation(phone_manager)

    if os.environ.get("CONTENTSWARM_API_TOKEN"):
        print("🔒 API token auth enabled for /api/v1")
    else:
        print("⚠️  CONTENTSWARM_API_TOKEN not set - /api/v1 is unauthenticated")

    init_dashboard(
        phone_manager=phone_manager,
        automation=automation,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
