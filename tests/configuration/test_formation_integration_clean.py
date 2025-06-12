"""
Tests for FormationLoader integration with Overlord and validation tools.
"""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, patch

from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.config.validation import ValidationResult, FormationValidator


class TestFormationIntegration:
    """Test FormationLoader integration with Overlord and validation tools."""

    @pytest.fixture
    def sample_formation_config(self):
        """Sample formation configuration for testing."""
        return {
            'name': 'test-formation',
            'version': '1.0.0',
            'description': 'Test formation for integration testing',
            'agents': [
                {
                    'agent_id': 'test-agent',
                    'model': {
                        'provider': 'openai',
                        'model': 'gpt-4',
                        'temperature': 0.7
                    },
                    'system_message': 'You are a helpful test agent.',
                    'description': 'A test agent for validation'
                }
            ],
            'mcp': {
                'servers': [
                    {
                        'id': 'test-mcp',
                        'url': 'http://localhost:8000'
                    }
                ]
            }
        }

    @pytest.fixture
    def temp_formation_file(self, sample_formation_config):
        """Create a temporary formation file for testing."""
        import yaml

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(sample_formation_config, f)
            formation_path = f.name

        yield formation_path

        # Cleanup
        os.unlink(formation_path)

    def test_formation_validator_basic(self, temp_formation_file):
        """Test basic formation validation functionality."""
        validator = FormationValidator()
        result = validator.validate(temp_formation_file)

        assert isinstance(result, ValidationResult)
        assert result.is_valid
        assert len(result.errors) == 0
        assert "✅ Formation configuration is valid" in result.summary()

    @pytest.mark.asyncio
    async def test_overlord_validate_formation(self, temp_formation_file):
        """Test Overlord's formation validation method."""
        overlord = Overlord()

        validation_result = await overlord.validate_formation(temp_formation_file)

        assert validation_result['is_valid']
        assert len(validation_result['errors']) == 0
        assert "✅ Formation configuration is valid" in validation_result['summary']

    @pytest.mark.asyncio
    @patch('src.muxi.runtime.overlord.Overlord.create_model')
    async def test_overlord_load_formation_from_path(self, mock_create_model, temp_formation_file):
        """Test Overlord loading formation from path."""
        # Mock the model creation
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()

        # Mock the agent creation to avoid actual LLM calls
        with patch.object(overlord, 'create_agent'), \
             patch.object(overlord, 'register_mcp_server'):

            formation_config = await overlord.load_formation_from_path(temp_formation_file)

            # Verify formation was loaded
            assert formation_config['name'] == 'test-formation'
            assert formation_config['version'] == '1.0.0'

            # Verify overlord's config was updated
            assert overlord.formation_config == formation_config


if __name__ == "__main__":
    pytest.main([__file__])
