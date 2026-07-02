"""Persistent registry: per-phone config, accounts, and editable server config.

Stored as JSON next to the app profiles (parent of `profiles_dir`), so the whole
setup — profiles, device configs, accounts, model choices — lives together and
is easy to back up or commit.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Optional

from phone_server.config import get_settings
from phone_server.models import Account, DeviceConfig, EditableConfig, ModelHost

settings = get_settings()


def _default_config() -> EditableConfig:
    return EditableConfig(
        default_model_base_url=settings.vlm_base_url,
        default_model_name=settings.vlm_model,
        default_lang=settings.default_lang,
        stream_fps=settings.default_stream_fps,
        model_hosts=[
            # Pre-seed the known LAN Ollama box + a local vLLM slot.
            ModelHost(name="lan-ollama", base_url="http://192.168.55.231:11434/v1", kind="ollama"),
            ModelHost(name="local-vllm", base_url=settings.vlm_base_url, kind="openai-compatible"),
        ],
    )


class Registry:
    """Loads/saves device configs, accounts, and editable server config."""

    def __init__(self, path: Optional[str] = None):
        root = os.path.dirname(settings.profiles_dir.rstrip("/")) or settings.profiles_dir
        os.makedirs(root, exist_ok=True)
        self.path = path or os.path.join(root, "registry.json")
        self.config: EditableConfig = _default_config()
        self.devices: dict[str, DeviceConfig] = {}
        self.load()

    # --- persistence -------------------------------------------------------

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            data = json.load(f)
        if "config" in data:
            self.config = EditableConfig.model_validate(data["config"])
        self.devices = {
            k: DeviceConfig.model_validate(v) for k, v in data.get("devices", {}).items()
        }

    def save(self) -> None:
        data = {
            "config": self.config.model_dump(),
            "devices": {k: v.model_dump() for k, v in self.devices.items()},
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # --- config ------------------------------------------------------------

    def update_config(self, patch: dict) -> EditableConfig:
        merged = self.config.model_dump()
        for k, v in patch.items():
            if v is not None:
                merged[k] = v
        self.config = EditableConfig.model_validate(merged)
        self.save()
        return self.config

    def effective_model(self, device_id: Optional[str] = None) -> dict[str, str]:
        """Resolve the model config for a device: device > registry default > env."""
        base_url = self.config.default_model_base_url or settings.vlm_base_url
        model = self.config.default_model_name or settings.vlm_model
        api_key = settings.vlm_api_key
        if device_id and device_id in self.devices:
            dc = self.devices[device_id]
            if dc.model_base_url:
                base_url = dc.model_base_url
            if dc.model_name:
                model = dc.model_name
            # match api key from a configured host if present
            for h in self.config.model_hosts:
                if h.base_url == base_url and h.api_key:
                    api_key = h.api_key
        return {"base_url": base_url, "model_name": model, "api_key": api_key}

    # --- devices -----------------------------------------------------------

    def get_device(self, device_id: str) -> DeviceConfig:
        return self.devices.get(device_id) or DeviceConfig(device_id=device_id)

    def upsert_device(self, device_id: str, patch: dict) -> DeviceConfig:
        dc = self.devices.get(device_id) or DeviceConfig(device_id=device_id)
        merged = dc.model_dump()
        for k, v in patch.items():
            if v is not None and k != "accounts":
                merged[k] = v
        dc = DeviceConfig.model_validate(merged)
        self.devices[device_id] = dc
        self.save()
        return dc

    def delete_device(self, device_id: str) -> bool:
        if device_id in self.devices:
            del self.devices[device_id]
            self.save()
            return True
        return False

    # --- accounts ----------------------------------------------------------

    def add_account(self, device_id: str, account: Account) -> Account:
        dc = self.devices.get(device_id) or DeviceConfig(device_id=device_id)
        if not account.id:
            account.id = uuid.uuid4().hex[:8]
        dc.accounts[account.id] = account
        self.devices[device_id] = dc
        self.save()
        return account

    def delete_account(self, device_id: str, account_id: str) -> bool:
        dc = self.devices.get(device_id)
        if dc and account_id in dc.accounts:
            del dc.accounts[account_id]
            self.save()
            return True
        return False

    def all_accounts(self) -> list[dict]:
        out = []
        for did, dc in self.devices.items():
            for acc in dc.accounts.values():
                out.append({"device_id": did, "device_label": dc.label, **acc.model_dump()})
        return out


# Module-level singleton.
REGISTRY = Registry()
