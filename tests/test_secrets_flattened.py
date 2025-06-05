#!/usr/bin/env python3
"""Test the flattened SecretsManager implementation."""

import asyncio
import tempfile
import shutil
from pathlib import Path

from runtime.muxi.runtime.secrets import SecretsManager


async def test_flattened_secrets():
    """Test flattened SecretsManager functionality."""

    # Create temporary formation directory
    temp_dir = Path(tempfile.mkdtemp())
    formation_dir = temp_dir / "test_formation"
    formation_dir.mkdir()

    try:
        print(f"🧪 Testing SecretsManager in: {formation_dir}")

        # Initialize SecretsManager
        manager = SecretsManager(formation_dir)
        await manager.initialize_encryption()

        # Verify files are in formation root (not subdirectory)
        assert (formation_dir / ".key").exists(), "Master key should be in formation root"
        print("✅ Master key created in formation root")

        # Test basic secret storage
        await manager.store_secret("openai-api-key", "sk-test123")
        await manager.store_secret("database_url", "postgresql://localhost/test")

        # Verify secrets.enc is in formation root
        assert (formation_dir / "secrets.enc").exists(), "Secrets file should be in formation root"
        print("✅ Secrets file created in formation root")

        # Test retrieval
        api_key = await manager.get_secret("openai-api-key")
        assert api_key == "sk-test123", f"Expected 'sk-test123', got '{api_key}'"
        print("✅ Secret retrieval works")

        # Test normalization
        db_url = await manager.get_secret("DATABASE_URL")  # Different case
        assert db_url == "postgresql://localhost/test", "Normalization should work"
        print("✅ Secret name normalization works")

        # Test interpolation
        config = {
            "api_key": "${{ secrets.OPENAI_API_KEY }}",
            "database": "${{ secrets.DATABASE_URL }}"
        }

        interpolated = await manager.interpolate_secrets(config)
        expected = {
            "api_key": "sk-test123",
            "database": "postgresql://localhost/test"
        }
        assert interpolated == expected, f"Expected {expected}, got {interpolated}"
        print("✅ Secret interpolation works")

        # List secrets
        secret_names = await manager.list_secrets()
        assert set(secret_names) == {"OPENAI_API_KEY", "DATABASE_URL"}
        print("✅ Secret listing works")

        print("\n🎉 All tests passed! Flattened SecretsManager is working correctly.")

        # Show file structure
        print(f"\n📁 Final file structure in {formation_dir}:")
        for item in sorted(formation_dir.iterdir()):
            print(f"  - {item.name}")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("\n🧹 Cleaned up test directory")


if __name__ == "__main__":
    asyncio.run(test_flattened_secrets())
