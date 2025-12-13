#!/usr/bin/env python3
"""
Phone Pool CLI - Easy interface for controlling multiple phones.

Usage:
    python phone_pool_cli.py --config phones_config.json

Commands:
    list                    - List all phones
    status                  - Show connection status
    select <phone_name>     - Select a phone
    run <phone_name> "task" - Run task on specific phone
    interactive             - Enter interactive mode
    quit/exit               - Exit
"""

import argparse
import os
import sys

from phone_agent.model import ModelConfig
from phone_agent.agent import AgentConfig
from phone_agent.phone_pool import PhonePoolManager, create_sample_config


def print_banner():
    """Print welcome banner."""
    print("\n" + "="*70)
    print("📱 Phone Pool Manager - Control Multiple Phones")
    print("="*70 + "\n")


def print_help():
    """Print available commands."""
    print("\nAvailable Commands:")
    print("-" * 50)
    print("  list                    - List all phones in pool")
    print("  status                  - Show connection status")
    print("  select <phone_name>     - Select a phone to control")
    print("  run <phone_name> 'task' - Run task on specific phone")
    print("  current                 - Show currently selected phone")
    print("  help                    - Show this help message")
    print("  quit/exit               - Exit the program")
    print("-" * 50 + "\n")


def interactive_mode(manager: PhonePoolManager):
    """Run interactive command mode."""
    print_banner()
    print("Entering interactive mode. Type 'help' for commands.\n")

    while True:
        try:
            # Show current phone in prompt
            current = manager.current_phone or "None"
            command = input(f"[{current}]> ").strip()

            if not command:
                continue

            # Parse command
            parts = command.split(maxsplit=1)
            cmd = parts[0].lower()

            # Handle commands
            if cmd in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break

            elif cmd == 'help':
                print_help()

            elif cmd == 'list':
                phones = manager.list_phones()
                if phones:
                    print(f"\n📱 Available Phones ({len(phones)}):")
                    print("-" * 60)
                    for phone in phones:
                        current_marker = "🔹" if phone.name == manager.current_phone else "  "
                        print(f"{current_marker} {phone.name:15} | {phone.device_id:25} | {phone.description}")
                    print("-" * 60 + "\n")
                else:
                    print("❌ No phones in pool")

            elif cmd == 'status':
                manager.print_status()

            elif cmd == 'current':
                current_phone = manager.get_current_phone()
                if current_phone:
                    print(f"📱 Current: {current_phone.name} ({current_phone.device_id})")
                else:
                    print("❌ No phone selected")

            elif cmd == 'select':
                if len(parts) < 2:
                    print("❌ Usage: select <phone_name>")
                    continue

                phone_name = parts[1]
                try:
                    manager.select_phone(phone_name)
                except ValueError as e:
                    print(f"❌ Error: {e}")

            elif cmd == 'run':
                if len(parts) < 2:
                    print("❌ Usage: run <phone_name> 'task'")
                    continue

                # Parse phone name and task
                args = parts[1].split(maxsplit=1)
                if len(args) < 2:
                    print("❌ Usage: run <phone_name> 'task'")
                    continue

                phone_name = args[0]
                task = args[1].strip("'\"")

                try:
                    result = manager.quick_run(phone_name, task)
                    print(f"\n✅ Result: {result}\n")
                except Exception as e:
                    print(f"❌ Error: {e}")

            else:
                # Assume it's a task for current phone
                if manager.current_agent:
                    try:
                        result = manager.run_task(command)
                        print(f"\n✅ Result: {result}\n")
                    except Exception as e:
                        print(f"❌ Error: {e}")
                else:
                    print(f"❌ Unknown command: {cmd}")
                    print("Type 'help' for available commands")

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phone Pool Manager - Control multiple phones",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Interactive mode
    python phone_pool_cli.py --config phones_config.json

    # Run specific task
    python phone_pool_cli.py --config phones_config.json --phone phone_01 --task "Open Chrome"

    # Create sample config
    python phone_pool_cli.py --create-sample-config my_phones.json
        """
    )

    # Configuration options
    parser.add_argument(
        "--config",
        type=str,
        default="phones_config.json",
        help="Path to phones configuration JSON file"
    )

    parser.add_argument(
        "--create-sample-config",
        type=str,
        metavar="PATH",
        help="Create a sample phones configuration file"
    )

    # Model options
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
        help="Model API base URL"
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b-multilingual"),
        help="Model name"
    )

    parser.add_argument(
        "--apikey",
        type=str,
        default=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
        help="API key for model authentication"
    )

    parser.add_argument(
        "--lang",
        type=str,
        choices=["cn", "en"],
        default=os.getenv("PHONE_AGENT_LANG", "en"),
        help="Language for system prompt (cn or en, default: en)"
    )

    # Task options
    parser.add_argument(
        "--phone",
        type=str,
        help="Phone name to use (skips interactive mode)"
    )

    parser.add_argument(
        "--task",
        type=str,
        help="Task to execute (requires --phone)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all phones and exit"
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show connection status and exit"
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress verbose output"
    )

    args = parser.parse_args()

    # Handle sample config creation
    if args.create_sample_config:
        create_sample_config(args.create_sample_config)
        return

    # Create model config
    model_config = ModelConfig(
        base_url=args.base_url,
        model_name=args.model,
        api_key=args.apikey
    )

    # Create agent config
    agent_config = AgentConfig(
        lang=args.lang,
        verbose=not args.quiet
    )

    # Create phone pool manager
    try:
        manager = PhonePoolManager(
            model_config=model_config,
            agent_config=agent_config,
            phones_config=args.config
        )
    except FileNotFoundError:
        print(f"❌ Config file not found: {args.config}")
        print(f"\nCreate one with: python phone_pool_cli.py --create-sample-config {args.config}")
        sys.exit(1)

    # Handle list command
    if args.list:
        phones = manager.list_phones()
        print(f"\n📱 Available Phones ({len(phones)}):")
        print("-" * 60)
        for phone in phones:
            print(f"  {phone.name:15} | {phone.device_id:25} | {phone.description}")
        print("-" * 60 + "\n")
        return

    # Handle status command
    if args.status:
        manager.print_status()
        return

    # Handle direct task execution
    if args.phone and args.task:
        try:
            result = manager.quick_run(args.phone, args.task)
            print(f"\n✅ Result: {result}\n")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
        return

    # Enter interactive mode
    interactive_mode(manager)


if __name__ == "__main__":
    main()
