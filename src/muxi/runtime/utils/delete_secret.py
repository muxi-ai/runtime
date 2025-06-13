#!/usr/bin/env python3
"""
Delete Secret - MUXI Runtime Utility

Tool for deleting secrets from a formation's encrypted secrets store.
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


async def delete_secret_from_formation(secret_name: str):
    """Delete a secret from the formation's secrets store in current directory."""
    formation_dir = Path(".")

    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=ConversationEventType.SECRET_DELETION_STARTED,
                level=EventLevel.INFO,
                message="Starting secret deletion from formation",
                data={
                    "secret_name": secret_name,
                    "formation_dir": str(formation_dir.absolute()),
                    "operation": "delete_secret_from_formation"
                }
            )
        except Exception:
            pass

    print(f"🗑️  Deleting secret '{secret_name}' from formation...")
    print(f"📁 Formation directory: {formation_dir.absolute()}")

    try:
        # Initialize SecretsManager
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()

        # Check if secret exists
        secrets = await secrets_manager.list_secrets()
        if secret_name not in secrets:
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.SECRET_DELETION_COMPLETED,
                        level=EventLevel.WARNING,
                        message="Secret deletion failed - secret not found",
                        data={
                            "secret_name": secret_name,
                            "formation_dir": str(formation_dir.absolute()),
                            "result": "not_found",
                            "available_secrets": list(secrets)
                        }
                    )
                except Exception:
                    pass

            print(f"❌ Secret '{secret_name}' not found in formation!")
            print("\n📋 Available secrets:")
            if secrets:
                for secret in secrets:
                    print(f"   • {secret}")
            else:
                print("   (no secrets found)")
            return False

        # Delete the secret
        await secrets_manager.delete_secret(secret_name)

        print(f"✅ Secret '{secret_name}' deleted successfully!")

        # Show remaining secrets
        remaining_secrets = await secrets_manager.list_secrets()
        print("\n📋 Remaining secrets:")
        if remaining_secrets:
            for secret in remaining_secrets:
                print(f"   • {secret}")
        else:
            print("   (no secrets remaining)")

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.SECRET_DELETION_COMPLETED,
                    level=EventLevel.INFO,
                    message="Secret deletion completed successfully",
                    data={
                        "secret_name": secret_name,
                        "formation_dir": str(formation_dir.absolute()),
                        "result": "success",
                        "remaining_secrets_count": len(remaining_secrets),
                        "remaining_secrets": list(remaining_secrets)
                    }
                )
            except Exception:
                pass

        return True

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Secret deletion failed with error",
                    data={
                        "secret_name": secret_name,
                        "formation_dir": str(formation_dir.absolute()),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "operation": "delete_secret_from_formation"
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
                event_type=ConversationEventType.SECRET_LISTING_STARTED,
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
                    event_type=ConversationEventType.SECRET_LISTING_COMPLETED,
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
                event_type=ConversationEventType.UTILITY_STARTED,
                level=EventLevel.INFO,
                message="Delete secret utility started",
                data={
                    "utility": "delete_secret",
                    "args": sys.argv[1:] if len(sys.argv) > 1 else [],
                    "working_dir": str(Path(".").absolute())
                }
            )
        except Exception:
            pass

    # Check if no arguments provided and show custom help
    if len(sys.argv) == 1:
        print("🗑️  MUXI Secrets Management - Delete Secret")
        print("\nUsage:")
        print(f"  {sys.argv[0]} <SECRET_NAME>")
        print(f"  {sys.argv[0]} list")
        print("\nExamples:")
        print("  cd /path/to/formation")
        print(f"  {sys.argv[0]} OPENAI_API_KEY")
        print(f"  {sys.argv[0]} WEATHER_API_KEY")
        print(f"  {sys.argv[0]} list")
        print(f"\nFor detailed help: {sys.argv[0]} --help")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Delete secrets from MUXI Formation in current directory",
        epilog="""
Examples:
  cd /path/to/formation
  %(prog)s OPENAI_API_KEY
  %(prog)s WEATHER_API_KEY
  %(prog)s list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", help="SECRET_NAME to delete, or 'list' to show secrets")

    args = parser.parse_args()

    try:
        if args.command == "list":
            asyncio.run(list_secrets_in_formation())
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.UTILITY_COMPLETED,
                        level=EventLevel.INFO,
                        message="Delete secret utility completed successfully",
                        data={
                            "utility": "delete_secret",
                            "command": "list",
                            "result": "success"
                        }
                    )
                except Exception:
                    pass
        elif args.command:
            success = asyncio.run(delete_secret_from_formation(args.command))
            if not success:
                if ObservabilityManager and ConversationEventType:
                    try:
                        ObservabilityManager.get_instance().log_event(
                            event_type=ConversationEventType.UTILITY_COMPLETED,
                            level=EventLevel.WARNING,
                            message="Delete secret utility completed with failure",
                            data={
                                "utility": "delete_secret",
                                "command": args.command,
                                "result": "failure",
                                "reason": "secret_not_found"
                            }
                        )
                    except Exception:
                        pass
                sys.exit(1)
            else:
                if ObservabilityManager and ConversationEventType:
                    try:
                        ObservabilityManager.get_instance().log_event(
                            event_type=ConversationEventType.UTILITY_COMPLETED,
                            level=EventLevel.INFO,
                            message="Delete secret utility completed successfully",
                            data={
                                "utility": "delete_secret",
                                "command": args.command,
                                "result": "success"
                            }
                        )
                    except Exception:
                        pass
        else:
            print("🗑️  MUXI Secrets Management - Delete Secret")
            print("\nUsage:")
            print(f"  {sys.argv[0]} <SECRET_NAME>")
            print(f"  {sys.argv[0]} list")
            print("\nExamples:")
            print("  cd /path/to/formation")
            print(f"  {sys.argv[0]} OPENAI_API_KEY")
            print(f"  {sys.argv[0]} WEATHER_API_KEY")
            print(f"  {sys.argv[0]} list")
            sys.exit(1)

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Delete secret utility failed with error",
                    data={
                        "utility": "delete_secret",
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
