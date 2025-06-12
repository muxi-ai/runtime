#!/usr/bin/env python3
"""Quick test for OneLLMService"""

import asyncio
import os
import sys

# Add the runtime directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import errors from the proper module path
from src.muxi.runtime.llm.errors import (  # noqa: E402
    OneLLMConnectionError,
    OneLLMAuthenticationError,
    OneLLMRateLimitError,
    OneLLMTimeoutError,
    OneLLMServiceError,
)


# Mock onellm for testing
class MockResponse:
    def __init__(self, content):
        self.choices = [type('Choice', (), {'message': {'content': content}})()]


class MockChatCompletion:
    @staticmethod
    def create(**kwargs):
        return MockResponse('Mock response')


class MockEmbedding:
    @staticmethod
    def create(**kwargs):
        return type('EmbedResponse', (), {
            'data': [type('EmbedData', (), {'embedding': [0.1, 0.2, 0.3]})()]
        })()


# Mock the onellm module
sys.modules['onellm'] = type('MockModule', (), {
    'ChatCompletion': MockChatCompletion,
    'Embedding': MockEmbedding,
    'set_api_key': lambda *args: None
})()

# Import the service module and patch it
from src.muxi.runtime.llm import service  # noqa: E402

service.OneLLMConnectionError = OneLLMConnectionError
service.OneLLMAuthenticationError = OneLLMAuthenticationError
service.OneLLMRateLimitError = OneLLMRateLimitError
service.OneLLMTimeoutError = OneLLMTimeoutError
service.OneLLMServiceError = OneLLMServiceError

from src.muxi.runtime.llm.service import OneLLMService  # noqa: E402


async def test():
    """Run quick tests for OneLLMService."""
    service_instance = await OneLLMService.get_instance()
    print('✓ OneLLMService singleton created successfully')

    # Test API key management
    service_instance.set_api_key('openai', 'test-key')
    assert service_instance.get_api_key('openai') == 'test-key'
    print('✓ API key management working')

    # Test model parsing
    provider, model = service_instance._parse_model('openai/gpt-4o')
    assert provider == 'openai' and model == 'gpt-4o'
    print('✓ Model parsing working')

    # Test stats
    stats = service_instance.get_stats()
    assert isinstance(stats, dict)
    print('✓ Statistics working')

    print('\n✅ All basic tests passed!')


if __name__ == "__main__":
    asyncio.run(test())
