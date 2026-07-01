"""Standalone LAN Phone Control Server.

A thin FastAPI service that wraps the `phone_agent` package and exposes the full
phone-control surface over the network so an external agent harness can drive one
or many connected Android phones.

Two layers are exposed:
  * Raw primitives  — screenshot, tap, swipe, type, launch, keys, device mgmt.
  * High-level agent — run a natural-language task via the vision-language model.

See PHONE_SERVER.md for the full API reference and harness integration guide.
"""

from phone_server.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
__version__ = "0.1.0"
