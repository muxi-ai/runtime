#!/usr/bin/env python3
"""
Phase 6: Comprehensive Schema Validation Test Suite

This test suite ensures 100% coverage of all SCHEMA_GUIDE.md features,
edge cases, boundary values, and comprehensive validation scenarios.
"""

import tempfile
import yaml
import pytest
import time

from runtime.muxi.runtime.config.validation import FormationValidator


class TestPhase6ComprehensiveSchemaValidation:
    """Phase 6: Complete validation coverage for ALL SCHEMA_GUIDE.md features."""

    def setup_method(self):
        """Set up test environment."""
        self.validator = FormationValidator()

    def test_maximum_complex_formation_all_features(self):
        """Test the most complex possible formation with ALL SCHEMA_GUIDE.md features."""
        complex_formation = {
            "schema": "1.0.0",
            "id": "phase6-comprehensive-formation",
            "description": "Phase 6 comprehensive formation testing all features",
            "system_message": "Comprehensive system message for Phase 6 testing",
            # All optional metadata fields
            "author": "Phase 6 Test Author <phase6@test.com>",
            "url": "https://phase6.test.com/formation",
            "license": "Apache-2.0",
            "version": "6.0.0",
            # Complete authentication configuration
            "auth": {
                "api_keys": {
                    "admin_key": "${{ secrets.PHASE6_ADMIN_KEY }}",
                    "user_key": "${{ secrets.PHASE6_USER_KEY }}",
                }
            },
            # Complete LLM configuration with ALL capabilities
            "llm": {
                "settings": {"temperature": 0.8, "max_tokens": 3000, "timeout_seconds": 60},
                "api_keys": {
                    "openai": "${{ secrets.PHASE6_OPENAI_KEY }}",
                    "anthropic": "${{ secrets.PHASE6_ANTHROPIC_KEY }}",
                    "other": "${{ secrets.PHASE6_OTHER_KEY }}",
                },
                "models": [
                    {
                        "text": "openai/gpt-4o",
                        "api_key": "${{ secrets.PHASE6_TEXT_KEY }}",
                        "settings": {"temperature": 0.6, "max_tokens": 2500, "timeout_seconds": 45},
                    },
                    {
                        "vision": "openai/gpt-4o",
                        "api_key": "${{ secrets.PHASE6_VISION_KEY }}",
                        "settings": {
                            "temperature": 0.7,
                            "max_tokens": 2000,
                            "timeout_seconds": 50,
                            "image": {
                                "max_size_mb": 15,
                                "preprocessing": {
                                    "resize": True,
                                    "max_width": 2048,
                                    "max_height": 2048,
                                },
                            },
                        },
                    },
                    {
                        "audio": "openai/whisper-1",
                        "api_key": "${{ secrets.PHASE6_AUDIO_KEY }}",
                        "settings": {"max_size_mb": 30, "language": "en", "timeout_seconds": 120},
                    },
                    {
                        "documents": "openai/gpt-4o",
                        "api_key": "${{ secrets.PHASE6_DOCS_KEY }}",
                        "settings": {
                            "max_size_mb": 50,
                            "timeout_seconds": 90,
                            "extraction": {"chunk_size": 2000, "overlap": 200},
                        },
                    },
                    {
                        "embedding": "openai/text-embedding-3-large",
                        "api_key": "${{ secrets.PHASE6_EMBEDDING_KEY }}",
                        "settings": {"temperature": 0.0, "timeout_seconds": 30},
                    },
                ],
            },
            # Complete overlord configuration
            "overlord": {
                "system_message": "Phase 6 comprehensive overlord system message",
                "llm": {
                    "model": "anthropic/claude-3-opus",
                    "api_key": "${{ secrets.PHASE6_OVERLORD_KEY }}",
                    "settings": {"temperature": 0.15, "max_tokens": 4000, "timeout_seconds": 75},
                },
                "config": {
                    "max_extraction_tokens": 1500,
                    "caching": {"enabled": True, "ttl": 9600},
                    "max_tool_calls": 25,
                    "response_format": "json",
                },
            },
            # Complete memory configuration (all modes)
            "memory": {
                "buffer": {
                    "size": 25,
                    "multiplier": 20,
                    "vector_search": True,
                    "vector_dimension": 3072,
                    "mode": "remote",
                    "remote": {
                        "url": "tcp://phase6-memory.test.com:8000",
                        "api_key": "${{ secrets.PHASE6_FAISSX_KEY }}",
                        "tenant": "${{ secrets.PHASE6_FAISSX_TENANT }}",
                    },
                },
                "long_term": {
                    "connection_string": "${{ secrets.PHASE6_DATABASE_URL }}",
                    "embedding_model": "openai/text-embedding-3-large",
                },
            },
            # Complete logging configuration (all categories)
            "logging": {
                "level": "debug",
                "format": "jsonl",
                "output": "stream",
                "stream_url": "tcp://phase6-logs.test.com:9000/ingest",
                "log": [
                    "user_prompts_interaction",
                    "multi_modal_metadata",
                    "overlord_routing",
                    "agent_reflections",
                    "system_health",
                    "mcp_tool_calls",
                    "memory_recall",
                    "memory_storage",
                    "errors",
                ],
                "exclude": [
                    "agent_reflections"  # Should create warning about conflicting categories
                ],
            },
            # Complete A2A configuration
            "a2a": {
                "enabled": True,
                "outbound": {
                    "enabled": True,
                    "registries": [
                        "https://a2a.phase6.test.com",
                        "https://external.phase6.test.com",
                    ],
                    "default_retry_attempts": 6,
                    "default_timeout_seconds": 60,
                    "services": [],
                },
                "inbound": {
                    "enabled": True,
                    "registries": ["https://internal.phase6.test.com"],
                    "port": 8383,
                    "trusted_endpoints": ["trusted.phase6.test.com", "partner.phase6.test.com"],
                    "mode": "api_key",
                    "shared_key": "${{ secrets.PHASE6_A2A_SHARED_KEY }}",
                },
            },
            # Complete MCP configuration
            "mcp": {"default_retry_attempts": 5, "default_timeout_seconds": 45, "servers": []},
            # Empty agents (auto-discovered)
            "agents": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(complex_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Phase 6 comprehensive formation failed: {result.errors}"
        assert len(result.errors) == 0
        # Should have warnings about log conflicts
        assert len(result.warnings) >= 1

    def test_boundary_values_comprehensive(self):
        """Test ALL boundary values across all configuration sections."""
        boundary_formation = {
            "schema": "1.0.0",
            "id": "boundary-comprehensive-test",
            "description": "Testing all boundary values comprehensively",
            # LLM boundary values
            "llm": {
                "settings": {
                    "temperature": 0.0,  # Minimum
                    "max_tokens": 1,  # Minimum
                    "timeout_seconds": 1,  # Minimum
                },
                "models": [
                    {
                        "text": "test/model",
                        "settings": {
                            "temperature": 1.0,  # Maximum
                            "max_tokens": 100000,  # High value
                            "timeout_seconds": 3600,  # 1 hour
                        },
                    },
                    {
                        "vision": "test/vision-model",
                        "settings": {
                            "image": {
                                "max_size_mb": 1,  # Minimum
                                "preprocessing": {
                                    "resize": False,
                                    "max_width": 64,  # Small
                                    "max_height": 64,  # Small
                                },
                            }
                        },
                    },
                    {
                        "audio": "test/audio-model",
                        "settings": {"max_size_mb": 1, "language": "auto"},  # Minimum
                    },
                    {
                        "documents": "test/docs-model",
                        "settings": {
                            "max_size_mb": 1,  # Minimum
                            "extraction": {"chunk_size": 100, "overlap": 0},  # Small  # Minimum
                        },
                    },
                ],
            },
            # Memory boundary values
            "memory": {
                "buffer": {
                    "size": 1,  # Minimum
                    "multiplier": 1,  # Minimum
                    "vector_search": False,  # Disabled
                    "vector_dimension": 1,  # Minimum
                    "mode": "local",  # Local mode
                }
            },
            # Overlord boundary values
            "overlord": {
                "config": {
                    "max_extraction_tokens": 1,  # Minimum
                    "caching": {"enabled": False, "ttl": 1},  # Disabled  # Minimum
                    "max_tool_calls": 1,  # Minimum positive
                    "response_format": "text",  # Simple format
                }
            },
            # A2A boundary values
            "a2a": {
                "outbound": {
                    "default_retry_attempts": 0,  # Minimum
                    "default_timeout_seconds": 1,  # Minimum
                },
                "inbound": {
                    "port": 1024,  # Minimum valid port
                    "trusted_endpoints": [],  # Empty array
                },
            },
            # MCP boundary values
            "mcp": {
                "default_retry_attempts": 0,  # Minimum
                "default_timeout_seconds": 1,  # Minimum
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(boundary_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Boundary values test failed: {result.errors}"
        assert len(result.errors) == 0

    def test_invalid_boundary_values(self):
        """Test invalid boundary values that should fail validation."""
        invalid_formation = {
            "schema": "1.0.0",
            "id": "invalid-boundary-test",
            "description": "Testing invalid boundary values",
            "llm": {
                "settings": {
                    "temperature": -1.0,  # Invalid negative
                    "max_tokens": 0,  # Invalid zero
                    "timeout_seconds": -5,  # Invalid negative
                }
            },
            "memory": {
                "buffer": {
                    "size": 0,  # Invalid zero
                    "multiplier": 0,  # Invalid zero
                    "vector_dimension": 0,  # Invalid zero
                }
            },
            "a2a": {"inbound": {"port": -1}},  # Invalid negative port
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid, "Invalid boundary values should fail validation"
        assert len(result.errors) >= 3  # Should have multiple boundary errors

    def test_secrets_interpolation_comprehensive(self):
        """Test comprehensive secrets usage across ALL configuration sections."""
        secrets_formation = {
            "schema": "1.0.0",
            "id": "secrets-comprehensive-test",
            "description": "Testing secrets in all possible locations",
            # Auth secrets
            "auth": {
                "api_keys": {
                    "admin_key": "${{ secrets.COMPREHENSIVE_ADMIN_KEY }}",
                    "user_key": "${{ secrets.COMPREHENSIVE_USER_KEY }}",
                }
            },
            # LLM secrets (all providers and models)
            "llm": {
                "api_keys": {
                    "openai": "${{ secrets.COMPREHENSIVE_OPENAI_KEY }}",
                    "anthropic": "${{ secrets.COMPREHENSIVE_ANTHROPIC_KEY }}",
                    "other": "${{ secrets.COMPREHENSIVE_OTHER_KEY }}",
                },
                "models": [
                    {
                        "text": "openai/gpt-4o",
                        "api_key": "${{ secrets.COMPREHENSIVE_TEXT_API_KEY }}",
                    },
                    {
                        "vision": "openai/gpt-4o",
                        "api_key": "${{ secrets.COMPREHENSIVE_VISION_API_KEY }}",
                    },
                    {
                        "audio": "openai/whisper-1",
                        "api_key": "${{ secrets.COMPREHENSIVE_AUDIO_API_KEY }}",
                    },
                    {
                        "documents": "openai/gpt-4o",
                        "api_key": "${{ secrets.COMPREHENSIVE_DOCS_API_KEY }}",
                    },
                    {
                        "embedding": "openai/text-embedding-3-large",
                        "api_key": "${{ secrets.COMPREHENSIVE_EMBEDDING_API_KEY }}",
                    },
                ],
            },
            # Overlord secrets
            "overlord": {"llm": {"api_key": "${{ secrets.COMPREHENSIVE_OVERLORD_API_KEY }}"}},
            # Memory secrets
            "memory": {
                "buffer": {
                    "remote": {
                        "api_key": "${{ secrets.COMPREHENSIVE_FAISSX_API_KEY }}",
                        "tenant": "${{ secrets.COMPREHENSIVE_FAISSX_TENANT_ID }}",
                    }
                },
                "long_term": {
                    "connection_string": "${{ secrets.COMPREHENSIVE_DATABASE_CONNECTION_STRING }}"
                },
            },
            # A2A secrets
            "a2a": {"inbound": {"shared_key": "${{ secrets.COMPREHENSIVE_A2A_SHARED_KEY }}"}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(secrets_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Comprehensive secrets test failed: {result.errors}"
        assert len(result.errors) == 0

    def test_unknown_fields_detection_comprehensive(self):
        """Test comprehensive unknown fields detection across ALL sections."""
        unknown_fields_formation = {
            "schema": "1.0.0",
            "id": "unknown-fields-test",
            "description": "Testing unknown fields detection",
            # Top-level unknown fields
            "unknown_top_level_field": "should warn",
            "invalid_formation_field": "should warn",
            # LLM unknown fields
            "llm": {
                "unknown_llm_field": "should warn",
                "settings": {
                    "unknown_setting": "should warn",
                    "invalid_llm_setting": "should warn",
                },
                "models": [
                    {
                        "text": "openai/gpt-4o",
                        "unknown_model_field": "should warn",
                        "settings": {"unknown_model_setting": "should warn"},
                    }
                ],
            },
            # Overlord unknown fields
            "overlord": {
                "unknown_overlord_field": "should warn",
                "config": {"unknown_overlord_config": "should warn"},
            },
            # Memory unknown fields
            "memory": {
                "unknown_memory_field": "should warn",
                "buffer": {"unknown_buffer_field": "should warn"},
                "long_term": {"unknown_long_term_field": "should warn"},
            },
            # Logging unknown fields
            "logging": {"unknown_logging_field": "should warn"},
            # A2A unknown fields
            "a2a": {
                "unknown_a2a_field": "should warn",
                "outbound": {"unknown_outbound_field": "should warn"},
                "inbound": {"unknown_inbound_field": "should warn"},
            },
            # MCP unknown fields
            "mcp": {"unknown_mcp_field": "should warn"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(unknown_fields_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, "Unknown fields should not invalidate the formation"
        assert len(result.warnings) >= 5, (
            "Should warn about multiple unknown fields, "
            f"got {len(result.warnings)} warnings: {result.warnings}"
        )

    def test_type_validation_comprehensive(self):
        """Test comprehensive type validation for ALL field types."""
        invalid_types_formation = {
            "schema": 123,  # Should be string
            "id": [],  # Should be string
            "description": {},  # Should be string
            "system_message": 456,  # Should be string
            "auth": {"api_keys": "not_an_object"},  # Should be object
            "llm": {
                "settings": {
                    "temperature": "invalid",  # Should be float
                    "max_tokens": "invalid",  # Should be int
                    "timeout_seconds": [],  # Should be int
                },
                "api_keys": "not_an_object",  # Should be object
                "models": "not_an_array",  # Should be array
            },
            "overlord": {
                "system_message": 789,  # Should be string
                "config": {
                    "max_extraction_tokens": "invalid",  # Should be int
                    "max_tool_calls": "invalid",  # Should be int
                    "caching": {
                        "enabled": "yes",  # Should be bool
                        "ttl": "invalid",  # Should be int
                    },
                },
            },
            "memory": {
                "buffer": {
                    "size": "invalid",  # Should be int
                    "multiplier": "invalid",  # Should be int
                    "vector_search": "yes",  # Should be bool
                    "vector_dimension": "invalid",  # Should be int
                }
            },
            "a2a": {
                "enabled": "yes",  # Should be bool
                "outbound": {
                    "enabled": "true",  # Should be bool
                    "default_retry_attempts": "invalid",  # Should be int
                    "default_timeout_seconds": "invalid",  # Should be int
                    "registries": "not_an_array",  # Should be array
                },
                "inbound": {"port": "invalid"},  # Should be int
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(invalid_types_formation, f)
            result = self.validator.validate(f.name)

        assert not result.is_valid, "Invalid types should fail validation"
        assert len(result.errors) >= 10, f"Should have many type errors, got {len(result.errors)}"

    def test_performance_with_maximum_complexity(self):
        """Test validation performance with maximum complexity configuration."""
        # Create a formation with maximum allowed complexity
        max_complexity_formation = {
            "schema": "1.0.0",
            "id": "performance-max-complexity",
            "description": "Performance testing with maximum complexity",
            "llm": {"models": []},
        }

        # Add maximum number of model configurations for each capability
        for i in range(20):  # 20 of each capability = 100 total models
            max_complexity_formation["llm"]["models"].extend(
                [
                    {
                        "text": f"provider/text-model-{i}",
                        "api_key": f"${{{{ secrets.TEXT_KEY_{i} }}}}",
                        "settings": {"temperature": 0.7, "max_tokens": 1000, "timeout_seconds": 30},
                    },
                    {
                        "vision": f"provider/vision-model-{i}",
                        "settings": {
                            "image": {
                                "max_size_mb": 10,
                                "preprocessing": {
                                    "resize": True,
                                    "max_width": 1024,
                                    "max_height": 1024,
                                },
                            }
                        },
                    },
                    {
                        "audio": f"provider/audio-model-{i}",
                        "settings": {"max_size_mb": 20, "language": "auto"},
                    },
                    {
                        "documents": f"provider/docs-model-{i}",
                        "settings": {
                            "max_size_mb": 30,
                            "extraction": {"chunk_size": 1000, "overlap": 100},
                        },
                    },
                    {
                        "embedding": f"provider/embedding-model-{i}",
                        "settings": {"temperature": 0.0},
                    },
                ]
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(max_complexity_formation, f)

            # Time the validation
            start_time = time.time()
            result = self.validator.validate(f.name)
            end_time = time.time()

            validation_time = end_time - start_time

        assert result.is_valid, f"Performance test formation should be valid: {result.errors}"
        assert (
            validation_time < 10.0
        ), f"Validation took too long: {validation_time:.3f}s (should be < 10s)"
        print(f"✅ Performance test: validated 100 models in {validation_time:.3f} seconds")


class TestPhase6EdgeCases:
    """Additional edge cases and stress testing for Phase 6."""

    def setup_method(self):
        """Set up test environment."""
        self.validator = FormationValidator()

    def test_empty_configurations_comprehensive(self):
        """Test various empty but valid configurations."""
        empty_configs = [
            # Minimal valid formation
            {"schema": "1.0.0", "id": "minimal", "description": "Minimal formation"},
            # Formation with empty arrays/objects
            {
                "schema": "1.0.0",
                "id": "empty-arrays",
                "description": "Formation with empty arrays and objects",
                "llm": {"api_keys": {}, "models": []},
                "agents": [],
                "mcp": {"servers": []},
                "a2a": {"outbound": {"services": []}},
            },
        ]

        for i, config in enumerate(empty_configs):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                yaml.dump(config, f)
                result = self.validator.validate(f.name)

            assert result.is_valid, f"Empty config {i} should be valid: {result.errors}"
            assert len(result.errors) == 0

    def test_mixed_authentication_scenarios(self):
        """Test various authentication configuration scenarios."""
        auth_scenarios = [
            # No authentication
            {"schema": "1.0.0", "id": "no-auth", "description": "Formation without authentication"},
            # Only admin key
            {
                "schema": "1.0.0",
                "id": "admin-only",
                "description": "Formation with admin key only",
                "auth": {"api_keys": {"admin_key": "${{ secrets.ADMIN_ONLY_KEY }}"}},
            },
            # Only user key
            {
                "schema": "1.0.0",
                "id": "user-only",
                "description": "Formation with user key only",
                "auth": {"api_keys": {"user_key": "${{ secrets.USER_ONLY_KEY }}"}},
            },
            # Both keys
            {
                "schema": "1.0.0",
                "id": "both-keys",
                "description": "Formation with both auth keys",
                "auth": {
                    "api_keys": {
                        "admin_key": "${{ secrets.ADMIN_KEY }}",
                        "user_key": "${{ secrets.USER_KEY }}",
                    }
                },
            },
        ]

        for i, config in enumerate(auth_scenarios):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                yaml.dump(config, f)
                result = self.validator.validate(f.name)

            assert result.is_valid, f"Auth scenario {i} should be valid: {result.errors}"
            assert len(result.errors) == 0

    def test_minimal_formation_edge_case(self):
        """Test minimal valid formation configuration."""
        minimal_formation = {
            "schema": "1.0.0",
            "id": "minimal-test",
            "description": "Minimal valid formation",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(minimal_formation, f)
            result = self.validator.validate(f.name)

        assert result.is_valid, f"Minimal formation failed: {result.errors}"
        assert len(result.errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
