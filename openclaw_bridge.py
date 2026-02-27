"""
OpenClaw ↔ ContentSwarm Bridge

Bidirectional WebSocket bridge that connects OpenClaw Gateway to the
ContentSwarm API, allowing OpenClaw to act as the strategic brain
controlling the phone fleet.

Responsibilities:
- Connect to OpenClaw Gateway via WebSocket
- Listen to ContentSwarm events via SocketIO /ws/events namespace
- Forward ContentSwarm events → OpenClaw as memory entries
- Route OpenClaw skill invocations → ContentSwarm API HTTP calls
- Auto-reconnect with exponential backoff on disconnection

Usage:
    python openclaw_bridge.py
    python openclaw_bridge.py --config openclaw_config.json
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

import requests
import websockets
import websockets.exceptions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("openclaw_bridge")


class OpenClawBridge:
    """Bidirectional bridge between OpenClaw Gateway and ContentSwarm."""

    def __init__(self, config: Dict[str, Any]):
        self.gateway_url = config.get("gateway_url", "ws://127.0.0.1:18789")
        self.contentswarm_api = config.get("contentswarm_api_url", "http://127.0.0.1:5000/api/v1")
        self.contentswarm_ws = config.get("contentswarm_ws_url", "http://127.0.0.1:5000")
        self.token = config.get("token", os.environ.get("OPENCLAW_TOKEN", ""))
        self.skills_dir = config.get("skills_dir", "openclaw_skills")

        self.reconnect_base = config.get("reconnect_base_seconds", 2)
        self.reconnect_max = config.get("reconnect_max_seconds", 60)

        self._gateway_ws = None
        self._running = False
        self._event_buffer: list = []

    async def start(self):
        """Start the bridge — connects to both OpenClaw and ContentSwarm."""
        self._running = True
        logger.info("Starting OpenClaw ↔ ContentSwarm bridge")
        logger.info(f"  Gateway:      {self.gateway_url}")
        logger.info(f"  ContentSwarm: {self.contentswarm_api}")

        # Run both connections concurrently
        await asyncio.gather(
            self._gateway_loop(),
            self._contentswarm_event_loop(),
            return_exceptions=True
        )

    async def stop(self):
        """Stop the bridge gracefully."""
        self._running = False
        if self._gateway_ws:
            await self._gateway_ws.close()
        logger.info("Bridge stopped")

    # ── OpenClaw Gateway Connection ─────────────────────────────

    async def _gateway_loop(self):
        """Connect to OpenClaw Gateway with auto-reconnect."""
        attempt = 0

        while self._running:
            try:
                logger.info(f"Connecting to OpenClaw Gateway at {self.gateway_url}...")
                async with websockets.connect(self.gateway_url) as ws:
                    self._gateway_ws = ws
                    attempt = 0
                    logger.info("Connected to OpenClaw Gateway")

                    # Send registration message
                    await ws.send(json.dumps({
                        "type": "register",
                        "source": "contentswarm_bridge",
                        "skills": [
                            "contentswarm.phones",
                            "contentswarm.pipeline",
                            "contentswarm.analytics"
                        ],
                        "skills_dir": self.skills_dir
                    }))

                    # Flush buffered events
                    if self._event_buffer:
                        logger.info(f"Flushing {len(self._event_buffer)} buffered events")
                        for event in self._event_buffer:
                            await self._send_to_gateway(event)
                        self._event_buffer.clear()

                    # Listen for messages from Gateway
                    async for message in ws:
                        await self._handle_gateway_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Gateway connection closed")
            except ConnectionRefusedError:
                logger.warning(f"Gateway not available at {self.gateway_url}")
            except Exception as e:
                logger.error(f"Gateway error: {e}")

            self._gateway_ws = None

            if not self._running:
                break

            # Exponential backoff
            delay = min(self.reconnect_base * (2 ** attempt), self.reconnect_max)
            attempt += 1
            logger.info(f"Reconnecting in {delay}s (attempt {attempt})...")
            await asyncio.sleep(delay)

    async def _handle_gateway_message(self, raw_message: str):
        """Handle incoming message from OpenClaw Gateway."""
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from Gateway: {raw_message[:100]}")
            return

        msg_type = message.get("type", "")

        if msg_type == "skill_invoke":
            await self._handle_skill_invoke(message)
        elif msg_type == "ping":
            await self._send_to_gateway({"type": "pong", "timestamp": time.time()})
        else:
            logger.debug(f"Unhandled gateway message type: {msg_type}")

    async def _handle_skill_invoke(self, message: Dict[str, Any]):
        """Route an OpenClaw skill invocation to the ContentSwarm API."""
        skill = message.get("skill", "")
        action = message.get("action", "")
        params = message.get("params", {})
        invoke_id = message.get("id", "")

        logger.info(f"Skill invocation: {skill}.{action} (id={invoke_id})")

        try:
            result = self._call_contentswarm_api(skill, action, params)
            await self._send_to_gateway({
                "type": "skill_result",
                "id": invoke_id,
                "success": True,
                "result": result
            })
        except Exception as e:
            logger.error(f"Skill invocation failed: {e}")
            await self._send_to_gateway({
                "type": "skill_result",
                "id": invoke_id,
                "success": False,
                "error": str(e)
            })

    def _call_contentswarm_api(self, skill: str, action: str, params: Dict) -> Any:
        """Translate skill+action into ContentSwarm API calls."""
        base = self.contentswarm_api

        routes = {
            # contentswarm.phones
            ("contentswarm.phones", "list"): ("GET", f"{base}/phones", None),
            ("contentswarm.phones", "get"): ("GET", f"{base}/phones/{params.get('phone', '')}", None),
            ("contentswarm.phones", "run_task"): ("POST", f"{base}/phones/{params.get('phone', '')}/task", {"task": params.get("task", "")}),
            ("contentswarm.phones", "batch"): ("POST", f"{base}/phones/batch", {"tasks": params.get("tasks", {})}),
            ("contentswarm.phones", "task_status"): ("GET", f"{base}/tasks/{params.get('task_id', '')}", None),
            ("contentswarm.phones", "list_tasks"): ("GET", f"{base}/tasks", None),

            # contentswarm.pipeline
            ("contentswarm.pipeline", "run"): ("POST", f"{base}/pipeline/run", params),
            ("contentswarm.pipeline", "discover"): ("POST", f"{base}/pipeline/discover", params),
            ("contentswarm.pipeline", "status"): ("GET", f"{base}/pipeline/status", None),
            ("contentswarm.pipeline", "trending"): ("GET", f"{base}/pipeline/trending", None),
            ("contentswarm.pipeline", "content"): ("GET", f"{base}/pipeline/content", None),
            ("contentswarm.pipeline", "set_assignments"): ("POST", f"{base}/assignments", params),
            ("contentswarm.pipeline", "get_assignments"): ("GET", f"{base}/assignments", None),

            # contentswarm.analytics
            ("contentswarm.analytics", "status"): ("GET", f"{base}/status", None),
            ("contentswarm.analytics", "analytics"): ("GET", f"{base}/analytics", None),
        }

        key = (skill, action)
        if key not in routes:
            raise ValueError(f"Unknown skill action: {skill}.{action}")

        method, url, body = routes[key]

        if method == "GET":
            resp = requests.get(url, timeout=30)
        else:
            resp = requests.post(url, json=body, timeout=30)

        resp.raise_for_status()
        return resp.json()

    async def _send_to_gateway(self, message: Dict[str, Any]):
        """Send a message to OpenClaw Gateway, buffering if disconnected."""
        if self._gateway_ws:
            try:
                await self._gateway_ws.send(json.dumps(message))
                return
            except Exception:
                pass

        # Buffer if not connected
        self._event_buffer.append(message)
        if len(self._event_buffer) > 1000:
            self._event_buffer = self._event_buffer[-500:]

    # ── ContentSwarm Event Listener ─────────────────────────────

    async def _contentswarm_event_loop(self):
        """Listen to ContentSwarm events via SocketIO polling fallback."""
        attempt = 0

        while self._running:
            try:
                # Use polling to check for events since we can't easily
                # do SocketIO from asyncio. Poll the status endpoint.
                await asyncio.sleep(5)

                resp = requests.get(f"{self.contentswarm_api}/status", timeout=10)
                if resp.ok:
                    status = resp.json()
                    attempt = 0

                    # Forward status as a heartbeat to OpenClaw memory
                    await self._send_to_gateway({
                        "type": "memory_entry",
                        "memory_type": "declarative",
                        "source": "contentswarm",
                        "content": {
                            "kind": "system_status",
                            "phones_connected": status.get("phones", {}).get("connected", 0),
                            "phones_total": status.get("phones", {}).get("total", 0),
                            "pipeline_stage": status.get("pipeline", {}).get("stage", "unknown") if status.get("pipeline") else "not_initialized",
                        },
                        "timestamp": time.time()
                    })

            except requests.ConnectionError:
                delay = min(self.reconnect_base * (2 ** attempt), self.reconnect_max)
                attempt += 1
                logger.warning(f"ContentSwarm API not available, retrying in {delay}s")
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"ContentSwarm event loop error: {e}")
                await asyncio.sleep(5)


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load bridge configuration from file or environment."""
    config = {
        "gateway_url": os.environ.get("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789"),
        "contentswarm_api_url": os.environ.get("CONTENTSWARM_API_URL", "http://127.0.0.1:5000/api/v1"),
        "contentswarm_ws_url": os.environ.get("CONTENTSWARM_WS_URL", "http://127.0.0.1:5000"),
        "token": os.environ.get("OPENCLAW_TOKEN", ""),
        "skills_dir": "openclaw_skills",
        "reconnect_base_seconds": 2,
        "reconnect_max_seconds": 60
    }

    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            file_config = json.load(f)
        config.update(file_config)

    return config


def main():
    parser = argparse.ArgumentParser(description="OpenClaw ↔ ContentSwarm Bridge")
    parser.add_argument("--config", default="openclaw_config.json", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    bridge = OpenClawBridge(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        loop.create_task(bridge.stop())

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(bridge.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bridge.stop())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
