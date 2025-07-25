"""
Test for real MCP SDK implementation.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.muxi.services.mcp.protocol.message_handler import MCPMessageHandler
from src.muxi.services.mcp.transports.streamable import StreamableHTTPTransport
from src.muxi.services.mcp.transports.http_sse import HTTPSSETransport
from src.muxi.services.mcp.transports.command import CommandLineTransport


class TestMCPMessageHandler:
    """Test real MCP message handler."""

    def test_create_request(self):
        """Test creating proper MCP request."""
        handler = MCPMessageHandler()

        message = handler.create_request("test_method", {"param1": "value1"})

        assert message is not None
        assert hasattr(message, 'message')
        assert message.message.method == "test_method"
        assert message.message.params == {"param1": "value1"}

    def test_create_notification(self):
        """Test creating MCP notification."""
        handler = MCPMessageHandler()

        message = handler.create_notification("notify", {"data": "test"})

        assert message is not None
        assert hasattr(message, 'message')
        assert message.message["method"] == "notify"
        assert message.message["params"] == {"data": "test"}

    def test_validate_request(self):
        """Test request validation."""
        handler = MCPMessageHandler()

        # Valid request
        valid_request = {
            "jsonrpc": "2.0",
            "method": "test_method",
            "id": "123"
        }
        assert handler.validate_request(valid_request) is True

        # Invalid request - missing method
        invalid_request = {
            "jsonrpc": "2.0",
            "id": "123"
        }
        assert handler.validate_request(invalid_request) is False

    def test_format_error_response(self):
        """Test error response formatting."""
        handler = MCPMessageHandler()

        error_response = handler.format_error_response(
            "123", -32600, "Invalid Request", {"detail": "test"}
        )

        assert error_response["jsonrpc"] == "2.0"
        assert error_response["id"] == "123"
        assert error_response["error"]["code"] == -32600
        assert error_response["error"]["message"] == "Invalid Request"
        assert error_response["error"]["data"]["detail"] == "test"


class TestStreamableHTTPTransport:
    """Test real MCP streamable HTTP transport."""

    @pytest.fixture
    def transport(self):
        """Create transport instance."""
        return StreamableHTTPTransport("http://localhost:8002")

    def test_initialization(self, transport):
        """Test transport initialization."""
        assert transport.url == "http://localhost:8002"
        assert transport.message_handler is not None
        assert transport.session_id is None
        assert not transport.connected

    @patch('src.muxi.services.mcp.transports.streamable.streamablehttp_client')
    async def test_connect_success(self, mock_client, transport):
        """Test successful connection."""
        # Mock the context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=(
            AsyncMock(),  # read_stream
            AsyncMock(),  # write_stream
            "session_123"  # session_id
        ))
        mock_client.return_value = mock_session

        result = await transport.connect()

        assert result is True
        assert transport.connected is True
        assert transport.session_id is not None

    @patch('src.muxi.services.mcp.transports.streamable.streamablehttp_client')
    async def test_connect_failure(self, mock_client, transport):
        """Test connection failure."""
        mock_client.side_effect = Exception("Connection failed")

        with pytest.raises(Exception) as exc_info:
            await transport.connect()

        assert "Failed to connect to MCP server" in str(exc_info.value)
        assert not transport.connected


class TestHTTPSSETransport:
    """Test real MCP HTTP+SSE transport."""

    @pytest.fixture
    def transport(self):
        """Create transport instance."""
        return HTTPSSETransport("http://localhost:8001")

    def test_initialization(self, transport):
        """Test transport initialization."""
        assert transport.url == "http://localhost:8001"
        assert transport.message_handler is not None
        assert transport.session is None
        assert not transport.connected

    @patch('src.muxi.services.mcp.transports.http_sse.sse_client')
    async def test_connect_success(self, mock_client, transport):
        """Test successful connection."""
        # Mock the context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=(
            AsyncMock(),  # read_stream
            AsyncMock()   # write_stream
        ))
        mock_client.return_value = mock_session

        result = await transport.connect()

        assert result is True
        assert transport.connected is True
        assert transport.session is not None


class TestCommandLineTransport:
    """Test real MCP STDIO transport."""

    @pytest.fixture
    def transport(self):
        """Create transport instance."""
        return CommandLineTransport("python", ["test_server.py"])

    def test_initialization(self, transport):
        """Test transport initialization."""
        assert transport.command == "python"
        assert transport.args == ["test_server.py"]
        assert transport.message_handler is not None
        assert transport.session is None
        assert not transport.connected

    @patch('src.muxi.services.mcp.transports.command.stdio_client')
    async def test_connect_success(self, mock_client, transport):
        """Test successful connection."""
        # Mock the context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=(
            AsyncMock(),  # read_stream
            AsyncMock()   # write_stream
        ))
        mock_client.return_value = mock_session

        result = await transport.connect()

        assert result is True
        assert transport.connected is True
        assert transport.session is not None


class TestRealMCPIntegration:
    """Integration tests for real MCP implementation."""

    @pytest.mark.asyncio
    async def test_end_to_end_message_flow(self):
        """Test complete message flow through real MCP components."""
        # This would test with actual MCP servers
        # For now, just verify components work together

        handler = MCPMessageHandler()
        transport = StreamableHTTPTransport("http://localhost:8002")

        # Create a request
        request = handler.create_request("list_tools", {})

        # Verify request structure
        assert request is not None
        assert hasattr(request, 'message')
        assert request.message.method == "list_tools"

        # Transport should be able to handle the request format
        assert transport.message_handler is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
