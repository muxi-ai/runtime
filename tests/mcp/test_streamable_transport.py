"""
Streamable HTTP Transport Tests

PRODUCTION-READY test suite for MCP Streamable HTTP transport.
Tests the ACTUAL implementation with proper mocking.
"""

import sys
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
import json

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

# Import muxi modules after path modification
from muxi.services.mcp.transports.streamable import StreamableHTTPTransport
from muxi.services.mcp.transports.base import (
    MCPConnectionError,
    MCPTimeoutError,
    MCPRequestError,
    MCPCancelledError,
    CancellationToken
)


class TestStreamableHTTPTransport:
    """PRODUCTION-READY tests for Streamable HTTP transport."""

    @pytest.fixture
    def transport(self):
        """Create a test transport instance."""
        return StreamableHTTPTransport("https://test.example.com", request_timeout=30)

    @pytest.mark.asyncio
    async def test_connection_success(self, transport):
        """Test successful connection."""
        with patch('mcp.client.streamable_http.streamablehttp_client') as mock_client:
            # Mock the context manager properly
            mock_context = AsyncMock()
            mock_client.return_value = mock_context

            # Mock the streams returned by __aenter__
            mock_read_stream = AsyncMock()
            mock_write_stream = AsyncMock()
            mock_get_session_id = Mock(return_value="session-123")

            mock_context.__aenter__ = AsyncMock(return_value=(
                mock_read_stream,
                mock_write_stream,
                mock_get_session_id
            ))
            mock_context.__aexit__ = AsyncMock(return_value=None)

            result = await transport.connect()

            assert result is True
            assert transport.connected is True
            assert transport.connect_time is not None
            assert transport.read_stream is mock_read_stream
            assert transport.write_stream is mock_write_stream

    @pytest.mark.asyncio
    async def test_connection_failure(self, transport):
        """Test connection failure handling."""
        with patch('mcp.client.streamable_http.streamablehttp_client') as mock_client:
            # Mock the context manager to raise an exception
            mock_context = AsyncMock()
            mock_client.return_value = mock_context
            mock_context.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))

            with pytest.raises(MCPConnectionError) as exc_info:
                await transport.connect()

            assert "Failed to connect via Streamable HTTP" in str(exc_info.value)
            assert transport.connected is False

    @pytest.mark.asyncio
    async def test_send_request_success(self, transport):
        """Test successful request sending."""
        # Properly mock connected state with streams
        transport.connected = True
        transport.read_stream = AsyncMock()
        transport.write_stream = AsyncMock()

        # Mock the stream operations to return proper responses
        mock_response_data = {"result": "test response", "status": "success"}
        mock_response_json = json.dumps(mock_response_data)
        transport.read_stream.receive = AsyncMock(return_value=mock_response_json.encode('utf-8'))
        transport.write_stream.send = AsyncMock()

        request_obj = {
            "method": "test_tool",
            "params": {"arg1": "value1"}
        }

        result = await transport.send_request(request_obj)

        # Verify the response
        assert result["status"] == "success"
        assert "result" in result

        # Verify stream operations were called
        transport.write_stream.send.assert_called_once()
        transport.read_stream.receive.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_request_not_connected(self, transport):
        """Test request when not connected."""
        request_obj = {"method": "test"}

        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send_request(request_obj)

        assert "Not connected to Streamable HTTP server" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_request_missing_streams(self, transport):
        """Test request when connected but missing streams."""
        transport.connected = True
        # Don't set read_stream or write_stream

        with pytest.raises(MCPConnectionError):
            await transport.send_request({"method": "test"})

    @pytest.mark.asyncio
    async def test_send_request_timeout(self, transport):
        """Test request timeout handling."""
        transport.connected = True
        transport.read_stream = AsyncMock()
        transport.write_stream = AsyncMock()

        # Mock asyncio.wait_for to raise TimeoutError
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()

            with pytest.raises(MCPTimeoutError):
                await transport.send_request({"method": "test"}, timeout=1)

    @pytest.mark.asyncio
    async def test_disconnect_success(self, transport):
        """Test successful disconnection."""
        # Mock connected state with context manager
        transport.connected = True
        transport.context_manager = AsyncMock()
        transport.context_manager.__aexit__ = AsyncMock()

        result = await transport.disconnect()

        assert result is True
        assert transport.connected is False
        assert transport.context_manager is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, transport):
        """Test disconnect when already disconnected."""
        result = await transport.disconnect()
        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_with_exception(self, transport):
        """Test disconnect when cleanup fails."""
        transport.connected = True
        transport.context_manager = AsyncMock()
        transport.context_manager.__aexit__ = AsyncMock(side_effect=Exception("Cleanup failed"))

        result = await transport.disconnect()

        # Should still mark as disconnected even if cleanup fails
        assert result is True
        assert transport.connected is False

    def test_get_connection_stats(self, transport):
        """Test connection statistics."""
        transport.connected = True
        transport.connect_time = datetime.now()
        transport.last_activity = datetime.now()

        stats = transport.get_connection_stats()

        assert stats["transport_type"] == "streamable_http"
        assert stats["protocol_version"] == "2025-03-26"
        assert stats["connected"] is True
        assert "connect_time" in stats
        assert "last_activity" in stats
        assert "session_duration_s" in stats

    @pytest.mark.asyncio
    async def test_cancellation_support(self, transport):
        """Test request cancellation."""
        transport.connected = True
        transport.read_stream = AsyncMock()
        transport.write_stream = AsyncMock()

        # Create cancelled token
        token = CancellationToken()
        token.cancel()

        # The cancellation check happens before the actual request
        with pytest.raises(MCPCancelledError):
            await transport.send_request({"method": "test"}, cancellation_token=token)

    @pytest.mark.asyncio
    async def test_request_validation(self, transport):
        """Test request object validation."""
        transport.connected = True
        transport.read_stream = AsyncMock()
        transport.write_stream = AsyncMock()

        # Test invalid request type
        with pytest.raises(MCPRequestError):
            await transport.send_request("not_a_dict")

        # Test missing method
        with pytest.raises(MCPRequestError):
            await transport.send_request({"params": {}})

    def test_transport_info(self, transport):
        """Test transport information."""
        info = transport.get_transport_info()

        assert info["type"] == "streamable_http"
        assert info["protocol_version"] == "2025-03-26"
        assert info["supports_streaming"] is True
        assert info["supports_cancellation"] is True

    @pytest.mark.asyncio
    async def test_connection_timeout(self, transport):
        """Test connection timeout."""
        with patch('mcp.client.streamable_http.streamablehttp_client') as mock_client:
            mock_context = AsyncMock()
            mock_client.return_value = mock_context
            mock_context.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())

            with pytest.raises(MCPTimeoutError):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_request_with_model_dump(self, transport):
        """Test request with object that has model_dump method."""
        transport.connected = True
        transport.read_stream = AsyncMock()
        transport.write_stream = AsyncMock()

        # Mock the stream operations
        mock_response_data = {"result": "test response"}
        mock_response_json = json.dumps(mock_response_data)
        transport.read_stream.receive = AsyncMock(return_value=mock_response_json.encode('utf-8'))
        transport.write_stream.send = AsyncMock()

        # Mock request object with model_dump
        mock_request = Mock()
        mock_request.model_dump = Mock(return_value={"method": "test", "params": {}})

        result = await transport.send_request(mock_request)

        assert result["status"] == "success"
        mock_request.model_dump.assert_called_once()

    def test_constructor_with_auth(self):
        """Test constructor with authentication."""
        auth = Mock()
        transport = StreamableHTTPTransport(
            "https://test.example.com",
            request_timeout=45,
            auth=auth
        )

        assert transport.url == "https://test.example.com"
        assert transport.request_timeout == 45
        assert transport.auth is auth

    def test_efficiency_metrics(self, transport):
        """Test efficiency metrics calculation."""
        transport.connection_stats = {
            'requests_sent': 10,
            'responses_received': 9,
            'errors_encountered': 1,
            'bytes_sent': 1000,
            'bytes_received': 2000
        }

        stats = transport.get_connection_stats()

        assert stats['success_rate'] == 0.9  # 1 - (1/10)
        assert stats['avg_bytes_per_request'] == 100.0  # 1000/10
        assert stats['avg_bytes_per_response'] == 222.22222222222223  # 2000/9
