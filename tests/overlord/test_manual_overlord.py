#!/usr/bin/env python3
"""
Manual test script for new overlord schema functionality.
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.muxi.overlord import Overlord


def test_new_overlord_schema():
    """Test new overlord schema configuration."""

    # Test new schema formation
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'overlord': {
            'persona': 'Test overlord persona',
            'llm': {
                'model': 'openai/gpt-4o-mini',
                'settings': {
                    'temperature': 0.2,
                    'max_tokens': 2000,
                    'timeout_seconds': 45
                }
            },
            'config': {
                'max_extraction_tokens': 500,
                'caching': {'enabled': True, 'ttl': 3600},
                'max_tool_calls': -1,
                'response_format': 'markdown'
            }
        }
    }

    overlord = Overlord()
    overlord.formation_config = formation
    overlord._initialize_routing_model()

    print('✅ New overlord schema test passed')
    print(f'- Cache enabled: {overlord.routing_cache_enabled}')
    print(f'- Cache TTL: {overlord.routing_cache_ttl}')
    print(f'- Max extraction tokens: {overlord.max_extraction_tokens}')
    print(f'- Max tool calls: {overlord.max_tool_calls}')
    print(f'- Response format: {overlord.response_format}')
    print(f'- Persona: {overlord.routing_persona}')

    # Verify all expected attributes exist
    assert hasattr(overlord, 'routing_cache_enabled')
    assert hasattr(overlord, 'routing_cache_ttl')
    assert hasattr(overlord, 'max_extraction_tokens')
    assert hasattr(overlord, 'max_tool_calls')
    assert hasattr(overlord, 'response_format')
    assert hasattr(overlord, 'routing_persona')

    # Verify values
    assert overlord.routing_cache_enabled is True
    assert overlord.routing_cache_ttl == 3600
    assert overlord.max_extraction_tokens == 500
    assert overlord.max_tool_calls == -1
    assert overlord.response_format == 'markdown'
    assert overlord.routing_persona == 'Test overlord persona'

    print('✅ All assertions passed!')


def test_legacy_overlord_schema():
    """Test legacy overlord schema configuration."""

    formation = {
        'schema': '1.0.0',
        'id': 'legacy-formation',
        'description': 'Legacy formation',
        'overlord': {
            'routing': {
                'model': 'openai/gpt-4o-mini',
                'settings': {
                    'temperature': 0.3,
                    'max_tokens': 1500
                },
                'use_caching': False,
                'cache_ttl': 7200,
                'system_message': 'Legacy system message'
            }
        }
    }

    overlord = Overlord()
    overlord.formation_config = formation
    overlord._initialize_routing_model()

    print('✅ Legacy overlord schema test passed')
    print(f'- Cache enabled: {overlord.routing_cache_enabled}')
    print(f'- Cache TTL: {overlord.routing_cache_ttl}')
    print(f'- Persona: {overlord.routing_persona}')

    # Verify legacy configuration with defaults
    assert overlord.routing_cache_enabled is False
    assert overlord.routing_cache_ttl == 7200
    assert overlord.max_extraction_tokens == 500  # Default
    assert overlord.max_tool_calls == -1  # Default
    assert overlord.response_format == 'markdown'  # Default
    assert overlord.routing_persona == 'Legacy system message'

    print('✅ Legacy assertions passed!')


def test_persona_loading():
    """Test persona loading from file."""

    overlord = Overlord()

    # The _load_default_persona should be called during init
    assert hasattr(overlord, '_default_persona')
    assert overlord._default_persona is not None
    assert len(overlord._default_persona) > 0

    print('✅ Persona loading test passed')
    print(f'- Default persona length: {len(overlord._default_persona)} characters')


def test_routing_prompt_with_timestamp():
    """Test routing prompt includes timestamp."""

    overlord = Overlord()

    test_message = "Test user message"
    prompt = overlord._create_routing_prompt(test_message)

    # Check that timestamp is included
    assert "Today is" in prompt
    # Check that both technical instructions and message are included
    assert "overlord" in prompt.lower()
    assert test_message in prompt

    print('✅ Routing prompt with timestamp test passed')
    print(f'- Prompt includes timestamp: {"Today is" in prompt}')


if __name__ == '__main__':
    print("Running manual overlord schema tests...\n")

    try:
        test_new_overlord_schema()
        print()

        test_legacy_overlord_schema()
        print()

        test_persona_loading()
        print()

        test_routing_prompt_with_timestamp()
        print()

        print("🎉 All manual tests passed successfully!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
