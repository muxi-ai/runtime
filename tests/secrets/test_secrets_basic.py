#!/usr/bin/env python3
"""
Basic test script for SecretsManager functionality.
"""

import asyncio
import tempfile
import shutil
from pathlib import Path

from src.muxi.runtime.secrets import SecretsManager


async def test_basic_functionality():
    """Test basic SecretsManager functionality."""
    print("🧪 Testing SecretsManager...")

    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp())
    print(f"📁 Using temp directory: {temp_dir}")

    try:
        # Initialize manager
        manager = SecretsManager(temp_dir)
        await manager.initialize_encryption()
        print("✅ Initialization successful!")

        # Test storage and retrieval
        await manager.store_secret('test_key', 'test_value')
        value = await manager.get_secret('test_key')
        assert value == 'test_value'
        print("✅ Basic storage/retrieval works!")

        # Test case-insensitive access
        value2 = await manager.get_secret('TEST_KEY')
        assert value2 == 'test_value'
        print("✅ Case-insensitive access works!")

        # Test interpolation
        result = await manager.interpolate_secrets('${{ secrets.TEST_KEY }}')
        assert result == 'test_value'
        print("✅ Full interpolation works!")

        # Test partial interpolation
        template = "postgres://user:${{ secrets.TEST_KEY }}@localhost/db"
        result = await manager.interpolate_secrets(template)
        expected = "postgres://user:test_value@localhost/db"
        assert result == expected
        print("✅ Partial interpolation works!")

        # Test name normalization
        normalized = manager._normalize_secret_name('openai-api-key')
        assert normalized == 'OPENAI_API_KEY'
        print("✅ Name normalization works!")

        # Test whitespace tolerance
        await manager.store_secret('api_key', 'sk-123456')
        test_cases = [
            '${{ secrets.API_KEY }}',
            '${{secrets.API_KEY}}',
            '${{ secrets.API_KEY}}',
            '${{secrets.API_KEY }}',
        ]

        for template in test_cases:
            result = await manager.interpolate_secrets(template)
            assert result == 'sk-123456'
        print("✅ Whitespace tolerance works!")

        # Test nested data interpolation
        config = {
            "database": {
                "url": "${{ secrets.TEST_KEY }}",
                "timeout": 30
            },
            "static": "no_change"
        }

        result = await manager.interpolate_secrets(config)
        expected = {
            "database": {
                "url": "test_value",
                "timeout": 30
            },
            "static": "no_change"
        }
        assert result == expected
        print("✅ Nested data interpolation works!")

        print("🎉 All tests passed! SecretsManager is working correctly!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
        print("🧹 Cleaned up temp directory")


if __name__ == "__main__":
    asyncio.run(test_basic_functionality())
