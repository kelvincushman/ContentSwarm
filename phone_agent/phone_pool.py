"""Phone Pool Manager for controlling multiple phones with easy switching."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from phone_agent import PhoneAgent
from phone_agent.adb import ADBConnection, list_devices
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig


@dataclass
class PhoneInfo:
    """Information about a phone in the pool."""

    device_id: str
    name: str
    description: str = ""
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class PhonePoolManager:
    """
    Manages a pool of phones and allows easy switching between them.

    Example:
        >>> manager = PhonePoolManager()
        >>> manager.load_phones("phones.json")
        >>> manager.select_phone("phone_1")
        >>> manager.run_task("Open Chrome")
        >>> manager.select_phone("phone_2")
        >>> manager.run_task("Open Gmail")
    """

    def __init__(
        self,
        model_config: Optional[ModelConfig] = None,
        agent_config: Optional[AgentConfig] = None,
        phones_config: Optional[str] = None
    ):
        """
        Initialize the Phone Pool Manager.

        Args:
            model_config: Configuration for the AI model.
            agent_config: Base configuration for agents.
            phones_config: Path to JSON file with phone configurations.
        """
        self.model_config = model_config or ModelConfig()
        self.base_agent_config = agent_config or AgentConfig()

        self.phones: Dict[str, PhoneInfo] = {}
        self.current_phone: Optional[str] = None
        self.current_agent: Optional[PhoneAgent] = None

        if phones_config:
            self.load_phones(phones_config)

    def load_phones(self, config_path: str) -> None:
        """
        Load phone configurations from JSON file.

        Args:
            config_path: Path to JSON configuration file.
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Phone config file not found: {config_path}")

        with open(config_file) as f:
            data = json.load(f)

        self.phones = {}
        for phone_data in data.get("phones", []):
            phone = PhoneInfo(
                device_id=phone_data["device_id"],
                name=phone_data["name"],
                description=phone_data.get("description", ""),
                tags=phone_data.get("tags", [])
            )
            self.phones[phone.name] = phone

        print(f"✅ Loaded {len(self.phones)} phones from {config_path}")

    def save_phones(self, config_path: str) -> None:
        """
        Save current phone configurations to JSON file.

        Args:
            config_path: Path to save JSON configuration.
        """
        data = {
            "phones": [
                {
                    "device_id": phone.device_id,
                    "name": phone.name,
                    "description": phone.description,
                    "tags": phone.tags
                }
                for phone in self.phones.values()
            ]
        }

        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✅ Saved {len(self.phones)} phones to {config_path}")

    def add_phone(
        self,
        name: str,
        device_id: str,
        description: str = "",
        tags: List[str] = None
    ) -> None:
        """
        Add a phone to the pool.

        Args:
            name: Unique name for the phone.
            device_id: ADB device ID (e.g., "192.168.1.100:5555").
            description: Optional description.
            tags: Optional tags for categorization.
        """
        if name in self.phones:
            raise ValueError(f"Phone '{name}' already exists in pool")

        phone = PhoneInfo(
            device_id=device_id,
            name=name,
            description=description,
            tags=tags or []
        )
        self.phones[name] = phone
        print(f"✅ Added phone: {name} ({device_id})")

    def remove_phone(self, name: str) -> None:
        """
        Remove a phone from the pool.

        Args:
            name: Name of the phone to remove.
        """
        if name not in self.phones:
            raise ValueError(f"Phone '{name}' not found in pool")

        if self.current_phone == name:
            self.current_phone = None
            self.current_agent = None

        del self.phones[name]
        print(f"✅ Removed phone: {name}")

    def list_phones(self, tag: Optional[str] = None) -> List[PhoneInfo]:
        """
        List all phones in the pool.

        Args:
            tag: Optional tag filter.

        Returns:
            List of PhoneInfo objects.
        """
        phones = list(self.phones.values())

        if tag:
            phones = [p for p in phones if tag in p.tags]

        return phones

    def select_phone(self, name: str) -> None:
        """
        Select a phone to control.

        Args:
            name: Name of the phone to select.
        """
        if name not in self.phones:
            raise ValueError(f"Phone '{name}' not found. Available: {list(self.phones.keys())}")

        phone = self.phones[name]

        # Create agent config with selected device
        agent_config = AgentConfig(
            max_steps=self.base_agent_config.max_steps,
            device_id=phone.device_id,
            lang=self.base_agent_config.lang,
            verbose=self.base_agent_config.verbose
        )

        # Create new agent for this phone
        self.current_agent = PhoneAgent(
            model_config=self.model_config,
            agent_config=agent_config
        )

        self.current_phone = name
        print(f"📱 Selected phone: {name} ({phone.device_id})")

    def get_current_phone(self) -> Optional[PhoneInfo]:
        """Get currently selected phone info."""
        if self.current_phone:
            return self.phones[self.current_phone]
        return None

    def run_task(self, task: str) -> str:
        """
        Run a task on the currently selected phone.

        Args:
            task: Natural language task description.

        Returns:
            Result message.
        """
        if not self.current_agent:
            raise RuntimeError("No phone selected. Use select_phone() first.")

        print(f"\n{'='*60}")
        print(f"📱 Running on: {self.current_phone}")
        print(f"📋 Task: {task}")
        print(f"{'='*60}\n")

        result = self.current_agent.run(task)
        return result

    def quick_run(self, phone_name: str, task: str) -> str:
        """
        Quick method to select phone and run task in one call.

        Args:
            phone_name: Name of phone to use.
            task: Task to execute.

        Returns:
            Result message.
        """
        self.select_phone(phone_name)
        return self.run_task(task)

    def scan_and_add_devices(self) -> int:
        """
        Scan for connected ADB devices and add them to pool.

        Returns:
            Number of new devices added.
        """
        devices = list_devices()
        added = 0

        for device in devices:
            # Generate name from device ID
            name = f"phone_{device.device_id.replace(':', '_').replace('.', '_')}"

            # Skip if already exists
            if name in self.phones:
                continue

            # Add device
            self.add_phone(
                name=name,
                device_id=device.device_id,
                description=f"Auto-detected {device.connection_type.value} device"
            )
            added += 1

        return added

    def check_connections(self) -> Dict[str, bool]:
        """
        Check connection status for all phones.

        Returns:
            Dictionary mapping phone names to connection status.
        """
        conn = ADBConnection()
        status = {}

        for name, phone in self.phones.items():
            is_connected = conn.is_connected(phone.device_id)
            status[name] = is_connected

        return status

    def print_status(self) -> None:
        """Print formatted status of all phones."""
        if not self.phones:
            print("❌ No phones in pool")
            return

        print(f"\n{'='*70}")
        print(f"📱 Phone Pool Status ({len(self.phones)} phones)")
        print(f"{'='*70}")

        status = self.check_connections()

        for name, phone in self.phones.items():
            is_current = "🔹" if name == self.current_phone else "  "
            is_connected = "✅" if status.get(name) else "❌"

            print(f"{is_current} {is_connected} {name:15} | {phone.device_id:25} | {phone.description}")

        print(f"{'='*70}\n")

        if self.current_phone:
            print(f"Current: {self.current_phone}")
        else:
            print("Current: None selected")


def create_sample_config(output_path: str = "phones.json") -> None:
    """
    Create a sample phone configuration file.

    Args:
        output_path: Path to save the sample config.
    """
    sample_config = {
        "phones": [
            {
                "device_id": "192.168.1.100:5555",
                "name": "phone_1",
                "description": "Samsung Galaxy S21",
                "tags": ["android", "testing"]
            },
            {
                "device_id": "192.168.1.101:5555",
                "name": "phone_2",
                "description": "Google Pixel 7",
                "tags": ["android", "testing"]
            },
            {
                "device_id": "emulator-5554",
                "name": "emulator_1",
                "description": "Android Emulator",
                "tags": ["emulator", "development"]
            }
        ]
    }

    with open(output_path, 'w') as f:
        json.dump(sample_config, f, indent=2)

    print(f"✅ Created sample config: {output_path}")
