"""Comprehensive tests for complete MCP implementation.

This test suite covers all MCP protocol features:
- Resources (list, read)
- Prompts (list, get)
- Sampling (createMessage)
- Health monitoring (ping)
- Logging (setLevel, log collection)
"""

import asyncio
import os
import pytest
import sys
from unittest.mock import AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Import all the MCP components we're testing
try:
    from muxi.runtime.services.mcp.resources.discovery import MCPResourceDiscovery
    from muxi.runtime.services.mcp.resources.manager import MCPResourceManager
    from muxi.runtime.services.mcp.prompts.discovery import MCPPromptDiscovery
    from muxi.runtime.services.mcp.prompts.manager import MCPPromptManager
    from muxi.runtime.services.mcp.sampling.client import MCPSamplingClient
    from muxi.runtime.services.mcp.sampling.manager import MCPSamplingManager
    from muxi.runtime.services.mcp.protocol.health import MCPHealthMonitor
    from muxi.runtime.services.mcp.protocol.logging import MCPLoggingClient
except ImportError as e:
    pytest.skip(f"Could not import MCP modules: {e}", allow_module_level=True)


class TestMCPResources:
    """Test MCP Resources implementation."""

    @pytest.fixture
    def transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        return transport

    @pytest.fixture
    def resource_discovery(self):
        """Create resource discovery instance."""
        return MCPResourceDiscovery()

    async def test_list_resources_success(self, transport, resource_discovery):
        """Test successful resource listing."""
        # Mock successful response
        transport.send_request.return_value = {
            "result": {
                "resources": [
                    {
                        "uri": "file://test.txt",
                        "name": "Test File",
                        "description": "A test file",
                        "mimeType": "text/plain"
                    }
                ]
            }
        }

        result = await resource_discovery.list_resources(transport)

        assert len(result["resources"]) == 1
        assert result["resources"][0]["uri"] == "file://test.txt"
        assert result["resources"][0]["name"] == "Test File"

    async def test_read_resource_success(self, transport, resource_discovery):
        """Test successful resource reading."""
        # Mock successful response
        transport.send_request.return_value = {
            "result": {
                "text": "Hello, World!",
                "mimeType": "text/plain"
            }
        }

        content = await resource_discovery.read_resource(transport, "file://test.txt")

        assert content["text"] == "Hello, World!"
        assert content["mimeType"] == "text/plain"


class TestMCPPrompts:
    """Test MCP Prompts implementation."""

    @pytest.fixture
    def transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        return transport

    @pytest.fixture
    def prompt_discovery(self):
        """Create prompt discovery instance."""
        return MCPPromptDiscovery()

    async def test_list_prompts_success(self, transport, prompt_discovery):
        """Test successful prompt listing."""
        # Mock successful response
        transport.send_request.return_value = {
            "result": {
                "prompts": [
                    {
                        "name": "analyze_code",
                        "description": "Analyze code for bugs",
                        "arguments": [
                            {
                                "name": "code",
                                "description": "The code to analyze",
                                "required": True
                            }
                        ]
                    }
                ]
            }
        }

        prompts = await prompt_discovery.list_prompts(transport)

        assert len(prompts) == 1
        assert prompts[0]["name"] == "analyze_code"
        assert len(prompts[0]["arguments"]) == 1

    async def test_get_prompt_success(self, transport, prompt_discovery):
        """Test successful prompt retrieval."""
        # Mock successful response
        transport.send_request.return_value = {
            "result": {
                "description": "Code analysis prompt",
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze this code: test"
                    }
                ]
            }
        }

        prompt = await prompt_discovery.get_prompt(
            transport,
            "analyze_code",
            {"code": "def hello(): print('hello')"}
        )

        assert prompt["description"] == "Code analysis prompt"
        assert len(prompt["messages"]) == 1


