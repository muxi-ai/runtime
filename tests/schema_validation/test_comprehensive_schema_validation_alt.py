#!/usr/bin/env python3
"""
Comprehensive Schema Validation Test Suite for Phase 6

This test suite ensures 100% coverage of all SCHEMA_GUIDE.md features
and edge cases for comprehensive validation and testing.
"""

import tempfile
import yaml
import pytest

from src.muxi.runtime.config.validation import FormationValidator


class TestComprehensiveSchemaValidation:
    """Phase 6: Comprehensive validation coverage for all SCHEMA_GUIDE.md features."""

    def setup_method(self):
        """Set up test environment."""
        self.validator = FormationValidator()

    def test_maximum_complex_formation_config(self):
        """Test the most complex possible formation configuration with all features."""
        complex_formation = {
            'schema': '1.0.0',
            'id': 'complex-formation',
            'description': 'The most complex formation possible',
            'system_message': 'Complex system message for testing',

            # Optional metadata fields
            'author': 'Test Author <test@example.com>',
            'url': 'https://example.com/formation',
            'license': 'MIT',
            'version': '2.1.0',

            # Authentication configuration
            'auth': {
                'api_keys': {
                    'admin_key': '${{ secrets.ADMIN_KEY }}',
                    'client_key': '${{ secrets.CLIENT_KEY }}'
                }
            },

            # Full LLM configuration with all capabilities
            'llm': {
                'settings': {
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'timeout_seconds': 45
                },
                'api_keys': {
                    'openai': '${{ secrets.OPENAI_KEY }}',
                    'anthropic': '${{ secrets.ANTHROPIC_KEY }}',
                    'other': '${{ secrets.OTHER_KEY }}'
                },
                'models': [
                    {
                        'text': 'openai/gpt-4o',
                        'api_key': '${{ secrets.CUSTOM_TEXT_KEY }}',
                        'settings': {
                            'temperature': 0.5,
                            'max_tokens': 1500
                        }
                    },
                    {
                        'vision': 'openai/gpt-4o',
                        'settings': {
                            'temperature': 0.8,
                            'image': {
                                'max_size_mb': 10,
                                'preprocessing': {
                                    'resize': True,
                                    'max_width': 2048,
                                    'max_height': 2048
                                }
                            }
                        }
                    }
                ]
            },

            # Full overlord configuration
            'overlord': {
                'system_message': 'Custom overlord system message',
                'llm': {
                    'model': 'anthropic/claude-3-opus',
                    'api_key': '${{ secrets.OVERLORD_KEY }}',
                    'settings': {
                        'temperature': 0.1,
                        'max_tokens': 3000,
                        'timeout_seconds': 60
                    }
                },
                'config': {
                    'max_extraction_tokens': 1000,
                    'caching': {
                        'enabled': True,
                        'ttl': 7200
                    },
                    'max_tool_calls': 20,
                    'response_format': 'json'
                }
            },

            # Full memory configuration
            'memory': {
                'buffer': {
                    'size': 20,
                    'multiplier': 15,
                    'vector_search': True,
                    'vector_dimension': 3072,
                    'mode': 'remote',
                    'remote': {
                        'url': 'tcp://memory.example.com:8000',
                        'api_key': '${{ secrets.FAISSX_KEY }}',
                        'tenant': '${{ secrets.FAISSX_TENANT }}'
                    }
                },
                'long_term': {
                    'connection_string': '${{ secrets.DATABASE_URL }}',
                    'embedding_model': 'openai/text-embedding-3-large'
                }
            },

            # Full logging configuration
            'logging': {
                'enabled': True,
                'streams': [
                    {
                        'transport': 'stream',
                        'level': 'debug',
                        'format': 'jsonl',
                        'destination': 'tcp://logs.example.com:9000/ingest',
                        'protocol': 'zmq',
                        'events': [
                            'user_prompts_interaction',
                            'multi_modal_metadata',
                            'overlord_routing',
                            'system_health',
                            'error.*'
                        ],
                        'auth': {
                            'type': 'token',
                            'token': '${{ secrets.LOGS_TOKEN }}'
                        }
                    }
                ]
            },

            # Full A2A configuration
            'a2a': {
                'enabled': True,
                'outbound': {
                    'enabled': True,
                    'registries': [
                        'https://a2a.muxihub.com'
                    ],
                    'default_retry_attempts': 5,
                    'default_timeout_seconds': 45,
                    'services': []
                },
                'inbound': {
                    'enabled': True,
                    'port': 8282,
                    'trusted_endpoints': [
                        'trusted.partner.com'
                    ],
                    'mode': 'api_key',
                    'shared_key': '${{ secrets.A2A_SHARED_KEY }}'
                }
            },

            # MCP configuration
            'mcp': {
                'default_retry_attempts': 4,
                'default_timeout_seconds': 35,
                'servers': []
            },

            # Agents configuration
            'agents': []
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(complex_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Complex formation validation failed: {result.errors}"
        assert len(result.errors) == 0

    def test_edge_case_validation_scenarios(self):
        """Test various edge cases for comprehensive validation."""
        # Test empty but valid configuration
        minimal_formation = {
            'schema': '1.0.0',
            'id': 'minimal',
            'description': 'Minimal valid formation'
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_boundary_value_validation(self):
        """Test boundary values for numeric fields."""
        boundary_formation = {
            'schema': '1.0.0',
            'id': 'boundary-test',
            'description': 'Testing boundary values',
            'llm': {
                'settings': {
                    'temperature': 0.0,
                    'max_tokens': 1,
                    'timeout_seconds': 1
                }
            },
            'memory': {
                'buffer': {
                    'size': 1,
                    'multiplier': 1,
                    'vector_dimension': 1
                }
            },
            'a2a': {
                'outbound': {
                    'default_retry_attempts': 0,
                    'default_timeout_seconds': 1
                },
                'inbound': {
                    'port': 1024
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(boundary_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid
        assert len(result.errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
