#!/usr/bin/env python3
"""
Add Secret - MUXI Runtime Utility

Tool for adding secrets to a formation's encrypted secrets store.
Operates in the current working directory.
"""

import sys
import argparse
import asyncio
import warnings
from pathlib import Path
import os

from ..secrets import SecretsManager

# Observability integration
try:
    from ..observability import ObservabilityManager, ConversationEventType, SystemEventType, EventLevel
except ImportError:
    # Graceful fallback if observability is not available
    ObservabilityManager = None
    ConversationEventType = None
    EventLevel = None

# Suppress common warnings that clutter the output
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="python-magic not available")
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["LOGURU_LEVEL"] = "ERROR"


async def add_secret_to_formation(secret_name: str, secret_value: str):
    """Add a secret to the formation's secrets store in current directory."""
    formation_dir = Path(".")

    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=SystemEventType.SECRET_STORAGE_STARTED,
                level=EventLevel.INFO,
                message="Starting secret addition to formation",
                data={
                    "secret_name": secret_name,
                    "formation_dir": str(formation_dir.absolute()),
                    "operation": "add_secret_to_formation",
                    "secret_value_length": len(secret_value) if secret_value else 0
                }
            )
        except Exception:
            pass

    print(f"🔐 Adding secret '{secret_name}' to formation...")
    print(f"📁 Formation directory: {formation_dir.absolute()}")

    try:
        # Initialize SecretsManager
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()

        # Store the secret
        await secrets_manager.store_secret(secret_name, secret_value)

        print(f"✅ Secret '{secret_name}' added successfully!")

        # Show file locations
        key_file = formation_dir / ".key"
        secrets_file = formation_dir / "secrets.enc"

        print("\n📂 Files created:")
        print(f"   🔑 Master key: {key_file.absolute()}")
        print(f"   🔒 Secrets: {secrets_file.absolute()}")

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=SystemEventType.SECRET_STORAGE_COMPLETED,
                    level=EventLevel.INFO,
                    message="Secret addition completed successfully",
                    data={
                        "secret_name": secret_name,
                        "formation_dir": str(formation_dir.absolute()),
                        "operation": "add_secret_to_formation",
                        "key_file": str(key_file.absolute()),
                        "secrets_file": str(secrets_file.absolute()),
                        "key_file_exists": key_file.exists(),
                        "secrets_file_exists": secrets_file.exists(),
                        "secret_value_length": len(secret_value) if secret_value else 0
                    }
                )
            except Exception:
                pass

        return secrets_manager

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Secret addition failed with error",
                    data={
                        "secret_name": secret_name,
                        "formation_dir": str(formation_dir.absolute()),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "operation": "add_secret_to_formation"
                    }
                )
            except Exception:
                pass
        raise


async def list_secrets_in_formation():
    """List all secrets in the formation in current directory."""
    formation_dir = Path(".")

    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=SystemEventType.SECRET_LISTING_STARTED,
                level=EventLevel.DEBUG,
                message="Starting secret listing for formation",
                data={
                    "formation_dir": str(formation_dir.absolute()),
                    "operation": "list_secrets_in_formation"
                }
            )
        except Exception:
            pass

    print(f"📁 Formation directory: {formation_dir.absolute()}")

    try:
        # Initialize SecretsManager
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()

        # List secrets
        secrets = await secrets_manager.list_secrets()

        print("📋 Secrets in formation:")
        if secrets:
            for secret in secrets:
                print(f"   • {secret}")
        else:
            print("   (no secrets found)")

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=SystemEventType.SECRET_LISTING_COMPLETED,
                    level=EventLevel.DEBUG,
                    message="Secret listing completed successfully",
                    data={
                        "formation_dir": str(formation_dir.absolute()),
                        "secrets_count": len(secrets),
                        "secrets": list(secrets),
                        "operation": "list_secrets_in_formation"
                    }
                )
            except Exception:
                pass

        return secrets

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Secret listing failed with error",
                    data={
                        "formation_dir": str(formation_dir.absolute()),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "operation": "list_secrets_in_formation"
                    }
                )
            except Exception:
                pass
        raise


def main():
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=SystemEventType.UTILITY_STARTED,
                level=EventLevel.INFO,
                message="Add secret utility started",
                data={
                    "utility": "add_secret",
                    "args": sys.argv[1:] if len(sys.argv) > 1 else [],
                    "working_dir": str(Path(".").absolute())
                }
            )
        except Exception:
            pass

    # Check if no arguments provided and show custom help
    if len(sys.argv) == 1:
        print("🔐 MUXI Secrets Management - Add Secret")
        print("\nUsage:")
        print(f"  {sys.argv[0]} <SECRET_NAME> <secret_value>")
        print(f"  {sys.argv[0]} list")
        print("\nExamples:")
        print("  cd /path/to/formation")
        print(f"  {sys.argv[0]} OPENAI_API_KEY 'sk-your-key-here'")
        print(f"  {sys.argv[0]} WEATHER_API_KEY 'your-weather-key'")
        print(f"  {sys.argv[0]} list")
        print(f"\nFor detailed help: {sys.argv[0]} --help")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Add secrets to MUXI Formation in current directory",
        epilog="""
Examples:
  cd /path/to/formation
  %(prog)s OPENAI_API_KEY "sk-your-key-here"
  %(prog)s WEATHER_API_KEY "your-weather-key"
  %(prog)s list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", help="SECRET_NAME to add, or 'list' to show secrets")
    parser.add_argument("value", nargs="?", help="Secret value (required when adding a secret)")

    args = parser.parse_args()

    try:
        if args.command == "list":
            asyncio.run(list_secrets_in_formation())
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=SystemEventType.UTILITY_COMPLETED,
                        level=EventLevel.INFO,
                        message="Add secret utility completed successfully",
                        data={
                            "utility": "add_secret",
                            "command": "list",
                            "result": "success"
                        }
                    )
                except Exception:
                    pass
        elif args.command and args.value:
            asyncio.run(add_secret_to_formation(args.command, args.value))
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=SystemEventType.UTILITY_COMPLETED,
                        level=EventLevel.INFO,
                        message="Add secret utility completed successfully",
                        data={
                            "utility": "add_secret",
                            "command": args.command,
                            "result": "success"
                        }
                    )
                except Exception:
                    pass
        elif args.command and not args.value:
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=SystemEventType.UTILITY_COMPLETED,
                        level=EventLevel.WARNING,
                        message="Add secret utility completed with failure",
                        data={
                            "utility": "add_secret",
                            "command": args.command,
                            "result": "failure",
                            "reason": "missing_secret_value"
                        }
                    )
                except Exception:
                    pass
            print(f"❌ Error: Secret value required for '{args.command}'")
            print(f"\nUsage: {sys.argv[0]} <SECRET_NAME> <secret_value>")
            print(f"Example: {sys.argv[0]} OPENAI_API_KEY 'sk-your-key-here'")
            sys.exit(1)
        else:
            print("🔐 MUXI Secrets Management - Add Secret")
            print("\nUsage:")
            print(f"  {sys.argv[0]} <SECRET_NAME> <secret_value>")
            print(f"  {sys.argv[0]} list")
            print("\nExamples:")
            print("  cd /path/to/formation")
            print(f"  {sys.argv[0]} OPENAI_API_KEY 'sk-your-key-here'")
            print(f"  {sys.argv[0]} WEATHER_API_KEY 'your-weather-key'")
            print(f"  {sys.argv[0]} list")
            sys.exit(1)

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Add secret utility failed with error",
                    data={
                        "utility": "add_secret",
                        "command": args.command if 'args' in locals() else None,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
