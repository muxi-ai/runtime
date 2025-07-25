"""
Tests for Protobuf Schema Management and Validation Framework
"""

import pytest
from datetime import datetime

from src.muxi.services.observability.protobuf_schema import (
    ProtobufSchemaManager,
    ValidationResult,
    ValidationError
)


class TestValidationResult:
    """Test ValidationResult dataclass"""

    def test_validation_result_creation(self):
        """Test creating ValidationResult instances"""
        result = ValidationResult(valid=True, issues=[])
        assert result.valid is True
        assert result.issues == []
        assert result.warnings == []

    def test_validation_result_with_warnings(self):
        """Test ValidationResult with warnings"""
        result = ValidationResult(
            valid=True,
            issues=[],
            warnings=["Test warning"]
        )
        assert result.valid is True
        assert result.warnings == ["Test warning"]


class TestProtobufSchemaManager:
    """Test ProtobufSchemaManager class"""

    @pytest.fixture
    def schema_manager(self):
        """Create a schema manager for testing"""
        return ProtobufSchemaManager()

    @pytest.fixture
    def valid_json_event(self):
        """Create a valid JSON event for testing"""
        return {
            "id": "evt_123456789",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_987654321",
                "status": "completed",
                "started": int(datetime.now().timestamp() * 1000),
                "duration_ms": 1500,
                "formation_id": "form_abc123",
                "user_id": "user_def456",
                "tokens": {
                    "total": 1200,
                    "breakdown": {
                        "input": 800,
                        "output": 400,
                        "model": "gpt-4o"
                    }
                }
            },
            "data": {
                "description": "User sent a message",
                "user_message": "Hello, how can you help me?",
                "agent_response": "I can help with various tasks...",
                "agent_id": "assistant_001"
            }
        }

    def test_schema_manager_initialization(self, schema_manager):
        """Test schema manager initializes correctly"""
        assert schema_manager.schema_path is not None
        assert isinstance(schema_manager.schemas, dict)
        assert isinstance(schema_manager.validators, dict)
        assert len(schema_manager.validators) > 0

    def test_schema_info(self, schema_manager):
        """Test getting schema information"""
        info = schema_manager.get_schema_info()
        assert "schema_path" in info
        assert "loaded_schemas" in info
        assert "validators" in info
        assert "schema_files" in info
        assert isinstance(info["validators"], list)

    def test_valid_json_event_validation(self, schema_manager, valid_json_event):
        """Test validation of a completely valid JSON event"""
        result = schema_manager.validate_json_compatibility(valid_json_event)
        assert isinstance(result, ValidationResult)
        # Should be valid or have only warnings, not hard errors
        if not result.valid:
            # If not valid, print issues for debugging
            print(f"Validation issues: {result.issues}")
        assert result.valid is True or len(result.issues) == 0

    def test_missing_required_fields(self, schema_manager):
        """Test validation fails for missing required fields"""
        incomplete_event = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            # Missing level, muxi_version, server, event
        }

        result = schema_manager.validate_json_compatibility(incomplete_event)
        assert result.valid is False
        assert len(result.issues) > 0
        assert any("Missing required field" in issue for issue in result.issues)

    def test_invalid_field_types(self, schema_manager):
        """Test validation fails for invalid field types"""
        invalid_event = {
            "id": 123,  # Should be string
            "timestamp": "not-a-number",  # Should be numeric
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE"
        }

        result = schema_manager.validate_json_compatibility(invalid_event)
        assert result.valid is False
        assert len(result.issues) > 0

    def test_invalid_timestamp_range(self, schema_manager):
        """Test validation flags unreasonable timestamps"""
        invalid_event = {
            "id": "evt_123",
            "timestamp": 123456,  # Too small (not in milliseconds)
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE"
        }

        result = schema_manager.validate_json_compatibility(invalid_event)
        assert result.valid is False
        assert any("timestamp" in issue.lower() for issue in result.issues)

    def test_unknown_event_type_warning(self, schema_manager):
        """Test that unknown event types generate warnings but not errors"""
        event_with_unknown_type = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "UNKNOWN_EVENT_TYPE"
        }

        result = schema_manager.validate_json_compatibility(event_with_unknown_type)
        # Should be valid but with warnings
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("not in known types" in warning for warning in result.warnings)

    def test_deeply_nested_data_warning(self, schema_manager):
        """Test that deeply nested data generates performance warnings"""
        deep_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {
                                "level6": {
                                    "level7": {
                                        "level8": {
                                            "level9": {
                                                "level10": {
                                                    "level11": "deep"
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        event_with_deep_data = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "data": deep_data
        }

        result = schema_manager.validate_json_compatibility(event_with_deep_data)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("deeply nested" in warning for warning in result.warnings)

    def test_large_data_payload_warning(self, schema_manager):
        """Test that large data payloads generate warnings"""
        large_data = {"big_field": "x" * (1024 * 1024 + 1)}  # > 1MB

        event_with_large_data = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "data": large_data
        }

        result = schema_manager.validate_json_compatibility(event_with_large_data)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("large" in warning.lower() for warning in result.warnings)

    def test_request_context_validation(self, schema_manager):
        """Test request context structure validation"""
        event_with_invalid_request = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                # Missing required 'id' and 'status' fields
                "started": "not-a-number",  # Should be numeric
                "duration_ms": "also-not-a-number"  # Should be numeric
            }
        }

        result = schema_manager.validate_json_compatibility(event_with_invalid_request)
        assert result.valid is False
        assert len(result.issues) > 0

    def test_token_structure_validation(self, schema_manager):
        """Test token usage structure validation"""
        event_with_invalid_tokens = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_123",
                "status": "completed",
                "tokens": {
                    # Missing 'total' field
                    "breakdown": {
                        "model": "gpt-4o",
                        "input": 100,
                        "output": 50
                    }
                }
            }
        }

        result = schema_manager.validate_json_compatibility(event_with_invalid_tokens)
        assert result.valid is False
        assert any("total" in issue.lower() for issue in result.issues)

    def test_openai_token_pattern_detection(self, schema_manager):
        """Test detection of OpenAI token patterns"""
        event_with_openai_tokens = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_123",
                "status": "completed",
                "tokens": {
                    "total": 150,
                    "breakdown": {
                        "model": "gpt-4o",
                        "input": 100,
                        "output": 50
                        # Missing expected OpenAI fields
                    }
                }
            }
        }

        result = schema_manager.validate_json_compatibility(event_with_openai_tokens)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("openai" in warning.lower() for warning in result.warnings)

    def test_anthropic_token_pattern_detection(self, schema_manager):
        """Test detection of Anthropic token patterns"""
        event_with_anthropic_tokens = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_123",
                "status": "completed",
                "tokens": {
                    "total": 150,
                    "breakdown": {
                        "model": "claude-3-opus",
                        "prompt_tokens": 100,
                        "completion_tokens": 50
                        # Missing expected Anthropic fields
                    }
                }
            }
        }

        result = schema_manager.validate_json_compatibility(event_with_anthropic_tokens)
        assert result.valid is True
        assert len(result.warnings) > 0
        assert any("anthropic" in warning.lower() for warning in result.warnings)

    def test_validator_exception_handling(self, schema_manager):
        """Test that validator exceptions are handled gracefully"""
        # Create a malformed event that might cause exceptions
        malformed_event = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "data": {"recursive": None}  # This shouldn't cause an exception
        }

        # Set data to be self-referential (which would cause issues in depth calculation)
        malformed_event["data"]["recursive"] = malformed_event["data"]

        # This should not raise an exception, but should handle it gracefully
        result = schema_manager.validate_json_compatibility(malformed_event)
        assert isinstance(result, ValidationResult)
        # Result might be valid or invalid, but should not crash

    def test_empty_and_null_values(self, schema_manager):
        """Test handling of empty and null values"""
        event_with_nulls = {
            "id": "evt_123",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "",  # Empty string
            "muxi_version": None,  # Null value
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE"
        }

        result = schema_manager.validate_json_compatibility(event_with_nulls)
        assert result.valid is False
        assert len(result.issues) > 0
        assert any("cannot be null" in issue for issue in result.issues)
        assert any("cannot be empty" in issue for issue in result.issues)


class TestSchemaManagerEdgeCases:
    """Test edge cases and error conditions"""

    def test_invalid_schema_path(self):
        """Test behavior with invalid schema path"""
        with pytest.raises(ValidationError):
            ProtobufSchemaManager(schema_path="/nonexistent/path")

    def test_schema_path_without_proto_files(self, tmp_path):
        """Test behavior with empty schema directory"""
        empty_dir = tmp_path / "empty_schemas"
        empty_dir.mkdir()

        manager = ProtobufSchemaManager(schema_path=str(empty_dir))
        assert manager.schema_path == empty_dir
        assert len(manager.schemas) == 0

        # Should still be able to validate (with warnings/errors)
        result = manager.validate_json_compatibility({"id": "test"})
        assert isinstance(result, ValidationResult)
