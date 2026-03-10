"""Auto-discover USB-connected phones and map to persona slots."""

import json
import subprocess
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "phones_config.json"

# Persona slot order — first detected device = zara, second = marcus, third = jay
PERSONA_ORDER = ["zara", "marcus", "jay"]


def discover_devices() -> list[str]:
    """Run `adb devices` and return list of serial IDs for connected devices.

    Returns:
        List of device serial IDs (e.g. ["RFCN30XXXXX", "emulator-5554"]).
    """
    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[discovery] adb error: {e}")
        return []

    devices = []
    for line in result.stdout.strip().split("\n")[1:]:  # skip header
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def load_config() -> dict:
    """Load phones_config.json."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Write phones_config.json."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[discovery] Config saved to {CONFIG_PATH}")


def map_devices_to_personas(device_ids: list[str] | None = None) -> dict:
    """Discover USB devices and assign them to persona slots by order.

    Args:
        device_ids: Optional pre-discovered list. If None, runs adb devices.

    Returns:
        Updated config dict with device_id fields populated.
    """
    if device_ids is None:
        device_ids = discover_devices()

    config = load_config()
    phones = config.get("phones", [])

    # Build name -> index lookup
    name_to_idx = {p["name"]: i for i, p in enumerate(phones)}

    for slot_idx, persona_name in enumerate(PERSONA_ORDER):
        if slot_idx < len(device_ids) and persona_name in name_to_idx:
            phones[name_to_idx[persona_name]]["device_id"] = device_ids[slot_idx]
            print(f"[discovery] {persona_name} -> {device_ids[slot_idx]}")
        elif persona_name in name_to_idx:
            print(f"[discovery] {persona_name} -> no device (slot {slot_idx})")

    if len(device_ids) > len(PERSONA_ORDER):
        print(
            f"[discovery] {len(device_ids) - len(PERSONA_ORDER)} extra device(s) not mapped"
        )

    config["phones"] = phones
    save_config(config)
    return config


def get_device_for_persona(persona: str) -> str | None:
    """Look up the device_id for a given persona name.

    Args:
        persona: Persona name (case-insensitive).

    Returns:
        Device serial ID or None if not mapped / still 'auto'.
    """
    config = load_config()
    for phone in config.get("phones", []):
        if phone["name"].lower() == persona.lower():
            device_id = phone.get("device_id", "auto")
            return None if device_id == "auto" else device_id
    return None


def get_persona_platforms(persona: str) -> list[str]:
    """Return the platforms list for a persona."""
    config = load_config()
    for phone in config.get("phones", []):
        if phone["name"].lower() == persona.lower():
            return phone.get("platforms", [])
    return []


if __name__ == "__main__":
    print("[discovery] Scanning for USB-connected devices...")
    devices = discover_devices()
    print(f"[discovery] Found {len(devices)} device(s): {devices}")
    map_devices_to_personas(devices)
