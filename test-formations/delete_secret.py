#!/usr/bin/env python3
"""
Delete Secret - MUXI Runtime Utility (Fixed for direct execution)
"""

import sys
import argparse
import asyncio
import warnings
from pathlib import Path
import os

# Fix the import path
sys.path.insert(0, "/Users/ran/Projects/muxi/code/runtime/src")
from muxi.runtime.services.secrets import SecretsManager  # noqa: E402

# Suppress common warnings that clutter the output
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="python-magic not available")
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["LOGURU_LEVEL"] = "ERROR"


async def delete_secret_from_formation(secret_name: str):
    """Delete a secret from the formation's secrets store in current directory."""
    formation_dir = Path(".")
    print(f"🔐 Deleting secret '{secret_name}' from formation...")
    print(f"📁 Formation directory: {formation_dir.absolute()}")

    try:
        # Initialize SecretsManager
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()

        # Delete the secret
        await secrets_manager.delete_secret(secret_name)

        print(f"✅ Secret '{secret_name}' deleted successfully!")

        return secrets_manager

    except Exception as e:
        print(f"❌ Error deleting secret: {e}")
        raise


async def list_secrets_in_formation():
    """List all secrets in the formation in current directory."""
    formation_dir = Path(".")
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

        return secrets

    except Exception:
        raise


def main():
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
        elif args.command:
            # Confirm deletion
            response = input(f"⚠️  Are you sure you want to delete secret '{args.command}'? (y/N): ")
            if response.lower() == "y":
                asyncio.run(delete_secret_from_formation(args.command))
            else:
                print("❌ Deletion cancelled")
                sys.exit(0)
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
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
