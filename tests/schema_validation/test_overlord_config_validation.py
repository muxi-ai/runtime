#!/usr/bin/env python3
"""
Test comprehensive overlord configuration validation according to SCHEMA_GUIDE.md

This test module validates:
1. Overlord configuration validation in FormationValidator
2. All overlord configuration fields and their types
3. Overlord LLM configuration overrides
4. Overlord behavior configuration (max_extraction_tokens, caching, etc.)
"""

import pytest
import tempfile
import yaml

# Import the validation classes
from src.muxi.formation.config.validation import FormationValidator


class TestOverlordConfigValidation:
    """Test overlord configuration validation according to SCHEMA_GUIDE.md"""

    def setup_method(self):
        """Set up test fixtures"""
        self.validator = FormationValidator()

    def _create_test_formation(self, overlord_config):
        """Helper to create a test formation with overlord config"""
        return {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for overlord config validation',
            'overlord': overlord_config
        }

    def test_valid_overlord_system_message(self):
        """Test valid overlord system message configuration"""
        overlord_config = {
            'system_message': 'Custom overlord system message for routing.'
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_valid_overlord_llm_config(self):
        """Test valid overlord LLM configuration"""
        overlord_config = {
            'llm': {
                'model': 'openai/gpt-4o',
                'api_key': 'sk-test-key',
                'settings': {
                    'temperature': 0.2,
                    'max_tokens': 2000,
                    'timeout_seconds': 45
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_valid_overlord_behavior_config(self):
        """Test valid overlord behavior configuration"""
        overlord_config = {
            'config': {
                'max_extraction_tokens': 500,
                'max_tool_calls': -1,
                'response_format': 'markdown',
                'caching': {
                    'enabled': True,
                    'ttl': 3600
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_complete_overlord_config(self):
        """Test complete overlord configuration with all fields"""
        overlord_config = {
            'system_message': 'You are a specialized router for this formation.',
            'llm': {
                'model': 'anthropic/claude-3-sonnet',
                'api_key': '${{ secrets.OVERLORD_API_KEY }}',
                'settings': {
                    'temperature': 0.1,
                    'max_tokens': 1500,
                    'timeout_seconds': 30
                }
            },
            'config': {
                'max_extraction_tokens': 750,
                'max_tool_calls': 10,
                'response_format': 'json',
                'caching': {
                    'enabled': False,
                    'ttl': 1800
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_overlord_system_message_type(self):
        """Test invalid overlord system message type"""
        overlord_config = {
            'system_message': 123  # Should be string
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('system_message must be a string' in error for error in result.errors)

    def test_invalid_overlord_llm_model_type(self):
        """Test invalid overlord LLM model type"""
        overlord_config = {
            'llm': {
                'model': ['invalid', 'list']  # Should be string
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('model must be a string' in error for error in result.errors)

    def test_invalid_max_extraction_tokens(self):
        """Test invalid max_extraction_tokens values"""
        # Test negative value
        overlord_config = {
            'config': {
                'max_extraction_tokens': -100
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('max_extraction_tokens must be a positive integer' in error for error in result.errors)

        # Test zero value
        overlord_config['config']['max_extraction_tokens'] = 0

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('max_extraction_tokens must be a positive integer' in error for error in result.errors)

    def test_invalid_max_tool_calls(self):
        """Test invalid max_tool_calls values"""
        # Test invalid value (not -1 or positive)
        overlord_config = {
            'config': {
                'max_tool_calls': -5
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('max_tool_calls must be positive integer or -1' in error for error in result.errors)

    def test_invalid_response_format(self):
        """Test invalid response format values"""
        overlord_config = {
            'config': {
                'response_format': 'invalid_format'
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('response_format' in error and 'invalid' in error for error in result.errors)

    def test_valid_response_formats(self):
        """Test all valid response format values"""
        valid_formats = ['markdown', 'json', 'text']

        for format_val in valid_formats:
            overlord_config = {
                'config': {
                    'response_format': format_val
                }
            }

            formation = self._create_test_formation(overlord_config)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(formation, f)
                result = self.validator.validate(f.name)

            assert result.is_valid, f"Valid format '{format_val}' should pass validation"

    def test_invalid_caching_enabled_type(self):
        """Test invalid caching enabled type"""
        overlord_config = {
            'config': {
                'caching': {
                    'enabled': 'true'  # Should be boolean
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('enabled must be a boolean' in error for error in result.errors)

    def test_invalid_caching_ttl(self):
        """Test invalid caching TTL values"""
        # Test negative TTL
        overlord_config = {
            'config': {
                'caching': {
                    'ttl': -60
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('TTL must be a positive integer' in error for error in result.errors)

        # Test zero TTL
        overlord_config['config']['caching']['ttl'] = 0

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid
        assert any('TTL must be a positive integer' in error for error in result.errors)

    def test_unknown_overlord_fields_warning(self):
        """Test that unknown overlord fields generate warnings"""
        overlord_config = {
            'unknown_field': 'some value',
            'another_unknown': 42
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid  # Should still be valid, just warnings
        assert len(result.warnings) > 0
        assert any('Unknown overlord fields' in warning for warning in result.warnings)

    def test_unknown_caching_fields_warning(self):
        """Test that unknown caching fields generate warnings"""
        overlord_config = {
            'config': {
                'caching': {
                    'enabled': True,
                    'unknown_caching_field': 'value'
                }
            }
        }

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid  # Should still be valid, just warnings
        assert len(result.warnings) > 0
        assert any('Unknown caching fields' in warning for warning in result.warnings)

    def test_empty_overlord_config(self):
        """Test that empty overlord configuration is valid"""
        overlord_config = {}

        formation = self._create_test_formation(overlord_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
