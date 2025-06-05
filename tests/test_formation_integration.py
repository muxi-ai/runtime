"""
Tests for FormationLoader integration with Overlord and validation tools.

This module tests the integration between the FormationLoader, validation tools,
and the Overlord to ensure formation configurations can be loaded properly.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime.muxi.runtime.overlord import Overlord
from runtime.muxi.runtime.config.validation import ValidationResult, FormationValidator


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

    @pytest.fixture
    def temp_modular_formation(self, sample_formation_config):
        """Create a temporary modular formation directory for testing."""
        import yaml

        with tempfile.TemporaryDirectory() as temp_dir:
            formation_dir = Path(temp_dir)

            # Create main formation.yaml
            main_config = {
                'name': sample_formation_config['name'],
                'version': sample_formation_config['version'],
                'description': sample_formation_config['description']
            }

            with open(formation_dir / 'formation.yaml', 'w') as f:
                yaml.dump(main_config, f)

            # Create agents directory and files
            agents_dir = formation_dir / 'agents'
            agents_dir.mkdir()

            for agent in sample_formation_config['agents']:
                agent_file = agents_dir / f"{agent['agent_id']}.yaml"
                with open(agent_file, 'w') as f:
                    yaml.dump(agent, f)

            # Create mcp directory and files
            mcp_dir = formation_dir / 'mcp'
            mcp_dir.mkdir()

            for server in sample_formation_config['mcp']['servers']:
                server_file = mcp_dir / f"{server['id']}.yaml"
                with open(server_file, 'w') as f:
                    yaml.dump(server, f)

            yield str(formation_dir)

    def test_formation_validator_basic(self, temp_formation_file):
        """Test basic formation validation functionality."""
        validator = FormationValidator()
        result = validator.validate(temp_formation_file)

        assert isinstance(result, ValidationResult)
        assert result.is_valid
        assert len(result.errors) == 0
        assert "✅ Formation configuration is valid" in result.summary()

    def test_formation_validator_modular(self, temp_modular_formation):
        """Test formation validation with modular formation."""
        validator = FormationValidator()
        result = validator.validate(temp_modular_formation)

        assert isinstance(result, ValidationResult)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_formation_validator_invalid_path(self):
        """Test formation validation with invalid path."""
        validator = FormationValidator()
        result = validator.validate("/nonexistent/path")

        assert isinstance(result, ValidationResult)
        assert not result.is_valid
        assert len(result.errors) > 0
        assert "does not exist" in result.errors[0]

    @pytest.mark.asyncio
    async def test_overlord_validate_formation(self, temp_formation_file):
        """Test Overlord's formation validation method."""
        overlord = Overlord()

        validation_result = await overlord.validate_formation(temp_formation_file)

        assert validation_result['is_valid']
        assert len(validation_result['errors']) == 0
        assert "✅ Formation configuration is valid" in validation_result['summary']

    @pytest.mark.asyncio
    async def test_overlord_validate_formation_invalid(self):
        """Test Overlord's formation validation with invalid formation."""
        overlord = Overlord()

        validation_result = await overlord.validate_formation("/nonexistent/path")

        assert not validation_result['is_valid']
        assert len(validation_result['errors']) > 0

    @pytest.mark.asyncio
    @patch('runtime.muxi.runtime.overlord.Overlord.create_model')
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

    @pytest.mark.asyncio
    @patch('runtime.muxi.runtime.overlord.Overlord.create_model')
    async def test_overlord_load_modular_formation(self, mock_create_model, temp_modular_formation):
        """Test Overlord loading modular formation."""
        # Mock the model creation
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        overlord = Overlord()

        # Mock the agent creation to avoid actual LLM calls
        with patch.object(overlord, 'create_agent'), \
             patch.object(overlord, 'register_mcp_server'):

            formation_config = await overlord.load_formation_from_path(temp_modular_formation)

            # Verify formation was loaded
            assert formation_config['name'] == 'test-formation'
            assert formation_config['version'] == '1.0.0'

            # Verify components were discovered and merged
            assert 'agents' in formation_config
            assert len(formation_config['agents']) == 1
            assert 'mcp' in formation_config
            assert 'servers' in formation_config['mcp']
            assert len(formation_config['mcp']['servers']) == 1

    @pytest.mark.asyncio
    async def test_overlord_load_formation_validation_failure(self):
        """Test Overlord handling of formation validation failures."""
        import tempfile
        import yaml

        # Create an invalid formation file
        invalid_config = {
            'name': 'test-formation',
            # Missing required 'version' field
            'agents': [
                {
                    # Missing required 'agent_id' field
                    'model': {
                        # Missing required 'provider' field
                        'model': 'gpt-4'
                    }
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_config, f)
            invalid_formation_path = f.name

        try:
            overlord = Overlord()

            # Should raise ValueError due to validation failure
            with pytest.raises(ValueError) as exc_info:
                await overlord.load_formation_from_path(invalid_formation_path)

            assert "Formation validation failed" in str(exc_info.value)

        finally:
            os.unlink(invalid_formation_path)

    def test_formation_validation_detailed_report(self):
        """Test detailed validation reporting."""
        import tempfile
        import yaml

        # Create formation with warnings and suggestions
        config_with_issues = {
            'name': 'test-formation',
            'version': '1.0.0',
            'unknown_field': 'should_warn',  # Unknown field - should warn
            'agents': [
                {
                    'agent_id': 'test-agent',
                    'model': {
                        'provider': 'unknown_provider',  # Should warn about unknown provider
                        'model': 'gpt-4'
                    }
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_with_issues, f)
            formation_path = f.name

        try:
            validator = FormationValidator()
            result = validator.validate(formation_path)

            # Should be valid but have warnings
            assert result.is_valid
            assert len(result.warnings) > 0

            # Test detailed report
            report = result.detailed_report()
            assert "WARNINGS:" in report
            assert "unknown_field" in report or "unknown_provider" in report

        finally:
            os.unlink(formation_path)


if __name__ == "__main__":
    pytest.main([__file__])
