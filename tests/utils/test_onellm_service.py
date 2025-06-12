#!/usr/bin/env python3
"""
Basic test for OneLLMService to verify implementation.
This is a simple verification script, not a full test suite.
"""

import asyncio
import os
import sys
import traceback

# Add the runtime directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Mock the OneLLM imports for testing
class MockChatCompletion:
    @staticmethod
    def create(**kwargs):
        return {"choices": [{"message": {"content": "Mock response"}}]}


class MockEmbedding:
    @staticmethod
    def create(**kwargs):
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}


# Patch the imports
sys.modules['onellm'] = type('MockModule', (), {
    'ChatCompletion': MockChatCompletion,
    'Embedding': MockEmbedding,
    'config': type('MockConfig', (), {'set_api_key': lambda *args: None})()
})()

from src.muxi.runtime.llm.service import OneLLMService  # noqa: E402


async def test_singleton():
    """Test that singleton pattern works correctly."""
    print("Testing singleton pattern...")

    service1 = await OneLLMService.get_instance()
    service2 = await OneLLMService.get_instance()

    assert service1 is service2, "Singleton pattern failed"
    print("✓ Singleton pattern working correctly")


async def test_api_key_management():
    """Test API key management."""
    print("Testing API key management...")

    service = await OneLLMService.get_instance()

    # Test setting and getting API keys
    service.set_api_key("openai", "test-key-123")
    assert service.get_api_key("openai") == "test-key-123"

    # Test non-existent provider
    assert service.get_api_key("nonexistent") is None

    print("✓ API key management working correctly")


async def test_model_parsing():
    """Test model string parsing."""
    print("Testing model parsing...")

    service = await OneLLMService.get_instance()

    # Test with provider/model format
    provider, model = service._parse_model("openai/gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"

    # Test with just model name (should default to openai)
    provider, model = service._parse_model("gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"

    print("✓ Model parsing working correctly")


async def test_stats():
    """Test statistics tracking."""
    print("Testing statistics...")

    service = await OneLLMService.get_instance()

    # Get initial stats
    stats = service.get_stats()
    assert isinstance(stats, dict)
    assert 'total_requests' in stats

    # Reset stats
    service.reset_stats()
    stats = service.get_stats()
    assert stats['total_requests'] == 0

    print("✓ Statistics working correctly")


async def main():
    """Run all tests."""
    print("Running OneLLMService tests...\n")

    try:
        await test_singleton()
        await test_api_key_management()
        await test_model_parsing()
        await test_stats()

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