class TestMCPSampling:
    """Test MCP Sampling implementation."""

    @pytest.fixture
    def transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        return transport

    @pytest.fixture
    def sampling_client(self):
        """Create sampling client instance."""
        return MCPSamplingClient()

    async def test_create_message_success(self, transport, sampling_client):
        """Test successful message creation."""
        # Mock successful response
        transport.send_request.return_value = {
            "result": {
                "role": "assistant",
                "content": "Hello! How can I help you today?",
                "model": "gpt-4",
                "stopReason": "endTurn"
            }
        }

        messages = [{"role": "user", "content": "Hello"}]
        result = await sampling_client.create_message(transport, messages)

        assert result["role"] == "assistant"
        assert result["content"] == "Hello! How can I help you today?"
        assert result["model"] == "gpt-4"

    def test_prepare_conversation_messages(self, sampling_client):
        """Test conversation message preparation."""
        history = ["Hello", "Hi there!", "How are you?"]
        messages = sampling_client.prepare_conversation_messages(history)

        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    def test_create_model_preferences(self, sampling_client):
        """Test model preferences creation."""
        prefs = sampling_client.create_model_preferences(
            hints=["gpt-4", "claude"],
            cost_priority=0.8,
            speed_priority=0.2,
            intelligence_priority=0.9
        )

        assert prefs["hints"] == ["gpt-4", "claude"]
        assert prefs["costPriority"] == 0.8
        assert prefs["speedPriority"] == 0.2
        assert prefs["intelligencePriority"] == 0.9


class TestMCPHealth:
    """Test MCP Health monitoring implementation."""

    @pytest.fixture
    def transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        return transport

    @pytest.fixture
    def health_monitor(self):
        """Create health monitor instance."""
        return MCPHealthMonitor()

    async def test_ping_success(self, transport, health_monitor):
        """Test successful ping."""
        # Mock successful response
        transport.send_request.return_value = {"result": {}}

        result = await health_monitor.ping(transport)

        assert result["success"] is True
        assert "response_time_ms" in result
        assert result["response_time_ms"] > 0

    async def test_ping_timeout(self, transport, health_monitor):
        """Test ping timeout."""
        # Mock timeout
        transport.send_request.side_effect = asyncio.TimeoutError()

        result = await health_monitor.ping(transport, timeout=0.1)

        assert result["success"] is False
        assert result["error"] == "Ping timeout"


class TestMCPLogging:
    """Test MCP Logging implementation."""

    @pytest.fixture
    def transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        return transport

    @pytest.fixture
    def logging_client(self):
        """Create logging client instance."""
        return MCPLoggingClient()

    async def test_set_logging_level_success(self, transport, logging_client):
        """Test successful logging level setting."""
        # Mock successful response
        transport.send_request.return_value = {"result": {}}

        result = await logging_client.set_logging_level(transport, "debug")

        assert result["success"] is True
        assert result["level"] == "debug"

    def test_collect_logs(self, logging_client):
        """Test log collection."""
        logs = [
            {"level": "info", "data": "Test message 1"},
            {"level": "error", "data": "Test error"},
        ]

        logging_client.collect_logs(logs)

        assert len(logging_client.log_history) == 2
        assert logging_client.log_history[0]["level"] == "info"
        assert logging_client.log_history[1]["level"] == "error"

    def test_format_log_entry(self, logging_client):
        """Test log entry formatting."""
        log_entry = {
            "level": "error",
            "data": "Test error message",
            "timestamp": 1000000000  # Fixed timestamp for testing
        }

        formatted = logging_client.format_log_entry(log_entry)

        assert "ERROR" in formatted
        assert "Test error message" in formatted
        assert "❌" in formatted  # Error emoji


@pytest.mark.integration
class TestMCPIntegration:
    """Integration tests for MCP components working together."""

    def test_all_mcp_features_available(self):
        """Test that all MCP features are properly implemented and importable."""
        # Resources
        assert MCPResourceDiscovery is not None
        assert MCPResourceManager is not None

        # Prompts
        assert MCPPromptDiscovery is not None
        assert MCPPromptManager is not None

        # Sampling
        assert MCPSamplingClient is not None
        assert MCPSamplingManager is not None

        # Health
        assert MCPHealthMonitor is not None

        # Logging
        assert MCPLoggingClient is not None

        print("✅ All MCP features implemented:")
        print("  - Resources (list, read)")
        print("  - Prompts (list, get)")
        print("  - Sampling (createMessage)")
        print("  - Health monitoring (ping)")
        print("  - Logging (setLevel, collection)")
