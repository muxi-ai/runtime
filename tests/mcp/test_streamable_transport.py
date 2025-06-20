# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Streamable HTTP Transport Tests
# Description:  Comprehensive test suite for MCP Streamable HTTP transport
# Role:         Validates Streamable HTTP transport functionality and features
# Usage:        Run via pytest to verify transport implementation
# Author:       Muxi Framework Team
#
# This test suite validates the Streamable HTTP transport implementation
# according to the MCP 2025-03-26 protocol specification. Tests include:
#
# 1. Connection Management
#    - Successful connection establishment
#    - Connection failure scenarios
#    - Disconnection handling
#
# 2. Request/Response Handling
#    - Tool execution over Streamable HTTP
#    - Error handling and recovery
#    - Timeout scenarios
#
# 3. Modern Protocol Features
#    - Structured output support (MCP 2025-06-18)
#    - Resource links handling
#    - Elicitation request processing
#
# 4. Performance Characteristics
#    - Benchmarking against HTTP+SSE
#    - Resource utilization metrics
#    - Connection statistics
#
# This test suite implements the testing strategy specified in the
# Streamable HTTP implementation plan Phase 3.1.
# =============================================================================

import sys
import os
import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Add the source directory to Python path for importing muxi modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.runtime.services.mcp.transports import (
    StreamableHTTPTransport,
    MCPConnectionError,
    MCPTimeoutError,
    MCPCancelledError,
    MCPRequestError,
    CancellationToken
)


