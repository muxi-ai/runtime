#!/usr/bin/env python3
"""
Add Secret - MUXI Runtime Utility

Tool for adding secrets to a formation's encrypted secrets store.
Operates in the current working directory.

NOTE: WE DO NOT NEED TO USE OBSERVABILITY HERE!
This is a development-only tool and does not interfere with production runtime.
"""

import sys
import argparse
import asyncio
import warnings
from pathlib import Path
import os

from ..services.secrets import SecretsManager


# Suppress common warnings that clutter the output
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="python-magic not available")
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["LOGURU_LEVEL"] = "ERROR"


async def add_secret_to_formation(secret_name: str, secret_value: str):
    """Add a secret to the formation's secrets store in current directory."""
    formation_dir = Path(".")
    print(f"🔐 Adding secret '{secret_name}' to formation...")
    print(f"📁 Formation directory: {formation_dir.absolute()}")

    try:
        # Initialize SecretsManager
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()

        # Store the secret (also updates secrets)
        await secrets_manager.store_secret(secret_name, secret_value)

        print(f"✅ Secret '{secret_name}' added successfully!")

        # Show file locations
        key_file = formation_dir / ".key"
        secrets_file = formation_dir / "secrets.enc"
        example_file = formation_dir / "secrets"

        print("\n📂 Files updated:")
        print(f"   🔑 Master key: {key_file.absolute()}")
        print(f"   🔒 Secrets: {secrets_file.absolute()}")
        print(f"   📝 Example: {example_file.absolute()}")

        return secrets_manager

    except Exception:
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
        elif args.command and args.value:
            asyncio.run(add_secret_to_formation(args.command, args.value))
        elif args.command and not args.value:
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
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
