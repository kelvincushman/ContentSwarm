#!/usr/bin/env python3
"""
Example: Using Phone Pool Manager to control multiple phones.

This example shows different ways to manage and control 20+ phones.
"""

from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager


def example_basic_usage():
    """Example 1: Basic phone pool usage."""
    print("\n" + "="*70)
    print("Example 1: Basic Phone Pool Usage")
    print("="*70 + "\n")

    # Create model config
    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    # Create agent config with English
    agent_config = AgentConfig(
        lang="en",
        verbose=True
    )

    # Create phone pool manager
    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    # Show all phones
    manager.print_status()

    # Select and use phone 1
    manager.select_phone("phone_01")
    manager.run_task("Open Chrome browser")

    # Switch to phone 2
    manager.select_phone("phone_02")
    manager.run_task("Open Gmail")

    # Quick run on phone 3 without selecting
    manager.quick_run("phone_03", "Open Google Maps")


def example_batch_tasks():
    """Example 2: Run different tasks on multiple phones."""
    print("\n" + "="*70)
    print("Example 2: Batch Tasks on Multiple Phones")
    print("="*70 + "\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=False)

    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    # Define tasks for different phones
    tasks = {
        "phone_01": "Open Chrome and search for 'python tutorial'",
        "phone_02": "Open Gmail and check inbox",
        "phone_03": "Open Google Maps and search for coffee shops",
        "phone_04": "Open YouTube and search for music",
        "phone_05": "Open Google Calendar and check today's events"
    }

    # Execute tasks sequentially
    for phone_name, task in tasks.items():
        print(f"\n📱 Processing {phone_name}...")
        try:
            result = manager.quick_run(phone_name, task)
            print(f"✅ {phone_name}: {result}")
        except Exception as e:
            print(f"❌ {phone_name}: Error - {e}")


def example_dynamic_phone_management():
    """Example 3: Dynamically add/remove phones."""
    print("\n" + "="*70)
    print("Example 3: Dynamic Phone Management")
    print("="*70 + "\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en")

    # Create empty manager
    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config
    )

    # Add phones dynamically
    manager.add_phone(
        name="test_phone_1",
        device_id="192.168.1.200:5555",
        description="Test device 1",
        tags=["testing", "development"]
    )

    manager.add_phone(
        name="test_phone_2",
        device_id="192.168.1.201:5555",
        description="Test device 2",
        tags=["testing"]
    )

    # Save configuration
    manager.save_phones("test_phones.json")

    # Use the phones
    manager.quick_run("test_phone_1", "Open Settings")
    manager.quick_run("test_phone_2", "Open Chrome")

    # Remove a phone
    manager.remove_phone("test_phone_2")


def example_auto_discover():
    """Example 4: Auto-discover connected devices."""
    print("\n" + "="*70)
    print("Example 4: Auto-Discover Connected Devices")
    print("="*70 + "\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en")

    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config
    )

    # Scan for connected devices
    added = manager.scan_and_add_devices()
    print(f"✅ Added {added} new devices")

    # Show all discovered phones
    manager.print_status()

    # Save discovered phones
    if added > 0:
        manager.save_phones("discovered_phones.json")


def example_with_api_service():
    """Example 5: Using third-party API service."""
    print("\n" + "="*70)
    print("Example 5: Using Third-Party API Service")
    print("="*70 + "\n")

    # Using Novita AI or other service
    model_config = ModelConfig(
        base_url="https://api.novita.ai/openai",
        model_name="zai-org/autoglm-phone-9b-multilingual",
        api_key="your-novita-api-key"  # Replace with your key
    )

    agent_config = AgentConfig(lang="en", verbose=True)

    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    # Now you can control all 20 phones using the API
    # No local GPU needed!
    manager.quick_run("phone_01", "Open Chrome browser")
    manager.quick_run("phone_02", "Open Gmail")
    # ... and so on for all 20 phones


def example_sequential_workflow():
    """Example 6: Sequential workflow across phones."""
    print("\n" + "="*70)
    print("Example 6: Sequential Workflow Across Phones")
    print("="*70 + "\n")

    model_config = ModelConfig(
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual"
    )

    agent_config = AgentConfig(lang="en", verbose=True)

    manager = PhonePoolManager(
        model_config=model_config,
        agent_config=agent_config,
        phones_config="phones_config.json"
    )

    # Workflow: Check different apps on different phones
    workflow = [
        ("phone_01", "Open Gmail and check for new messages"),
        ("phone_02", "Open Google Calendar and check today's schedule"),
        ("phone_03", "Open Google Maps and navigate to work"),
        ("phone_04", "Open Chrome and check news"),
        ("phone_05", "Open YouTube and find music playlist")
    ]

    print("Starting sequential workflow...\n")

    for phone, task in workflow:
        print(f"📱 Step: {task}")
        result = manager.quick_run(phone, task)
        print(f"✅ Completed: {result}\n")

    print("✅ Workflow completed!")


if __name__ == "__main__":
    print("\n📱 Phone Pool Manager - Usage Examples\n")
    print("Choose an example to run:")
    print("1. Basic usage")
    print("2. Batch tasks on multiple phones")
    print("3. Dynamic phone management")
    print("4. Auto-discover connected devices")
    print("5. Using third-party API service")
    print("6. Sequential workflow across phones")

    choice = input("\nEnter example number (1-6): ").strip()

    examples = {
        "1": example_basic_usage,
        "2": example_batch_tasks,
        "3": example_dynamic_phone_management,
        "4": example_auto_discover,
        "5": example_with_api_service,
        "6": example_sequential_workflow
    }

    if choice in examples:
        examples[choice]()
    else:
        print("Invalid choice. Running basic usage example...")
        example_basic_usage()
