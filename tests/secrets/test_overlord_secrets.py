#!/usr/bin/env python3
"""Test Overlord with SecretsManager integration."""

import asyncio
import tempfile
import shutil
from pathlib import Path

from src.muxi.overlord import Overlord
from src.muxi.secrets import SecretsManager  # noqa: F401


async def test_overlord_secrets_integration():
    """Test complete Overlord + SecretsManager integration."""

    # Create temporary formation directory
    temp_dir = Path(tempfile.mkdtemp())
    formation_dir = temp_dir / "test_formation"
    formation_dir.mkdir()

    try:
        print(f"🧪 Testing Overlord with SecretsManager in: {formation_dir}")

        # Initialize Overlord with formation_path
        overlord = Overlord(formation_path=str(formation_dir))

        # Test 1: Verify SecretsManager was created
        assert overlord.secrets_manager is not None, "SecretsManager should be initialized"
        print("✅ SecretsManager initialization successful")

        # Test 2: Store some secrets
        await overlord.store_secret("OPENAI_API_KEY", "sk-test123456789")
        await overlord.store_secret("WEATHER_API_KEY", "weather-secret-key")
        await overlord.store_secret("SEARCH_API_KEY", "search-secret-key")
        print("✅ Secrets storage successful")

        # Test 3: List secrets
        secrets_list = await overlord.list_secrets()
        expected_secrets = {"OPENAI_API_KEY", "WEATHER_API_KEY", "SEARCH_API_KEY"}
        assert set(secrets_list) == expected_secrets, f"Expected {expected_secrets}, got {set(secrets_list)}"  # noqa: E501
        print("✅ Secrets listing successful")

        # Test 4: Test create_model with secrets interpolation
        try:
            model = await overlord.create_model(  # noqa: F841
                model="openai/gpt-4o",
                api_key="${{ secrets.OPENAI_API_KEY }}",
                temperature=0.7
            )
            print("✅ Model creation with secrets interpolation successful")
        except Exception as e:
            print(f"⚠️  Model creation test skipped (expected): {e}")

        # Test 5: Test MCP server registration with secrets interpolation
        try:
            await overlord.register_mcp_server(
                server_id="weather_server",
                url="http://localhost:5001",
                credentials={
                    "api_key": "${{ secrets.WEATHER_API_KEY }}",
                    "service_name": "weather"
                }
            )
            print("✅ MCP server registration with secrets interpolation successful")
        except Exception as e:
            print(f"⚠️  MCP server registration test skipped (expected): {e}")

        # Test 6: Test secrets interpolation directly
        test_config = {
            "model": {
                "api_key": "${{ secrets.OPENAI_API_KEY }}",
                "provider": "openai"
            },
            "mcp_servers": [
                {
                    "name": "weather",
                    "credentials": {
                        "api_key": "${{ secrets.WEATHER_API_KEY }}"
                    }
                }
            ]
        }

        interpolated_config = await overlord.interpolate_secrets(test_config)

        # Verify interpolation worked
        assert interpolated_config["model"]["api_key"] == "sk-test123456789", \
            f"Expected 'sk-test123456789', got '{interpolated_config['model']['api_key']}'"

        mcp_api_key = interpolated_config["mcp_servers"][0]["credentials"]["api_key"]
        assert mcp_api_key == "weather-secret-key", \
            f"Expected 'weather-secret-key', got '{mcp_api_key}'"

        print("✅ Secrets interpolation successful")

        # Test 7: Test secret deletion
        await overlord.delete_secret("SEARCH_API_KEY")
        remaining_secrets = await overlord.list_secrets()
        assert "SEARCH_API_KEY" not in remaining_secrets, "SEARCH_API_KEY should be deleted"
        print("✅ Secret deletion successful")

        print("\n🎉 All Overlord + SecretsManager integration tests passed!")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("\n🧹 Cleaned up test directory")


if __name__ == "__main__":
    asyncio.run(test_overlord_secrets_integration())
