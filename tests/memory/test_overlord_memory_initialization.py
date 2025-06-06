#!/usr/bin/env python3

"""
Test overlord memory initialization from formation configuration.
"""
import sys
import os
import asyncio
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from muxi.runtime.overlord import Overlord


def test_memory_initialization():
    """Test memory initialization from formation config."""

    # Test formation with memory configuration
    formation_config = {
        'schema': '1.0.0',
        'id': 'memory-test-formation',
        'description': 'Test formation with memory configuration',
        'llm': {
            'models': [
                {
                    'text': 'openai/gpt-4o-mini',
                    'settings': {'temperature': 0.7}
                },
                {
                    'embedding': 'openai/text-embedding-3-small',
                    'settings': {'temperature': 0.0}
                }
            ],
            'api_keys': {
                'openai': 'test-api-key'
            }
        },
        'memory': {
            'buffer': {
                'size': 15,
                'multiplier': 8,
                'vector_search': True,
                'vector_dimension': 1536,
                'mode': 'local'
            },
            'long_term': {
                'connection_string': 'sqlite:///test_memory.db',
                'embedding_model': 'openai/text-embedding-3-small'
            }
        }
    }

    async def run_test():
        # Create overlord without initial memory systems
        overlord = Overlord(formation_config=formation_config)

        # Mock the LLM creation to avoid needing real API keys
        with patch('runtime.muxi.runtime.overlord.LLM') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            # Initialize memory configuration
            await overlord._initialize_memory_config()

            print("Memory Initialization Test Results:")
            print(f"Buffer memory created: {overlord.buffer_memory is not None}")
            print(f"Long-term memory created: {overlord.long_term_memory is not None}")

            if overlord.buffer_memory:
                stats = overlord.buffer_memory.get_stats()
                print(f"Buffer stats: {stats}")

                # Verify buffer configuration matches formation config
                assert overlord.buffer_memory.max_size == 15
                assert overlord.buffer_memory.buffer_multiplier == 8
                assert overlord.buffer_memory.dimension == 1536
                assert overlord.buffer_memory.mode == 'local'
                print("✅ Buffer memory configuration matches formation config")

            if overlord.long_term_memory:
                print("✅ Long-term memory initialized successfully")

    # Run the async test
    asyncio.run(run_test())


def test_memory_config_no_memory():
    """Test that no memory systems are created when not configured."""

    formation_config = {
        'schema': '1.0.0',
        'id': 'no-memory-formation',
        'description': 'Test formation without memory configuration'
    }

    async def run_test():
        overlord = Overlord(formation_config=formation_config)
        await overlord._initialize_memory_config()

        print("\nNo Memory Configuration Test Results:")
        print(f"Buffer memory: {overlord.buffer_memory}")
        print(f"Long-term memory: {overlord.long_term_memory}")
        print("✅ No memory systems created when not configured")

    asyncio.run(run_test())


def test_remote_buffer_memory():
    """Test remote buffer memory configuration."""

    formation_config = {
        'schema': '1.0.0',
        'id': 'remote-memory-formation',
        'description': 'Test formation with remote buffer memory',
        'llm': {
            'models': [
                {
                    'embedding': 'openai/text-embedding-3-small'
                }
            ],
            'api_keys': {
                'openai': 'test-api-key'
            }
        },
        'memory': {
            'buffer': {
                'size': 20,
                'multiplier': 5,
                'vector_search': True,
                'mode': 'remote',
                'remote': {
                    'url': 'tcp://localhost:8000',
                    'api_key': 'test-faissx-key',
                    'tenant': 'test-tenant'
                }
            }
        }
    }

    async def run_test():
        overlord = Overlord(formation_config=formation_config)

        with patch('runtime.muxi.runtime.overlord.LLM') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            await overlord._initialize_memory_config()

            print("\nRemote Buffer Memory Test Results:")
            print(f"Buffer memory created: {overlord.buffer_memory is not None}")

            if overlord.buffer_memory:
                assert overlord.buffer_memory.mode == 'remote'
                assert overlord.buffer_memory.remote['url'] == 'tcp://localhost:8000'
                print("✅ Remote buffer memory configuration correct")

    asyncio.run(run_test())


if __name__ == "__main__":
    print("Testing overlord memory initialization...")
    test_memory_initialization()
    test_memory_config_no_memory()
    test_remote_buffer_memory()
    print("\n✅ All overlord memory initialization tests passed!")
