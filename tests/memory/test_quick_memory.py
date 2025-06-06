#!/usr/bin/env python3

import asyncio
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.append('.')
from muxi.runtime.overlord import Overlord

async def test_memory():
    formation_config = {
        'llm': {
            'models': [
                {'text': 'openai/gpt-4o-mini'},
                {'embedding': 'openai/text-embedding-3-small'}
            ],
            'api_keys': {
                'openai': 'test-key'
            }
        },
        'memory': {
            'long_term': {
                'connection_string': 'test_memory.db',
                'embedding_model': 'openai/text-embedding-3-small'
            }
        }
    }

    overlord = Overlord(formation_config=formation_config)

    with patch('runtime.muxi.runtime.overlord.LLM') as mock_llm_class:
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        await overlord._initialize_memory_config()

        print(f'Long-term memory initialized: {overlord.long_term_memory is not None}')
        if overlord.long_term_memory:
            print('✅ Long-term memory working!')
        else:
            print('❌ Long-term memory failed')

if __name__ == "__main__":
    asyncio.run(test_memory())
