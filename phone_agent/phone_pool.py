"""Phone Pool Manager for controlling multiple phones with easy switching."""

import json
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from phone_agent import PhoneAgent
from phone_agent.adb import ADBConnection, list_devices
from phone_agent.agent import AgentConfig
from phone_agent.model import ModelConfig


@dataclass
class TaskResult:
    """Result of an async phone task."""

    task_id: str
    phone_name: str
    task: str
    status: str  # "pending", "running", "completed", "failed"
    result: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


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
        phones_config: Optional[str] = None,
        max_parallel: int = 20,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initialize the Phone Pool Manager.

        Args:
            model_config: Configuration for the AI model.
            agent_config: Base configuration for agents.
            phones_config: Path to JSON file with phone configurations.
            max_parallel: Maximum number of phones to run in parallel.
            event_callback: Optional callback for task lifecycle events.
        """
        self.model_config = model_config or ModelConfig()
        self.base_agent_config = agent_config or AgentConfig()

        self.phones: Dict[str, PhoneInfo] = {}
        self.current_phone: Optional[str] = None
        self.current_agent: Optional[PhoneAgent] = None

        # Parallel execution
        self._executor = ThreadPoolExecutor(max_workers=max_parallel)
        self._phone_locks: Dict[str, threading.Lock] = {}
        self._tasks: Dict[str, TaskResult] = {}
        self._event_callback = event_callback

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

    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set callback for task lifecycle events."""
        self._event_callback = callback

    def _emit_event(self, event: Dict[str, Any]) -> None:
        """Emit a task lifecycle event."""
        if self._event_callback:
            try:
                self._event_callback(event)
            except Exception:
                pass

    def _get_phone_lock(self, phone_name: str) -> threading.Lock:
        """Get or create a lock for a specific phone."""
        if phone_name not in self._phone_locks:
            self._phone_locks[phone_name] = threading.Lock()
        return self._phone_locks[phone_name]

    def _run_task_on_phone(self, phone_name: str, task: str, task_id: str) -> str:
        """Run a task on a specific phone with locking. Used by async methods."""
        if phone_name not in self.phones:
            raise ValueError(f"Phone '{phone_name}' not found")

        lock = self._get_phone_lock(phone_name)
        if not lock.acquire(timeout=0):
            raise RuntimeError(f"Phone '{phone_name}' is busy with another task")

        try:
            phone = self.phones[phone_name]
            task_result = self._tasks.get(task_id)
            if task_result:
                task_result.status = "running"
                task_result.started_at = time.time()

            self._emit_event({
                "event": "task_started",
                "task_id": task_id,
                "phone": phone_name,
                "task": task,
                "timestamp": time.time()
            })

            agent_config = AgentConfig(
                max_steps=self.base_agent_config.max_steps,
                device_id=phone.device_id,
                lang=self.base_agent_config.lang,
                verbose=self.base_agent_config.verbose
            )

            agent = PhoneAgent(
                model_config=self.model_config,
                agent_config=agent_config
            )

            result = agent.run(task)

            if task_result:
                task_result.status = "completed"
                task_result.result = result
                task_result.completed_at = time.time()

            self._emit_event({
                "event": "task_completed",
                "task_id": task_id,
                "phone": phone_name,
                "task": task,
                "result": result,
                "timestamp": time.time()
            })

            return result

        except Exception as e:
            if task_id in self._tasks:
                self._tasks[task_id].status = "failed"
                self._tasks[task_id].error = str(e)
                self._tasks[task_id].completed_at = time.time()

            self._emit_event({
                "event": "task_failed",
                "task_id": task_id,
                "phone": phone_name,
                "task": task,
                "error": str(e),
                "timestamp": time.time()
            })
            raise

        finally:
            lock.release()

    def async_run(self, phone_name: str, task: str) -> str:
        """
        Submit a task for async execution on a phone.

        Args:
            phone_name: Name of phone to use.
            task: Task to execute.

        Returns:
            task_id that can be used to check status via get_task_status().
        """
        task_id = str(uuid.uuid4())[:8]

        self._tasks[task_id] = TaskResult(
            task_id=task_id,
            phone_name=phone_name,
            task=task,
            status="pending"
        )

        self._executor.submit(self._run_task_on_phone, phone_name, task, task_id)
        return task_id

    def batch_run_parallel(self, tasks: Dict[str, str]) -> Dict[str, str]:
        """
        Run tasks on multiple phones in parallel.

        Args:
            tasks: Dict mapping phone_name to task description.

        Returns:
            Dict mapping phone_name to task_id.
        """
        task_ids = {}
        for phone_name, task in tasks.items():
            task_ids[phone_name] = self.async_run(phone_name, task)
        return task_ids

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of an async task.

        Args:
            task_id: The task ID returned by async_run.

        Returns:
            Dict with task status details, or None if not found.
        """
        task_result = self._tasks.get(task_id)
        if not task_result:
            return None

        return {
            "task_id": task_result.task_id,
            "phone": task_result.phone_name,
            "task": task_result.task,
            "status": task_result.status,
            "result": task_result.result,
            "error": task_result.error,
            "started_at": task_result.started_at,
            "completed_at": task_result.completed_at
        }

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get status of all tracked tasks."""
        return [self.get_task_status(tid) for tid in self._tasks]

    def shutdown(self) -> None:
        """Shutdown the thread pool executor."""
        self._executor.shutdown(wait=False)

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
