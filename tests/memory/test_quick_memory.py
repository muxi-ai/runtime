#!/usr/bin/env python3

"""Quick memory test to verify proper functionality without hanging."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock

from muxi.runtime.overlord import Overlord


@pytest.mark.asyncio
async def test_memory():
    """Test memory initialization quickly."""

    formation_config = {
        'schema': '1.0.0',
        'id': 'quick-memory-test',
        'description': 'Quick memory test formation',
        'llm': {
            'models': [
                {
                    'text': 'openai/gpt-4o-mini',
                    'settings': {'temperature': 0.7}
                },
                {
                    'embedding': 'openai/text-embedding-3-small'
                }
            ],
            'api_keys': {
                'openai': 'test-api-key'
            }
        },
        'memory': {
            'long_term': {
                'connection_string': 'sqlite:///quick_test_memory.db'
            }
        }
    }

    overlord = Overlord(formation_config=formation_config)

    with patch('runtime.muxi.runtime.overlord.LLM') as mock_llm_class:
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        # Initialize LLM configuration FIRST
        await overlord._initialize_llm_config()

        # Then initialize memory configuration
        await overlord._initialize_memory_config()

        print(f'Long-term memory initialized: {overlord.long_term_memory is not None}')
        if overlord.long_term_memory:
            print('✅ Quick memory test passed!')
        else:
            print('❌ Memory not initialized')


if __name__ == "__main__":
    asyncio.run(test_memory())
