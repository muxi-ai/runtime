#!/usr/bin/env python3
"""
Phase 6.1: Comprehensive Schema Validator Audit

This test suite audits our FormationValidator to ensure 100% coverage
of all SCHEMA_GUIDE.md features and validates our implementation completeness.
"""

import tempfile
import yaml
import pytest

from src.muxi.runtime.config.validation import FormationValidator


class TestPhase6SchemaValidatorAudit:
    """Phase 6.1: Comprehensive audit of schema validation coverage."""

    def setup_method(self):
        """Set up test environment."""
        self.validator = FormationValidator()

    def test_all_required_formation_fields_validated(self):
        """Test that ALL required formation fields from SCHEMA_GUIDE.md are validated."""
        # Test missing required fields
        incomplete_formations = [
            # Missing schema
            {
                'id': 'test-formation',
                'description': 'Test formation'
            },
            # Missing id
            {
                'schema': '1.0.0',
                'description': 'Test formation'
            },
            # Missing description
            {
                'schema': '1.0.0',
                'id': 'test-formation'
            }
        ]

        for i, formation in enumerate(incomplete_formations):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(formation, f)
                result = self.validator.validate(f.name)

            error_msg = f"Formation {i} should fail validation for missing required fields"
            assert not result.is_valid, error_msg
            assert len(result.errors) >= 1, f"Formation {i} should have validation errors"

    def test_all_optional_formation_metadata_fields_supported(self):
        """Test that ALL optional formation metadata fields are supported."""
        formation_with_all_metadata = {
            'schema': '1.0.0',
            'id': 'metadata-test-formation',
            'description': 'Formation testing all optional metadata fields',
            'system_message': 'Test system message',
            'author': 'Test Author <test@example.com>',
            'url': 'https://example.com/formation',
            'license': 'MIT',
            'version': '1.2.3'
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation_with_all_metadata, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Formation with all metadata should be valid: {result.errors}"
        assert len(result.errors) == 0

    def test_all_llm_capabilities_validated(self):
        """Test that ALL LLM capabilities from SCHEMA_GUIDE.md are validated."""
        formation_with_all_capabilities = {
            'schema': '1.0.0',
            'id': 'capabilities-test',
            'description': 'Testing all LLM capabilities',
            'llm': {
                'settings': {
                    'temperature': 0.7,
                    'max_tokens': 1000,
                    'timeout_seconds': 30
                },
                'api_keys': {
                    'openai': '${{ secrets.OPENAI_KEY }}',
                    'anthropic': '${{ secrets.ANTHROPIC_KEY }}',
                    'other': '${{ secrets.OTHER_KEY }}'
                },
                'models': [
                    {
                        'text': 'openai/gpt-4o',
                        'api_key': '${{ secrets.TEXT_KEY }}',
                        'settings': {
                            'temperature': 0.6,
                            'max_tokens': 2000,
                            'timeout_seconds': 45
                        }
                    },
                    {
                        'vision': 'openai/gpt-4o',
                        'settings': {
                            'image': {
                                'max_size_mb': 10,
                                'preprocessing': {
                                    'resize': True,
                                    'max_width': 1024,
                                    'max_height': 1024
                                }
                            }
                        }
                    },
                    {
                        'audio': 'openai/whisper-1',
                        'settings': {
                            'max_size_mb': 20,
                            'language': 'auto'
                        }
                    },
                    {
                        'documents': 'openai/gpt-4o',
                        'settings': {
                            'max_size_mb': 30,
                            'extraction': {
                                'chunk_size': 1000,
                                'overlap': 100
                            }
                        }
                    },
                    {
                        'embedding': 'openai/text-embedding-3-large',
                        'settings': {
                            'temperature': 0.0
                        }
                    }
                ]
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation_with_all_capabilities, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Formation with all capabilities should be valid: {result.errors}"
        assert len(result.errors) == 0

    def test_all_overlord_configuration_fields_validated(self):
        """Test that ALL overlord configuration fields are validated."""
        formation_with_complete_overlord = {
            'schema': '1.0.0',
            'id': 'overlord-complete-test',
            'description': 'Testing complete overlord configuration',
            'overlord': {
                'system_message': 'Custom overlord system message',
                'llm': {
                    'model': 'anthropic/claude-3-opus',
                    'api_key': '${{ secrets.OVERLORD_KEY }}',
                    'settings': {
                        'temperature': 0.2,
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
                    'max_tool_calls': 15,
                    'response_format': 'markdown'
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation_with_complete_overlord, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Complete overlord config should be valid: {result.errors}"
        assert len(result.errors) == 0

    def test_all_memory_configuration_modes_validated(self):
        """Test that ALL memory configuration modes are validated."""
        # Test local mode
        formation_local_memory = {
            'schema': '1.0.0',
            'id': 'memory-local-test',
            'description': 'Testing local memory configuration',
            'memory': {
                'buffer': {
                    'size': 15,
                    'multiplier': 10,
                    'vector_search': True,
                    'vector_dimension': 1536,
                    'mode': 'local'
                },
                'long_term': {
                    'connection_string': 'sqlite:///memory.db',
                    'embedding_model': 'openai/text-embedding-3-large'
                }
            }
        }

        # Test remote mode
        formation_remote_memory = {
            'schema': '1.0.0',
            'id': 'memory-remote-test',
            'description': 'Testing remote memory configuration',
            'memory': {
                'buffer': {
                    'size': 20,
                    'multiplier': 15,
                    'vector_search': True,
                    'vector_dimension': 3072,
                    'mode': 'remote',
                    'remote': {
                        'url': 'tcp://faissx.example.com:8000',
                        'api_key': '${{ secrets.FAISSX_KEY }}',
                        'tenant': '${{ secrets.FAISSX_TENANT }}'
                    }
                }
            }
        }

        for formation in [formation_local_memory, formation_remote_memory]:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(formation, f)
                result = self.validator.validate(f.name)

            assert result.is_valid, f"Memory configuration should be valid: {result.errors}"
            assert len(result.errors) == 0

    def test_all_logging_transport_modes_validated(self):
        """Test that ALL logging transport modes are validated."""
        logging_configurations = [
            # stdout transport
            {
                'schema': '1.0.0',
                'id': 'logging-stdout-test',
                'description': 'Testing stdout logging',
                'logging': {
                    'enabled': True,
                    'streams': [
                        {
                            'transport': 'stdout',
                            'level': 'info',
                            'format': 'jsonl',
                            'events': ['error.*', 'system_health']
                        }
                    ]
                }
            },
            # file transport
            {
                'schema': '1.0.0',
                'id': 'logging-file-test',
                'description': 'Testing file logging',
                'logging': {
                    'enabled': True,
                    'streams': [
                        {
                            'transport': 'file',
                            'level': 'debug',
                            'format': 'text',
                            'destination': '/var/logs/formation.log',
                            'events': ['user_prompts_interaction', 'overlord_routing']
                        }
                    ]
                }
            },
            # stream transport with ZMQ
            {
                'schema': '1.0.0',
                'id': 'logging-stream-test',
                'description': 'Testing stream logging',
                'logging': {
                    'enabled': True,
                    'streams': [
                        {
                            'transport': 'stream',
                            'level': 'warn',
                            'format': 'msgpack',
                            'destination': 'tcp://logs.example.com:9000/ingest',
                            'protocol': 'zmq',
                            'events': ['mcp_tool_calls', 'memory_recall'],
                            'auth': {
                                'type': 'token',
                                'token': '${{ secrets.STREAM_TOKEN }}'
                            }
                        }
                    ]
                }
            },
            # trail transport
            {
                'schema': '1.0.0',
                'id': 'logging-trail-test',
                'description': 'Testing MUXI trail logging',
                'logging': {
                    'enabled': True,
                    'streams': [
                        {
                            'transport': 'trail',
                            'auth': {
                                'type': 'bearer',
                                'token': '${{ secrets.TRAIL_TOKEN }}'
                            }
                        }
                    ]
                }
            }
        ]

        for formation in logging_configurations:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(formation, f)
                result = self.validator.validate(f.name)

            assert result.is_valid, f"Logging config should be valid: {result.errors}"
            assert len(result.errors) == 0

    def test_all_a2a_configuration_modes_validated(self):
        """Test that ALL A2A configuration modes are validated."""
        formation_complete_a2a = {
            'schema': '1.0.0',
            'id': 'a2a-complete-test',
            'description': 'Testing complete A2A configuration',
            'a2a': {
                'enabled': True,
                'outbound': {
                    'enabled': True,
                    'registries': [
                        'https://a2a.example.com',
                        'https://partner.example.com'
                    ],
                    'default_retry_attempts': 5,
                    'default_timeout_seconds': 45,
                    'services': []
                },
                'inbound': {
                    'enabled': True,
                    'registries': [
                        'https://internal.example.com'
                    ],
                    'port': 8282,
                    'trusted_endpoints': [
                        'trusted.example.com',
                        'partner.example.com'
                    ],
                    'mode': 'api_key',
                    'shared_key': '${{ secrets.A2A_SHARED_KEY }}'
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation_complete_a2a, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Complete A2A config should be valid: {result.errors}"
        assert len(result.errors) == 0

    def test_all_authentication_configurations_validated(self):
        """Test that ALL authentication configurations are validated."""
        formation_complete_auth = {
            'schema': '1.0.0',
            'id': 'auth-complete-test',
            'description': 'Testing complete authentication configuration',
            'auth': {
                'api_keys': {
                    'admin_key': '${{ secrets.ADMIN_API_KEY }}',
                    'user_key': '${{ secrets.USER_API_KEY }}'
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation_complete_auth, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Complete auth config should be valid: {result.errors}"
        assert len(result.errors) == 0

    def test_comprehensive_error_message_quality(self):
        """Test that validation error messages are comprehensive and helpful."""
        invalid_formation = {
            'schema': 123,  # Wrong type
            'id': '',       # Empty string
            'description': None,  # Wrong type
            'llm': {
                'settings': {
                    'temperature': 'invalid',  # Wrong type
                    'max_tokens': -1,          # Invalid value
                    'timeout_seconds': 'bad'   # Wrong type
                }
            },
            'memory': {
                'buffer': {
                    'size': 0,              # Invalid value
                    'vector_dimension': -5  # Invalid value
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(invalid_formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid, "Invalid formation should fail validation"
        err_count_msg = f"Should have multiple specific errors, got {len(result.errors)}"
        assert len(result.errors) >= 5, err_count_msg

        # Check that error messages are descriptive
        error_text = ' '.join(result.errors)
        assert 'schema' in error_text.lower(), "Should mention schema field error"
        assert 'temperature' in error_text.lower(), "Should mention temperature field error"
        assert 'size' in error_text.lower(), "Should mention size field error"

    def test_validation_performance_benchmark(self):
        """Test validation performance with complex configurations."""
        import time

        # Create a complex but valid formation
        complex_formation = {
            'schema': '1.0.0',
            'id': 'performance-benchmark',
            'description': 'Performance testing formation',
            'llm': {
                'models': []
            }
        }

        # Add 50 model configurations
        for i in range(50):
            complex_formation['llm']['models'].append({
                'text': f'provider/model-{i}',
                'settings': {
                    'temperature': 0.7,
                    'max_tokens': 1000,
                    'timeout_seconds': 30
                }
            })

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(complex_formation, f)

            # Benchmark validation time
            start_time = time.time()
            result = self.validator.validate(f.name)
            end_time = time.time()

            validation_time = end_time - start_time

        perf_msg = f"Performance benchmark formation should be valid: {result.errors}"
        assert result.is_valid, perf_msg
        time_msg = f"Validation took too long: {validation_time:.3f}s (should be < 3s)"
        assert validation_time < 3.0, time_msg
        print(f"✅ Phase 6 Performance: validated 50 models in {validation_time:.3f} seconds")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
