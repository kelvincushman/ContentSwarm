#!/usr/bin/env python3
"""Entry point for the standalone Phone Control Server.

Usage:
    python run_phone_server.py

Environment (all optional):
    PHONE_SERVER_HOST   bind host                 (default 0.0.0.0 — all LAN interfaces)
    PHONE_SERVER_PORT   bind port                 (default 8770)
    PHONE_API_KEY       shared secret for auth    (default: unset = OPEN, LAN only!)
    VLM_BASE_URL        vision model endpoint      (default http://localhost:8000/v1)
    VLM_MODEL           vision model name          (default autoglm-phone-9b)
    PHONE_AGENT_LANG    agent prompt language      (default en)
"""

import uvicorn

from phone_server.config import get_settings


def main() -> None:
    s = get_settings()
    if not s.api_key:
        print("[phone-server] WARNING: PHONE_API_KEY is not set — server is OPEN. Use only on a trusted LAN.")
    print(f"[phone-server] Listening on http://{s.host}:{s.port}  (VLM: {s.vlm_base_url}, model: {s.vlm_model})")
    uvicorn.run("phone_server.server:app", host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    main()
