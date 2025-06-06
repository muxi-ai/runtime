"""
Tests for overlord configuration with new schema format.
"""
import pytest
import tempfile
import os
import sys
import yaml
from unittest.mock import MagicMock, patch

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from muxi.runtime.overlord import Overlord
from muxi.runtime.config.validation import FormationValidator


class TestOverlordNewSchema:
    """Test overlord functionality with new schema configuration."""

    @pytest.fixture
    def new_schema_formation(self):
        """Formation config using the new schema format."""
        return {
            'schema': '1.0.0',
            'id': 'overlord-test-formation',
            'description': 'Test formation for overlord new schema testing',
            'system_message': 'You are an orchestrator for routing messages.',

            # LLM configuration
            'llm': {
                'settings': {
                    'temperature': 0.7,
                    'max_tokens': 1000,
                    'timeout_seconds': 30
                },
                'api_keys': {
                    'openai': '${{ secrets.OPENAI_API_KEY }}'
                },
                'models': [
                    {
                        'text': 'openai/gpt-4o',
                        'settings': {
                            'temperature': 0.7,
                            'max_tokens': 1000
                        }
                    },
                    {
                        'vision': 'openai/gpt-4o',
                        'settings': {
                            'temperature': 0.5,
                            'max_tokens': 1500
                        }
                    }
                ]
            },

            # New overlord configuration
            'overlord': {
                'system_message': 'You are the MUXI Overlord routing messages.',
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
                    'caching': {
                        'enabled': True,
                        'ttl': 3600
                    },
                    'max_tool_calls': -1,
                    'response_format': 'markdown'
                }
            },

            'agents': [
                {
                    'schema': '1.0.0',
                    'id': 'test-agent',
                    'name': 'Test Agent',
                    'description': 'A test agent for overlord validation',
                    'system_message': 'You are a helpful test agent.',
                    'llm_models': [
                        {
                            'text': 'openai/gpt-4o',
                            'settings': {
                                'temperature': 0.8
                            }
                        }
                    ]
                }
            ],

            'mcp': {
                'default_retry_attempts': 3,
                'default_timeout_seconds': 30,
                'servers': []
            }
        }

    @pytest.fixture
    def legacy_overlord_formation(self):
        """Formation config using legacy overlord.routing format."""
        return {
            'schema': '1.0.0',
            'id': 'legacy-overlord-formation',
            'description': 'Test formation with legacy overlord routing config',

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
            },

            'agents': []
        }

    @pytest.fixture
    def temp_formation_file(self, new_schema_formation):
        """Create temporary formation file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(new_schema_formation, f)
            formation_path = f.name

        yield formation_path
        os.unlink(formation_path)

    @pytest.fixture
    def temp_legacy_formation(self, legacy_overlord_formation):
        """Create temporary legacy formation file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(legacy_overlord_formation, f)
            formation_path = f.name

        yield formation_path
        os.unlink(formation_path)

    def test_new_overlord_schema_validation(self, temp_formation_file):
        """Test validation of new overlord schema."""
        validator = FormationValidator()
        result = validator.validate(temp_formation_file)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_legacy_overlord_schema_validation(self, temp_legacy_formation):
        """Test validation of legacy overlord schema."""
        validator = FormationValidator()
        result = validator.validate(temp_legacy_formation)

        assert result.is_valid
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    @patch('runtime.muxi.runtime.overlord.Overlord.create_model')
    async def test_overlord_initialization_new_schema(self, mock_create_model,
                                                     new_schema_formation):
        """Test overlord initialization with new schema."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()
        overlord.formation_config = new_schema_formation

        # Test routing model initialization
        overlord._initialize_routing_model()

        # Verify new schema configuration was loaded
        assert overlord.routing_cache_enabled is True
        assert overlord.routing_cache_ttl == 3600
        assert overlord.max_extraction_tokens == 500
        assert overlord.max_tool_calls == -1
        assert overlord.response_format == 'markdown'
        assert overlord.routing_system_message == 'You are the MUXI Overlord routing messages.'

    @pytest.mark.asyncio
    @patch('runtime.muxi.runtime.overlord.Overlord.create_model')
    async def test_overlord_initialization_legacy_schema(self, mock_create_model,
                                                        legacy_overlord_formation):
        """Test overlord initialization with legacy schema."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()
        overlord.formation_config = legacy_overlord_formation

        # Test routing model initialization
        overlord._initialize_routing_model()

        # Verify legacy schema configuration was loaded with defaults
        assert overlord.routing_cache_enabled is False
        assert overlord.routing_cache_ttl == 7200
        assert overlord.max_extraction_tokens == 500  # Default
        assert overlord.max_tool_calls == -1  # Default
        assert overlord.response_format == 'markdown'  # Default
        assert overlord.routing_system_message == 'Legacy system message'

    @pytest.mark.asyncio
    @patch('muxi.runtime.overlord.Overlord.create_model')
    async def test_overlord_initialization_no_config(self, mock_create_model):
        """Test overlord initialization with no overlord config."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()
        overlord.formation_config = {
            'schema': '1.0.0',
            'id': 'minimal-formation',
            'description': 'Minimal formation'
        }

        # Test routing model initialization
        overlord._initialize_routing_model()

        # Verify default configuration
        assert overlord.routing_cache_enabled is True
        assert overlord.routing_cache_ttl == 3600
        assert overlord.max_extraction_tokens == 500
        assert overlord.max_tool_calls == -1
        assert overlord.response_format == 'markdown'
        assert overlord.routing_system_message is None

    def test_system_prompt_loading(self):
        """Test system prompt loading from file."""
        overlord = Overlord()

        # The _load_default_system_prompt should be called during init
        assert hasattr(overlord, '_default_system_prompt')
        assert overlord._default_system_prompt is not None
        assert len(overlord._default_system_prompt) > 0

    @pytest.mark.asyncio
    @patch('muxi.runtime.overlord.Overlord.create_model')
    async def test_llm_configuration_loading(self, mock_create_model, new_schema_formation):
        """Test LLM configuration loading with new schema."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()
        overlord.formation_config = new_schema_formation

        # Initialize LLM configuration
        await overlord._initialize_llm_config()

        # Check that capability models were set up
        assert hasattr(overlord, '_capability_models')
        assert 'text' in overlord._capability_models
        assert 'vision' in overlord._capability_models

        # Check global settings and API keys
        assert hasattr(overlord, '_global_llm_settings')
        assert hasattr(overlord, '_global_api_keys')
        assert overlord._global_llm_settings['temperature'] == 0.7
        assert overlord._global_api_keys['openai'] == '${{ secrets.OPENAI_API_KEY }}'

    @pytest.mark.asyncio
    @patch('muxi.runtime.overlord.Overlord.create_model')
    async def test_capability_model_resolution(self, mock_create_model, new_schema_formation):
        """Test model resolution by capability."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()
        overlord.formation_config = new_schema_formation

        # Initialize LLM configuration
        await overlord._initialize_llm_config()

        # Test capability model resolution
        text_model = await overlord.get_model_for_capability('text')
        vision_model = await overlord.get_model_for_capability('vision')

        assert text_model is not None
        assert vision_model is not None

    def test_routing_prompt_creation_with_timestamp(self):
        """Test that routing prompt includes timestamp."""
        overlord = Overlord()

        # Mock the default system prompt
        overlord._default_system_prompt = "Test system prompt"

        test_message = "Test user message"
        prompt = overlord._create_routing_prompt(test_message)

        # Check that timestamp is included
        assert "Today is" in prompt
        # Check that both default prompt and message are included
        assert "Test system prompt" in prompt
        assert test_message in prompt

    def test_routing_prompt_with_custom_system_message(self):
        """Test routing prompt with custom system message."""
        overlord = Overlord()
        overlord._default_system_prompt = "Default prompt"
        overlord.routing_system_message = "Custom routing message"

        test_message = "Test user message"
        prompt = overlord._create_routing_prompt(test_message)

        # Check that both default and custom messages are included
        assert "Default prompt" in prompt
        assert "Custom routing message" in prompt
        assert test_message in prompt


if __name__ == "__main__":
    pytest.main([__file__])
