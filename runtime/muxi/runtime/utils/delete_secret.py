#!/usr/bin/env python3
"""
Delete Secret - MUXI Runtime Utility

Tool for deleting secrets from a formation's encrypted secrets store.
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


async def delete_secret_from_formation(formation_path: str, secret_name: str):
    """Delete a secret from the formation's secrets store."""
    if formation_path.endswith('.yaml'):
        formation_dir = Path(formation_path).parent
    else:
        formation_dir = Path(formation_path)

    print(f"🗑️  Deleting secret '{secret_name}' from formation...")
    print(f"📁 Formation directory: {formation_dir}")

    # Initialize SecretsManager
    secrets_manager = SecretsManager(formation_dir)
    await secrets_manager.initialize_encryption()

    # Check if secret exists
    secrets = await secrets_manager.list_secrets()
    if secret_name not in secrets:
        print(f"❌ Secret '{secret_name}' not found!")
        print(f"📋 Available secrets: {', '.join(secrets) if secrets else '(none)'}")
        return False

    # Delete the secret
    await secrets_manager.delete_secret(secret_name)

    print(f"✅ Secret '{secret_name}' deleted successfully!")

    # Show remaining secrets
    remaining_secrets = await secrets_manager.list_secrets()
    print(f"📋 Remaining secrets: {', '.join(remaining_secrets) if remaining_secrets else '(none)'}")

    return True


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
        print("🗑️  MUXI Secrets Management - Delete Secret")
        print("\nUsage:")
        print(f"  {sys.argv[0]} <formation_path> <SECRET_NAME>")
        print(f"  {sys.argv[0]} <formation_path> list")
        print("\nExamples:")
        print(f"  {sys.argv[0]} examples/configs OPENAI_API_KEY")
        print(f"  {sys.argv[0]} formation.yaml WEATHER_API_KEY")
        print(f"  {sys.argv[0]} examples/configs list")
        print(f"\nFor detailed help: {sys.argv[0]} --help")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Delete secrets from MUXI Formation",
        epilog="""
Examples:
  %(prog)s examples/configs OPENAI_API_KEY
  %(prog)s formation.yaml WEATHER_API_KEY
  %(prog)s examples/configs list
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("formation_path", help="Path to formation directory or YAML file")
    parser.add_argument("command", nargs='?', help="SECRET_NAME to delete, or 'list' to show all secrets")

    args = parser.parse_args()

    try:
        if args.command == "list":
            asyncio.run(list_secrets_in_formation(args.formation_path))
        elif args.command:
            asyncio.run(delete_secret_from_formation(args.formation_path, args.command))
        else:
            print("🗑️  MUXI Secrets Management - Delete Secret")
            print("\nUsage:")
            print(f"  {sys.argv[0]} <formation_path> <SECRET_NAME>")
            print(f"  {sys.argv[0]} <formation_path> list")
            print("\nExamples:")
            print(f"  {sys.argv[0]} examples/configs OPENAI_API_KEY")
            print(f"  {sys.argv[0]} formation.yaml WEATHER_API_KEY")
            print(f"  {sys.argv[0]} examples/configs list")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