class TestStreamableHTTPTransport:
    """Comprehensive tests for Streamable HTTP transport."""

    @pytest.fixture
    def transport(self):
        """Create a test transport instance."""
        return StreamableHTTPTransport("https://test.example.com", request_timeout=30)

    @pytest.mark.asyncio
    async def test_streamable_connection_success(self):
        """Test successful Streamable HTTP connection."""
        transport = StreamableHTTPTransport("https://test.example.com")

        # Mock the streamablehttp_client
        mock_client = AsyncMock()

        with patch('muxi.runtime.services.mcp.transports.streamable.streamablehttp_client') as mock_client_factory:
            mock_client_factory.return_value = mock_client

            # Mock successful connection
            mock_client.connect = AsyncMock(return_value=True)

            result = await transport.connect()

            assert result is True
            assert transport.connected is True
            assert transport.client is mock_client
            assert transport.connect_time is not None
            assert transport.last_activity is not None

            # Verify the client was created with correct parameters
            mock_client_factory.assert_called_once_with(
                url="https://test.example.com",
                timeout=60
            )

    @pytest.mark.asyncio
    async def test_streamable_connection_timeout(self):
        """Test connection timeout scenarios."""
        transport = StreamableHTTPTransport("https://test.example.com", request_timeout=1)

        with patch('muxi.runtime.services.mcp.handler.streamablehttp_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_client_factory.return_value = mock_client

            # Mock timeout during connection
            mock_client.connect = AsyncMock(side_effect=asyncio.TimeoutError("Connection timeout"))

            with pytest.raises(MCPTimeoutError) as exc_info:
                await transport.connect()

            assert "Connection to Streamable HTTP endpoint timed out" in str(exc_info.value)
            assert transport.connected is False
            assert transport.connection_stats['errors_encountered'] == 1

    @pytest.mark.asyncio
    async def test_streamable_connection_cancelled(self):
        """Test connection cancellation scenarios."""
        transport = StreamableHTTPTransport("https://test.example.com")

        with patch('muxi.runtime.services.mcp.handler.streamablehttp_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_client_factory.return_value = mock_client

            # Mock cancellation during connection
            mock_client.connect = AsyncMock(side_effect=asyncio.CancelledError())

            with pytest.raises(MCPCancelledError) as exc_info:
                await transport.connect()

            assert "Streamable HTTP connection attempt was cancelled" in str(exc_info.value)
            assert transport.connected is False

    @pytest.mark.asyncio
    async def test_streamable_tool_execution(self):
        """Test tool execution over Streamable HTTP."""
        transport = StreamableHTTPTransport("https://test.example.com")

        # Mock connected state
        transport.connected = True
        transport.client = AsyncMock()

        # Mock successful tool execution
        expected_response = {
            "result": "test output",
            "status": "success"
        }
        transport.client.send_request = AsyncMock(return_value=expected_response)

        request_obj = {
            "method": "test_tool",
            "params": {"arg1": "value1"},
            "id": "test-request-123"
        }

        result = await transport.send_request(request_obj)

        assert result == expected_response
        assert transport.connection_stats['requests_sent'] == 1
        assert transport.connection_stats['responses_received'] == 1
        assert transport.last_activity is not None

    @pytest.mark.asyncio
    async def test_streamable_error_handling(self):
        """Test error scenarios specific to Streamable HTTP."""
        transport = StreamableHTTPTransport("https://test.example.com")

        # Test not connected error
        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send_request({"method": "test"})

        assert "Cannot send request: not connected to Streamable HTTP server" in str(exc_info.value)

        # Test with connected but client error
        transport.connected = True
        transport.client = AsyncMock()
        transport.client.send_request = AsyncMock(side_effect=Exception("Server error"))

        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send_request({"method": "test"})

        assert transport.connection_stats['errors_encountered'] == 1

    @pytest.mark.asyncio
    async def test_streamable_request_timeout(self):
        """Test request timeout scenarios."""
        transport = StreamableHTTPTransport("https://test.example.com", request_timeout=1)
        transport.connected = True
        transport.client = AsyncMock()

        # Mock timeout during request
        transport.client.send_request = AsyncMock(side_effect=asyncio.TimeoutError("Request timeout"))

        with pytest.raises(MCPTimeoutError) as exc_info:
            await transport.send_request({"method": "test", "params": {}})

        assert "Streamable HTTP request timed out" in str(exc_info.value)
        assert transport.connection_stats['errors_encountered'] == 1

    @pytest.mark.asyncio
    async def test_streamable_request_cancellation(self):
        """Test request cancellation with cancellation token."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Create and cancel the token
        token = CancellationToken()
        token.cancel()

        with pytest.raises(MCPCancelledError):
            await transport.send_request({"method": "test"}, cancellation_token=token)

    @pytest.mark.asyncio
    async def test_structured_output_support(self):
        """Test MCP 2025-06-18 structured output format."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Mock structured response object
        mock_response = Mock()
        mock_response.content = "Structured tool output"
        mock_response.isError = False
        mock_response.links = [{"href": "https://example.com/resource", "rel": "related"}]
        mock_response._meta = {"version": "2025-06-18", "type": "structured"}

        transport.client.send_request = AsyncMock(return_value=mock_response)

        result = await transport.send_request({"method": "test_tool", "params": {}})

        # Should return structured format
        assert "result" in result
        assert result["result"]["content"] == "Structured tool output"
        assert result["result"]["isError"] is False
        assert len(result["result"]["links"]) == 1
        assert result["result"]["_meta"]["version"] == "2025-06-18"
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_resource_links_handling(self):
        """Test resource links in tool results."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Mock response with resource links
        mock_response = Mock()
        mock_response.content = "Result with resource links"
        mock_response.isError = False
        mock_response.links = [
            {"href": "https://example.com/doc1", "rel": "documentation"},
            {"href": "https://example.com/api", "rel": "api-reference"}
        ]
        mock_response._meta = {}

        transport.client.send_request = AsyncMock(return_value=mock_response)

        result = await transport.send_request({"method": "test_tool", "params": {}})

        assert len(result["result"]["links"]) == 2
        assert result["result"]["links"][0]["rel"] == "documentation"
        assert result["result"]["links"][1]["rel"] == "api-reference"

    @pytest.mark.asyncio
    async def test_elicitation_request_processing(self):
        """Test server elicitation request handling."""
        # This test would require a mock server that sends elicitation requests
        # For now, we'll test the response structure for elicitation data
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Mock elicitation response
        mock_response = Mock()
        mock_response.content = {
            "type": "elicitation",
            "prompt": "Please provide additional context",
            "fields": ["user_context", "preferences"],
            "required": ["user_context"]
        }
        mock_response.isError = False
        mock_response.links = []
        mock_response._meta = {"elicitation_id": "elicit-123"}

        transport.client.send_request = AsyncMock(return_value=mock_response)

        result = await transport.send_request({"method": "get_user_info", "params": {}})

        assert result["result"]["content"]["type"] == "elicitation"
        assert "user_context" in result["result"]["content"]["fields"]
        assert result["result"]["_meta"]["elicitation_id"] == "elicit-123"

    @pytest.mark.asyncio
    async def test_streamable_performance_characteristics(self):
        """Benchmark Streamable HTTP performance."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Mock fast response
        transport.client.send_request = AsyncMock(return_value={"result": "fast response"})

        # Measure request timing
        start_time = time.time()
        await transport.send_request({"method": "test", "params": {}})
        request_time = time.time() - start_time

        # Should be very fast with mocked client
        assert request_time < 0.1  # Less than 100ms

        # Verify connection stats
        stats = transport.get_connection_stats()
        assert stats["transport_type"] == "streamable_http"
        assert stats["protocol_version"] == "2025-03-26"
        assert stats["requests_sent"] == 1
        assert stats["responses_received"] == 1

        # Test efficiency metrics
        assert "success_rate" in stats
        assert stats["success_rate"] == 1.0  # 100% success rate

    @pytest.mark.asyncio
    async def test_disconnect_handling(self):
        """Test proper disconnect handling."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()
        transport.connect_time = datetime.now()

        # Mock successful disconnect
        transport.client.disconnect = AsyncMock()

        result = await transport.disconnect()

        assert result is True
        assert transport.connected is False
        assert transport.client is None

        # Test disconnect when already disconnected
        result = await transport.disconnect()
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_request_objects(self):
        """Test handling of invalid request objects."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.client = AsyncMock()

        # Test invalid request object type
        with pytest.raises(MCPRequestError) as exc_info:
            await transport.send_request("invalid_request_string")

        assert "Invalid request object" in str(exc_info.value)

    def test_connection_stats_format(self):
        """Test connection statistics format and content."""
        transport = StreamableHTTPTransport("https://test.example.com")
        transport.connected = True
        transport.connect_time = datetime.now()
        transport.last_activity = datetime.now()
        transport.connection_stats = {
            'requests_sent': 5,
            'responses_received': 4,
            'errors_encountered': 1,
            'bytes_sent': 1024,
            'bytes_received': 2048
        }

        stats = transport.get_connection_stats()

        # Verify required fields
        assert stats["transport_type"] == "streamable_http"
        assert stats["protocol_version"] == "2025-03-26"
        assert stats["connected"] is True
        assert "connect_time" in stats
        assert "last_activity" in stats
        assert "session_duration_s" in stats

        # Verify efficiency metrics
        assert stats["success_rate"] == 0.8  # 4/5 success rate
        assert stats["avg_bytes_per_request"] == 204.8  # 1024/5
        assert stats["avg_bytes_per_response"] == 512.0  # 2048/4
