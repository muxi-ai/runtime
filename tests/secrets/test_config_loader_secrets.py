#!/usr/bin/env python3
"""Test the updated ConfigLoader with secrets integration."""

import asyncio
import tempfile
import json
from pathlib import Path

from src.muxi.runtime.config.loader import ConfigLoader
from src.muxi.runtime.secrets import SecretsManager


async def test_config_loader_secrets():
    """Test ConfigLoader with secrets integration."""

    # Create temporary formation directory
    temp_dir = Path(tempfile.mkdtemp())
    formation_dir = temp_dir / "test_formation"
    formation_dir.mkdir()

    try:
        print(f"🧪 Testing ConfigLoader with secrets in: {formation_dir}")

        # Initialize SecretsManager and store a test secret
        secrets_manager = SecretsManager(formation_dir)
        await secrets_manager.initialize_encryption()
        await secrets_manager.store_secret("OPENAI_API_KEY", "sk-test123456789")
        await secrets_manager.store_secret("WEATHER_API_KEY", "weather-secret-key")

        # Create a test config file with new secrets syntax
        config_file = formation_dir / "test_config.json"
        test_config = {
            "name": "test_agent",
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "${{ secrets.OPENAI_API_KEY }}"
            },
            "mcp_servers": [
                {
                    "name": "weather",
                    "url": "http://localhost:5001",
                    "credentials": {
                        "api_key": "${{ secrets.WEATHER_API_KEY }}"
                    }
                }
            ],
            "memory": {
                "buffer_size": 10
            }
        }

        with open(config_file, 'w') as f:
            json.dump(test_config, f, indent=2)

        print("✅ Created test config with secrets syntax")

        # Load and process the config
        loader = ConfigLoader()
        processed_config = await loader.load_and_process(str(config_file), secrets_manager)

        print("✅ Config loaded and processed successfully")

        # Verify secrets were interpolated
        assert processed_config["model"]["api_key"] == "sk-test123456789", \
            f"Expected 'sk-test123456789', got '{processed_config['model']['api_key']}'"

        mcp_creds = processed_config["mcp_servers"][0]["credentials"]["api_key"]
        assert mcp_creds == "weather-secret-key", \
            f"Expected 'weather-secret-key', got '{mcp_creds}'"

        print("✅ All secrets interpolated correctly!")

        # Test error handling for missing secret
        config_file_missing_secret = formation_dir / "test_config_missing.json"
        test_config_missing = {
            "name": "test_agent_missing",
            "model": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "${{ secrets.MISSING_SECRET }}"
            }
        }

        with open(config_file_missing_secret, 'w') as f:
            json.dump(test_config_missing, f, indent=2)

        try:
            await loader.load_and_process(str(config_file_missing_secret), secrets_manager)
            assert False, "Should have raised error for missing secret"
        except ValueError as e:
            assert "MISSING_SECRET" in str(e)
            print("✅ Error handling for missing secrets works correctly")

        print("\n🎉 All tests passed! ConfigLoader secrets integration working perfectly.")

    finally:
        import shutil
        shutil.rmtree(temp_dir)
        print("🧹 Cleaned up test directory")


if __name__ == "__main__":
    asyncio.run(test_config_loader_secrets())
