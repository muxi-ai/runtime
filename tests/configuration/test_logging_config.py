#!/usr/bin/env python3
"""
Test comprehensive logging configuration according to SCHEMA_GUIDE.md

This test module validates:
1. Logging configuration validation in FormationValidator
2. Logging configuration initialization in Overlord
3. All logging configuration fields according to SCHEMA_GUIDE.md
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the classes to test
from muxi.runtime.config.validation import FormationValidator
from muxi.runtime.overlord import Overlord


class TestLoggingConfigValidation:
    """Test logging configuration validation according to SCHEMA_GUIDE.md"""

    def setup_method(self):
        """Set up test fixtures"""
        self.validator = FormationValidator()

    def create_test_formation(self, logging_config):
        """Create a test formation with logging config"""
        return {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for logging validation',
            'logging': logging_config
        }

    def test_valid_logging_config_stdout(self):
        """Test valid logging configuration with stdout output"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stdout'
        }

        formation = self.create_test_formation(logging_config)

        # Create temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_file(self):
        """Test valid logging configuration with file output"""
        logging_config = {
            'level': 'debug',
            'format': 'text',
            'output': 'file',
            'path': '/var/logs/muxi.log'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_stream(self):
        """Test valid logging configuration with stream output"""
        logging_config = {
            'level': 'warning',
            'format': 'jsonl',
            'output': 'stream',
            'stream_url': 'tcp://server:8000/injest'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_with_categories(self):
        """Test valid logging configuration with log categories"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stdout',
            'log': [
                'user_prompts_interaction',
                'overlord_routing',
                'errors'
            ],
            'exclude': [
                'agent_reflections',
                'system_health'
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_invalid_logging_level(self):
        """Test invalid logging level"""
        logging_config = {
            'level': 'invalid_level',
            'format': 'jsonl',
            'output': 'stdout'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("Invalid logging level" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_logging_format(self):
        """Test invalid logging format"""
        logging_config = {
            'level': 'info',
            'format': 'invalid_format',
            'output': 'stdout'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("Invalid logging format" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_logging_output(self):
        """Test invalid logging output"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'invalid_output'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("Invalid logging output" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_missing_path_for_file_output(self):
        """Test missing path when output is 'file'"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'file'
            # Missing 'path' field
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("path is required when output is 'file'" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_missing_stream_url_for_stream_output(self):
        """Test missing stream_url when output is 'stream'"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stream'
            # Missing 'stream_url' field
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("stream_url is required when output is 'stream'" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_log_categories(self):
        """Test invalid log categories"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stdout',
            'log': [
                'valid_category',  # This should trigger a warning
                'user_prompts_interaction'  # Valid category
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid  # Should be valid but with warnings
            assert any("Unknown logging category" in warning for warning in result.warnings)
        finally:
            temp_file.unlink()

    def test_unknown_logging_fields(self):
        """Test unknown logging fields"""
        logging_config = {
            'level': 'info',
            'format': 'jsonl',
            'output': 'stdout',
            'unknown_field': 'some_value'
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid  # Should be valid but with warnings
            assert any("Unknown logging fields" in warning for warning in result.warnings)
        finally:
            temp_file.unlink()


class TestLoggingConfigInitialization:
    """Test logging configuration initialization in Overlord"""

    @pytest.mark.asyncio
    async def test_logging_config_initialization(self):
        """Test that overlord initializes logging configuration correctly"""
        formation_config = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for logging initialization',
            'logging': {
                'level': 'debug',
                'format': 'jsonl',
                'output': 'stdout',
                'log': ['user_prompts_interaction', 'overlord_routing'],
                'exclude': ['agent_reflections']
            }
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        # Mock the logging configuration to avoid actual logging setup
        with patch('runtime.muxi.runtime.config.logging.configure_logging') as mock_configure, \
             patch('runtime.muxi.runtime.config.logging.LoggingConfig') as mock_logging_config:

            await overlord._initialize_logging_config()

            # Verify that configure_logging was called
            mock_configure.assert_called_once()

            # Verify that the logging config was stored
            assert hasattr(overlord, '_logging_config')
            assert overlord._logging_config['level'] == 'debug'
            assert overlord._logging_config['format'] == 'jsonl'
            assert overlord._logging_config['output'] == 'stdout'
            assert 'user_prompts_interaction' in overlord._logging_config['log_categories']
            assert 'agent_reflections' in overlord._logging_config['exclude_categories']

    @pytest.mark.asyncio
    async def test_logging_config_format_conversion(self):
        """Test that logging format conversion works correctly"""
        overlord = Overlord()

        # Test jsonl format conversion
        jsonl_format = overlord._convert_logging_format('jsonl')
        assert '{name}:{function}:{line}' in jsonl_format

        # Test text format conversion
        text_format = overlord._convert_logging_format('text')
        assert '{message}' in text_format
        assert '{name}:{function}:{line}' not in text_format

        # Test default format conversion
        default_format = overlord._convert_logging_format('unknown')
        assert '{name}:{function}:{line}' in default_format

    @pytest.mark.asyncio
    async def test_no_logging_config(self):
        """Test that overlord handles missing logging configuration gracefully"""
        formation_config = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation without logging config'
            # No 'logging' section
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        # This should not raise an exception
        await overlord._initialize_logging_config()

        # Verify that no logging config was stored
        assert not hasattr(overlord, '_logging_config')

    @pytest.mark.asyncio
    async def test_logging_config_with_file_output(self):
        """Test logging configuration with file output"""
        formation_config = {
            'logging': {
                'level': 'info',
                'format': 'text',
                'output': 'file',
                'path': '/tmp/test.log'
            }
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        with patch('runtime.muxi.runtime.config.logging.configure_logging') as mock_configure, \
             patch('runtime.muxi.runtime.config.logging.LoggingConfig') as mock_logging_config:

            await overlord._initialize_logging_config()

            # Verify LoggingConfig was created with correct parameters
            mock_logging_config.assert_called_once_with(
                level='INFO',
                file='/tmp/test.log',
                format=overlord._convert_logging_format('text')
            )

            # Verify configure_logging was called
            mock_configure.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__])
