"""
Tests for Bidirectional JSON-Protobuf Event Converter
"""

import pytest
from datetime import datetime
from typing import Any, Dict

from src.muxi.runtime.services.observability.event_converter import (
    ObservabilityEventConverter,
    ConversionError
)


class TestObservabilityEventConverter:
    """Test the ObservabilityEventConverter class"""

    @pytest.fixture
    def converter(self):
        """Create converter instance for testing"""
        return ObservabilityEventConverter()

    @pytest.fixture
    def sample_conversation_event(self) -> Dict[str, Any]:
        """Sample conversation event in JSON format"""
        return {
            "id": "evt_conv_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "parent_event_id": "evt_conv_parent",
            "request": {
                "id": "req_001",
                "status": "completed",
                "started": int(datetime.now().timestamp()),
                "duration_ms": 1500,
                "formation_id": "formation_123",
                "user_id": "user_456",
                "tokens": {
                    "total": 150,
                    "breakdown": {
                        "model": "gpt-4",
                        "prompt_tokens": 100,
                        "completion_tokens": 50
                    }
                }
            },
            "data": {
                "description": "User message processed",
                "user_message": "Hello, how are you?",
                "agent_response": "I'm doing well, thank you!",
                "agent_id": "agent_001",
                "session_id": "session_123",
                "tool_calls": ["search", "format"],
                "response_time_ms": 1200
            }
        }

    @pytest.fixture
    def sample_system_event(self) -> Dict[str, Any]:
        """Sample system event in JSON format"""
        return {
            "id": "evt_sys_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "ERROR",
            "muxi_version": "1.0.0",
            "server": "prod-server",
            "event": "SYSTEM_ERROR",
            "data": {
                "description": "Component failure",
                "component": "database",
                "version": "1.2.3",
                "error_message": "Connection timeout",
                "exit_code": 1,
                "metrics": {
                    "cpu_usage": 85.5,
                    "memory_mb": 512,
                    "connections": 150
                }
            }
        }

    @pytest.fixture
    def sample_mcp_event(self) -> Dict[str, Any]:
        """Sample MCP event in JSON format"""
        return {
            "id": "evt_mcp_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "mcp-server",
            "event": "MCP_TOOL_CALL",
            "data": {
                "description": "Tool execution",
                "server_id": "mcp_server_123",
                "tool_name": "file_search",
                "parameters": {
                    "path": "/home/user",
                    "pattern": "*.py",
                    "recursive": True
                },
                "result": {
                    "files_found": 42,
                    "total_size_mb": 15.7
                },
                "execution_time_ms": 850
            }
        }

    def test_converter_initialization_success(self, converter):
        """Test that converter initializes successfully when protobuf is available"""
        assert converter is not None
        assert hasattr(converter, 'event_type_mapping')
        assert hasattr(converter, 'level_mapping')
        assert len(converter.event_type_mapping) > 0
        assert len(converter.level_mapping) == 4  # DEBUG, INFO, WARNING, ERROR

    def test_json_to_protobuf_conversation_event(self, converter, sample_conversation_event):
        """Test converting conversation event from JSON to protobuf"""
        pb_event = converter.json_to_protobuf(sample_conversation_event)

        # Verify core fields
        assert pb_event.id == sample_conversation_event["id"]
        assert pb_event.timestamp.ToMilliseconds() == sample_conversation_event["timestamp"]
        assert converter._reverse_map_level(pb_event.level) == sample_conversation_event["level"]
        assert pb_event.muxi_version == sample_conversation_event["muxi_version"]
        assert pb_event.server == sample_conversation_event["server"]
        assert converter._reverse_map_event_type(pb_event.event_type) == sample_conversation_event["event"]

        # Verify optional fields
        assert pb_event.parent_event_id == sample_conversation_event["parent_event_id"]
        assert pb_event.HasField("request")
        assert pb_event.HasField("data")

        # Verify request context
        assert pb_event.request.id == sample_conversation_event["request"]["id"]
        assert pb_event.request.status == sample_conversation_event["request"]["status"]
        assert pb_event.request.tokens.total == sample_conversation_event["request"]["tokens"]["total"]

        # Verify conversation data
        assert pb_event.data.HasField("conversation")
        conv_data = pb_event.data.conversation
        assert conv_data.user_message == sample_conversation_event["data"]["user_message"]
        assert conv_data.agent_response == sample_conversation_event["data"]["agent_response"]
        assert conv_data.agent_id == sample_conversation_event["data"]["agent_id"]
        assert list(conv_data.tool_calls) == sample_conversation_event["data"]["tool_calls"]

    def test_json_to_protobuf_system_event(self, converter, sample_system_event):
        """Test converting system event from JSON to protobuf"""
        pb_event = converter.json_to_protobuf(sample_system_event)

        # Verify core fields
        assert pb_event.id == sample_system_event["id"]
        assert converter._reverse_map_level(pb_event.level) == sample_system_event["level"]
        assert converter._reverse_map_event_type(pb_event.event_type) == sample_system_event["event"]

        # Verify system data
        assert pb_event.data.HasField("system")
        sys_data = pb_event.data.system
        assert sys_data.component == sample_system_event["data"]["component"]
        assert sys_data.version == sample_system_event["data"]["version"]
        assert sys_data.error_message == sample_system_event["data"]["error_message"]
        assert sys_data.exit_code == sample_system_event["data"]["exit_code"]
        assert sys_data.HasField("metrics")

    def test_json_to_protobuf_mcp_event(self, converter, sample_mcp_event):
        """Test converting MCP event from JSON to protobuf"""
        pb_event = converter.json_to_protobuf(sample_mcp_event)

        # Verify core fields
        assert pb_event.id == sample_mcp_event["id"]
        assert converter._reverse_map_event_type(pb_event.event_type) == sample_mcp_event["event"]

        # Verify MCP data
        assert pb_event.data.HasField("mcp")
        mcp_data = pb_event.data.mcp
        assert mcp_data.server_id == sample_mcp_event["data"]["server_id"]
        assert mcp_data.tool_name == sample_mcp_event["data"]["tool_name"]
        assert mcp_data.HasField("parameters")
        assert mcp_data.HasField("result")
        assert mcp_data.execution_time_ms == sample_mcp_event["data"]["execution_time_ms"]

    def test_protobuf_to_json_conversation_event(self, converter, sample_conversation_event):
        """Test converting conversation event from protobuf back to JSON"""
        # Convert to protobuf first
        pb_event = converter.json_to_protobuf(sample_conversation_event)

        # Convert back to JSON
        json_event = converter.protobuf_to_json(pb_event)

        # Verify round-trip conversion preserves data
        assert json_event["id"] == sample_conversation_event["id"]
        assert json_event["timestamp"] == sample_conversation_event["timestamp"]
        assert json_event["level"] == sample_conversation_event["level"]
        assert json_event["muxi_version"] == sample_conversation_event["muxi_version"]
        assert json_event["server"] == sample_conversation_event["server"]
        assert json_event["event"] == sample_conversation_event["event"]
        assert json_event["parent_event_id"] == sample_conversation_event["parent_event_id"]

        # Verify request context round-trip
        assert json_event["request"]["id"] == sample_conversation_event["request"]["id"]
        assert json_event["request"]["status"] == sample_conversation_event["request"]["status"]
        assert json_event["request"]["tokens"]["total"] == sample_conversation_event["request"]["tokens"]["total"]

        # Verify conversation data round-trip
        assert json_event["data"]["user_message"] == sample_conversation_event["data"]["user_message"]
        assert json_event["data"]["agent_response"] == sample_conversation_event["data"]["agent_response"]
        assert json_event["data"]["tool_calls"] == sample_conversation_event["data"]["tool_calls"]

    def test_protobuf_to_json_system_event(self, converter, sample_system_event):
        """Test converting system event from protobuf back to JSON"""
        # Convert to protobuf first
        pb_event = converter.json_to_protobuf(sample_system_event)

        # Convert back to JSON
        json_event = converter.protobuf_to_json(pb_event)

        # Verify round-trip conversion preserves core data
        assert json_event["event"] == sample_system_event["event"]
        assert json_event["level"] == sample_system_event["level"]
        assert json_event["data"]["component"] == sample_system_event["data"]["component"]
        assert json_event["data"]["error_message"] == sample_system_event["data"]["error_message"]
        assert json_event["data"]["exit_code"] == sample_system_event["data"]["exit_code"]

        # Verify metrics are preserved
        assert "metrics" in json_event["data"]
        assert isinstance(json_event["data"]["metrics"], dict)

    def test_protobuf_to_json_mcp_event(self, converter, sample_mcp_event):
        """Test converting MCP event from protobuf back to JSON"""
        # Convert to protobuf first
        pb_event = converter.json_to_protobuf(sample_mcp_event)

        # Convert back to JSON
        json_event = converter.protobuf_to_json(pb_event)

        # Verify round-trip conversion preserves core data
        assert json_event["event"] == sample_mcp_event["event"]
        assert json_event["data"]["server_id"] == sample_mcp_event["data"]["server_id"]
        assert json_event["data"]["tool_name"] == sample_mcp_event["data"]["tool_name"]
        assert json_event["data"]["execution_time_ms"] == sample_mcp_event["data"]["execution_time_ms"]

        # Verify structured data is preserved
        assert "parameters" in json_event["data"]
        assert "result" in json_event["data"]
        assert isinstance(json_event["data"]["parameters"], dict)
        assert isinstance(json_event["data"]["result"], dict)

    def test_unknown_event_level_error(self, converter):
        """Test that unknown event level raises ConversionError"""
        invalid_event = {
            "id": "evt_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INVALID_LEVEL",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "SYSTEM_STARTUP",
        }

        with pytest.raises(ConversionError, match="Unknown event level"):
            converter.json_to_protobuf(invalid_event)

    def test_unknown_event_type_error(self, converter):
        """Test that unknown event type raises ConversionError"""
        invalid_event = {
            "id": "evt_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "INVALID_EVENT_TYPE",
        }

        with pytest.raises(ConversionError, match="Unknown event type"):
            converter.json_to_protobuf(invalid_event)

    def test_missing_required_field_error(self, converter):
        """Test that missing required field raises ConversionError"""
        invalid_event = {
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "SYSTEM_STARTUP",
            # Missing 'id' field
        }

        with pytest.raises(ConversionError):
            converter.json_to_protobuf(invalid_event)

    def test_token_usage_openai_format(self, converter):
        """Test token usage conversion for OpenAI format"""
        event_with_openai_tokens = {
            "id": "evt_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_001",
                "status": "completed",
                "tokens": {
                    "total": 200,
                    "breakdown": {
                        "model": "gpt-4",
                        "prompt_tokens": 150,
                        "completion_tokens": 50,
                        "cached_tokens": 25
                    }
                }
            }
        }

        pb_event = converter.json_to_protobuf(event_with_openai_tokens)

        # Verify OpenAI token breakdown is used
        assert pb_event.request.tokens.HasField("openai")
        openai_tokens = pb_event.request.tokens.openai
        assert openai_tokens.model == "gpt-4"
        assert openai_tokens.prompt_tokens == 150
        assert openai_tokens.completion_tokens == 50
        assert openai_tokens.cached_tokens == 25

        # Verify round-trip preserves format
        json_event = converter.protobuf_to_json(pb_event)
        assert json_event["request"]["tokens"]["breakdown"]["model"] == "gpt-4"
        assert json_event["request"]["tokens"]["breakdown"]["prompt_tokens"] == 150
        assert json_event["request"]["tokens"]["breakdown"]["cached_tokens"] == 25

    def test_token_usage_anthropic_format(self, converter):
        """Test token usage conversion for Anthropic format"""
        event_with_anthropic_tokens = {
            "id": "evt_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_001",
                "status": "completed",
                "tokens": {
                    "total": 300,
                    "breakdown": {
                        "model": "claude-3",
                        "input_tokens": 200,
                        "output_tokens": 100,
                        "cache_creation_input_tokens": 50,
                        "cache_read_input_tokens": 75
                    }
                }
            }
        }

        pb_event = converter.json_to_protobuf(event_with_anthropic_tokens)

        # Verify Anthropic token breakdown is used
        assert pb_event.request.tokens.HasField("anthropic")
        anthropic_tokens = pb_event.request.tokens.anthropic
        assert anthropic_tokens.model == "claude-3"
        assert anthropic_tokens.input_tokens == 200
        assert anthropic_tokens.output_tokens == 100
        assert anthropic_tokens.cache_creation_input_tokens == 50
        assert anthropic_tokens.cache_read_input_tokens == 75

        # Verify round-trip preserves format
        json_event = converter.protobuf_to_json(pb_event)
        assert json_event["request"]["tokens"]["breakdown"]["model"] == "claude-3"
        assert json_event["request"]["tokens"]["breakdown"]["input_tokens"] == 200
        assert json_event["request"]["tokens"]["breakdown"]["cache_creation_input_tokens"] == 50

    def test_token_usage_generic_format(self, converter):
        """Test token usage conversion for generic format"""
        event_with_generic_tokens = {
            "id": "evt_001",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "test-server",
            "event": "CONVERSATION_MESSAGE",
            "request": {
                "id": "req_001",
                "status": "completed",
                "tokens": {
                    "total": 250,
                    "breakdown": {
                        "model": "custom-model",
                        "input_tokens": 180,
                        "output_tokens": 70,
                        "custom_metric": 42,
                        "processing_time": 1.5
                    }
                }
            }
        }

        pb_event = converter.json_to_protobuf(event_with_generic_tokens)

        # Verify generic token breakdown is used
        assert pb_event.request.tokens.HasField("generic")
        generic_tokens = pb_event.request.tokens.generic
        assert generic_tokens.model == "custom-model"
        assert generic_tokens.input_tokens == 180
        assert generic_tokens.output_tokens == 70
        assert generic_tokens.HasField("additional_metrics")

        # Verify round-trip preserves additional metrics
        json_event = converter.protobuf_to_json(pb_event)
        assert json_event["request"]["tokens"]["breakdown"]["model"] == "custom-model"
        assert json_event["request"]["tokens"]["breakdown"]["input_tokens"] == 180
        assert "custom_metric" in json_event["request"]["tokens"]["breakdown"]
        assert "processing_time" in json_event["request"]["tokens"]["breakdown"]

    def test_minimal_event_conversion(self, converter):
        """Test conversion of minimal event with only required fields"""
        minimal_event = {
            "id": "evt_minimal",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "DEBUG",
            "muxi_version": "1.0.0",
            "server": "minimal-server",
            "event": "SYSTEM_HEALTH_CHECK"
        }

        # Should convert successfully
        pb_event = converter.json_to_protobuf(minimal_event)
        assert pb_event.id == minimal_event["id"]
        assert converter._reverse_map_level(pb_event.level) == minimal_event["level"]
        assert converter._reverse_map_event_type(pb_event.event_type) == minimal_event["event"]

        # Should not have optional fields
        assert not pb_event.HasField("parent_event_id")
        assert not pb_event.HasField("request")
        assert not pb_event.HasField("data")

        # Round-trip should preserve minimal structure
        json_event = converter.protobuf_to_json(pb_event)
        assert json_event["id"] == minimal_event["id"]
        assert json_event["level"] == minimal_event["level"]
        assert json_event["event"] == minimal_event["event"]
        assert "parent_event_id" not in json_event
        assert "request" not in json_event
        assert "data" not in json_event

    def test_custom_event_data_fallback(self, converter):
        """Test that unknown event types fall back to custom data storage"""
        event_with_custom_data = {
            "id": "evt_custom",
            "timestamp": int(datetime.now().timestamp() * 1000),
            "level": "INFO",
            "muxi_version": "1.0.0",
            "server": "custom-server",
            "event": "PERFORMANCE_METRIC",  # Will use custom fallback
            "data": {
                "description": "Custom performance data",
                "metric_name": "response_time",
                "value": 125.5,
                "unit": "ms",
                "tags": ["important", "baseline"],
                "metadata": {
                    "source": "load_balancer",
                    "region": "us-west-2"
                }
            }
        }

        pb_event = converter.json_to_protobuf(event_with_custom_data)

        # Should use custom data storage
        assert pb_event.data.HasField("custom")

        # Round-trip should preserve custom data
        json_event = converter.protobuf_to_json(pb_event)
        assert json_event["data"]["metric_name"] == "response_time"
        assert json_event["data"]["value"] == 125.5
        assert json_event["data"]["tags"] == ["important", "baseline"]
        assert json_event["data"]["metadata"]["source"] == "load_balancer"
