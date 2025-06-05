#!/usr/bin/env python3
"""
Add Secret - MUXI Runtime Utility

Tool for adding secrets to a formation's encrypted secrets store.
"""

import sys
import argparse
import asyncio
import warnings
from pathlib import Path
import os

# Suppress common warnings that clutter the output
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="python-magic not available")
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["LOGURU_LEVEL"] = "ERROR"

# Add the runtime directory to Python path for imports
runtime_dir = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(runtime_dir))

from runtime.muxi.runtime.secrets import SecretsManager


async def add_secret_to_formation(formation_path: str, secret_name: str, secret_value: str):
    """Add a secret to the formation's secrets store."""
    if formation_path.endswith('.yaml'):
        formation_dir = Path(formation_path).parent
    else:
        formation_dir = Path(formation_path)

    print(f"🔐 Adding secret '{secret_name}' to formation...")
    print(f"📁 Formation directory: {formation_dir}")

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
    print(f"   🔑 Master key: {key_file}")
    print(f"   🔒 Secrets: {secrets_file}")

    return secrets_manager


async def list_secrets_in_formation(formation_path: str):
    """List all secrets in the formation."""
    if formation_path.endswith('.yaml'):
        formation_dir = Path(formation_path).parent
    else:
        formation_dir = Path(formation_path)

    print(f"📁 Formation directory: {formation_dir}")

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


def main():
    # Check if no arguments provided and show custom help
    if len(sys.argv) == 1:
        print("🔐 MUXI Secrets Management - Add Secret")
        print("\nUsage:")
        print(f"  {sys.argv[0]} <formation_path> <SECRET_NAME> <secret_value>")
        print(f"  {sys.argv[0]} <formation_path> list")
        print("\nExamples:")
        print(f"  {sys.argv[0]} examples/configs OPENAI_API_KEY 'sk-your-key-here'")
        print(f"  {sys.argv[0]} formation.yaml WEATHER_API_KEY 'your-weather-key'")
        print(f"  {sys.argv[0]} examples/configs list")
        print(f"\nFor detailed help: {sys.argv[0]} --help")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Add secrets to MUXI Formation",
        epilog="""
Examples:
  %(prog)s examples/configs OPENAI_API_KEY "sk-your-key-here"
  %(prog)s formation.yaml WEATHER_API_KEY "your-weather-key"
  %(prog)s examples/configs list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("formation_path", help="Path to formation directory or YAML file")
    parser.add_argument("command", nargs='?', help="SECRET_NAME to add, or 'list' to show all secrets")
    parser.add_argument("value", nargs='?', help="Secret value (required when adding a secret)")

    args = parser.parse_args()

    try:
        if args.command == "list":
            asyncio.run(list_secrets_in_formation(args.formation_path))
        elif args.command and args.value:
            asyncio.run(add_secret_to_formation(args.formation_path, args.command, args.value))
        elif args.command and not args.value:
            print(f"❌ Error: Secret value required for '{args.command}'")
            print(f"\nUsage: {sys.argv[0]} <formation_path> <SECRET_NAME> <secret_value>")
            print(f"Example: {sys.argv[0]} examples/configs OPENAI_API_KEY 'sk-your-key-here'")
            sys.exit(1)
        else:
            print("🔐 MUXI Secrets Management - Add Secret")
            print("\nUsage:")
            print(f"  {sys.argv[0]} <formation_path> <SECRET_NAME> <secret_value>")
            print(f"  {sys.argv[0]} <formation_path> list")
            print("\nExamples:")
            print(f"  {sys.argv[0]} examples/configs OPENAI_API_KEY 'sk-your-key-here'")
            print(f"  {sys.argv[0]} formation.yaml WEATHER_API_KEY 'your-weather-key'")
            print(f"  {sys.argv[0]} examples/configs list")
            print("\nFor more help: python -m argparse --help")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
