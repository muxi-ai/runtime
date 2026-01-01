#!/usr/bin/env python3
"""
Debug script to print formation configuration
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.muxi.formation.formation import Formation  # noqa: E402


async def debug_formation_config():
    """Load formation and print configuration."""
    print("\n" + "=" * 80)
    print("FORMATION CONFIGURATION DEBUG")
    print("=" * 80)

    formation_path = Path(__file__).parent / "formations" / "formation-synopsis"

    print(f"\nFormation path: {formation_path}")
    print(f"Formation exists: {formation_path.exists()}")

    # Check secrets file
    secrets_file = formation_path / "secrets.enc"
    print(f"Secrets file exists: {secrets_file.exists()}")

    try:
        # Just load the raw YAML and secrets without starting overlord
        print("\n[1] Loading raw formation YAML...")
        import yaml
        formation_yaml = formation_path / "formation.afs"

        with open(formation_yaml, 'r') as f:
            config = yaml.safe_load(f)

        print("[2] Checking memory configuration in YAML...")
        memory_config = config.get('memory', {})
        persistent_config = memory_config.get('persistent', {})

        # Print connection string from YAML
        connection_string_raw = persistent_config.get('connection_string', 'NOT FOUND')
        print(f"\n📌 Connection string in YAML (raw): {connection_string_raw}")

        # Now decrypt secrets and check
        print("\n[3] Decrypting secrets...")
        from muxi.runtime.services.secrets.secrets_manager import SecretsManager
        secrets_obj = SecretsManager(str(formation_path))

        # Get POSTGRES_URI specifically
        postgres_uri = secrets_obj.get_secret_sync('POSTGRES_URI')
        print(f"\n📌 POSTGRES_URI from secrets: {postgres_uri}")

        # Get all secret names
        all_secret_names = secrets_obj.get_all_secret_names()
        print(f"\nAll secret names: {sorted(all_secret_names)}")

        # Get database-related secrets
        db_secrets = {name: secrets_obj.get_secret_sync(name) for name in all_secret_names if 'POSTGRES' in name.upper() or 'DATABASE' in name.upper()}
        if db_secrets:
            print("\n📌 All database-related secrets:")
            for key, value in db_secrets.items():
                print(f"   {key}: {value}")


        # Check environment variables
        print("\n" + "-" * 80)
        print("ENVIRONMENT VARIABLES")
        print("-" * 80)
        import os
        print(f"\nPOSTGRES_DATABASE_URL: {os.getenv('POSTGRES_DATABASE_URL', 'NOT SET')}")
        print(f"SQLITE_DATABASE_PATH: {os.getenv('SQLITE_DATABASE_PATH', 'NOT SET')}")

        print("\n" + "=" * 80)
        print("✅ Formation loaded successfully")
        print("=" * 80)

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ ERROR: {type(e).__name__}")
        print("=" * 80)
        print(f"\n{str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_formation_config())
