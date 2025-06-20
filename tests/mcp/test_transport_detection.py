# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Transport Detection Tests
# Description:  Test suite for intelligent MCP transport detection
# Role:         Validates automatic transport selection and fallback logic
# Usage:        Run via pytest to verify transport detection implementation
# Author:       Muxi Framework Team
#
# This test suite validates the transport detection implementation
# for intelligent selection between MCP transport types. Tests include:
#
# 1. Auto-Detection Logic
#    - Streamable HTTP detection
#    - HTTP+SSE fallback detection
#    - Transport selection priority
#
# 2. Timeout and Error Handling
#    - Detection timeout scenarios
#    - Connection failure handling
#    - Graceful degradation
#
# 3. Fallback Behavior Integration
#    - End-to-end fallback in MCPService
#    - Transport preference ordering
#    - Error recovery mechanisms
#
# This test suite implements the testing strategy specified in the
# Streamable HTTP implementation plan Phase 3.1.
# =============================================================================

import sys
import os
import asyncio
from unittest.mock import AsyncMock, patch

# Add the source directory to Python path for importing muxi modules
if os.path.join(os.path.dirname(__file__), '../../src') not in sys.path:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.runtime.services.mcp.transports import TransportDetector
from muxi.runtime.services.mcp.handler import MCPConnectionError


class TestTransportDetection:
    """Tests for intelligent transport detection."""

    async def test_auto_detection_streamable(self):
        """Test detection of Streamable HTTP support."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            # Mock successful Streamable HTTP detection
            mock_streamable.return_value = True
            mock_sse.return_value = False  # Shouldn't be called, but just in case

            result = await TransportDetector.detect_best_transport("https://test.example.com")

            assert result == "streamable_http"
            mock_streamable.assert_called_once_with("https://test.example.com", 10)
            # SSE test should not be called since Streamable HTTP succeeded
            mock_sse.assert_not_called()

    async def test_auto_detection_http_sse(self):
        """Test fallback to HTTP+SSE detection."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            # Mock Streamable HTTP failure, HTTP+SSE success
            mock_streamable.return_value = False
            mock_sse.return_value = True

            result = await TransportDetector.detect_best_transport("https://test.example.com")

            assert result == "http_sse"
            mock_streamable.assert_called_once_with("https://test.example.com", 10)
            mock_sse.assert_called_once_with("https://test.example.com", 10)

    async def test_detection_no_supported_transport(self):
        """Test detection when no transport is supported."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            # Mock both transports failing
            mock_streamable.return_value = False
            mock_sse.return_value = False

            try:
                await TransportDetector.detect_best_transport("https://test.example.com")
                assert False, "Should have raised MCPConnectionError"
            except MCPConnectionError as e:
                assert "doesn't support any known MCP transport" in str(e)
                assert "tested_transports" in e.details
                assert e.details["tested_transports"] == ["streamable_http", "http_sse"]

    async def test_detection_timeout_handling(self):
        """Test detection timeout scenarios."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            # Mock timeout during Streamable HTTP test
            mock_streamable.return_value = False  # Timeout should result in False
            mock_sse.return_value = True

            # Test with short timeout
            result = await TransportDetector.detect_best_transport("https://test.example.com", timeout=1)

            assert result == "http_sse"
            mock_streamable.assert_called_once_with("https://test.example.com", 1)
            mock_sse.assert_called_once_with("https://test.example.com", 1)

    async def test_streamable_http_detection_logic(self):
        """Test the internal Streamable HTTP detection logic."""

        with patch('muxi.runtime.services.mcp.transport_detector.streamablehttp_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_client_factory.return_value = mock_client

            # Mock successful connection
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()

            result = await TransportDetector._test_streamable_http("https://test.example.com", 10)

            assert result is True
            mock_client_factory.assert_called_once_with(url="https://test.example.com", timeout=10)
            mock_client.connect.assert_called_once()
            mock_client.disconnect.assert_called_once()

    async def test_streamable_http_detection_failure(self):
        """Test Streamable HTTP detection failure scenarios."""

        with patch('muxi.runtime.services.mcp.transport_detector.streamablehttp_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_client_factory.return_value = mock_client

            # Mock connection failure
            mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

            result = await TransportDetector._test_streamable_http("https://test.example.com", 10)

            assert result is False
            mock_client_factory.assert_called_once()
            mock_client.connect.assert_called_once()

    async def test_streamable_http_detection_timeout(self):
        """Test Streamable HTTP detection timeout."""

        with patch('muxi.runtime.services.mcp.transport_detector.streamablehttp_client') as mock_client_factory:
            mock_client = AsyncMock()
            mock_client_factory.return_value = mock_client

            # Mock timeout during connection
            mock_client.connect = AsyncMock(side_effect=asyncio.TimeoutError("Connection timeout"))

            result = await TransportDetector._test_streamable_http("https://test.example.com", 5)

            assert result is False

    async def test_http_sse_detection_logic(self):
        """Test the internal HTTP+SSE detection logic."""

        with patch('muxi.runtime.services.mcp.transport_detector.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock successful SSE endpoint response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            result = await TransportDetector._test_http_sse("https://test.example.com", 10)

            assert result is True
            # Verify the correct SSE endpoint was tested
            mock_client.get.assert_called_once_with(
                "https://test.example.com/sse",
                headers={"Accept": "text/event-stream"}
            )

    async def test_http_sse_detection_failure(self):
        """Test HTTP+SSE detection failure scenarios."""

        with patch('muxi.runtime.services.mcp.transport_detector.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock 404 response (SSE endpoint not found)
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_client.get.return_value = mock_response

            result = await TransportDetector._test_http_sse("https://test.example.com", 10)

            assert result is False

    async def test_http_sse_detection_exception(self):
        """Test HTTP+SSE detection with connection exception."""

        with patch('muxi.runtime.services.mcp.transport_detector.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock connection exception
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))

            result = await TransportDetector._test_http_sse("https://test.example.com", 10)

            assert result is False

    async def test_url_path_handling(self):
        """Test proper URL path handling for different endpoint formats."""

        # Test URL with trailing slash
        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable:
            mock_streamable.return_value = True

            await TransportDetector.detect_best_transport("https://test.example.com/")

            mock_streamable.assert_called_once_with("https://test.example.com/", 10)

        # Test URL with path
        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable:
            mock_streamable.return_value = True

            await TransportDetector.detect_best_transport("https://test.example.com/api/mcp")

            mock_streamable.assert_called_once_with("https://test.example.com/api/mcp", 10)

    async def test_custom_timeout_parameter(self):
        """Test detection with custom timeout values."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            mock_streamable.return_value = True

            # Test with custom timeout
            await TransportDetector.detect_best_transport("https://test.example.com", timeout=30)

            mock_streamable.assert_called_once_with("https://test.example.com", 30)

    async def test_detection_priority_order(self):
        """Test that Streamable HTTP is always tested first."""

        call_order = []

        async def mock_streamable(*args):
            call_order.append("streamable")
            return False

        async def mock_sse(*args):
            call_order.append("sse")
            return True

        with patch.object(TransportDetector, '_test_streamable_http', side_effect=mock_streamable), \
             patch.object(TransportDetector, '_test_http_sse', side_effect=mock_sse):

            result = await TransportDetector.detect_best_transport("https://test.example.com")

            assert result == "http_sse"
            assert call_order == ["streamable", "sse"]

    async def test_concurrent_detection_calls(self):
        """Test that multiple concurrent detection calls work correctly."""

        with patch.object(TransportDetector, '_test_streamable_http') as mock_streamable, \
             patch.object(TransportDetector, '_test_http_sse') as mock_sse:

            mock_streamable.return_value = True
            mock_sse.return_value = False

            # Run multiple detections concurrently
            tasks = [
                TransportDetector.detect_best_transport("https://test1.example.com"),
                TransportDetector.detect_best_transport("https://test2.example.com"),
                TransportDetector.detect_best_transport("https://test3.example.com")
            ]

            results = await asyncio.gather(*tasks)

            # All should succeed with streamable_http
            assert all(result == "streamable_http" for result in results)

            # Each URL should have been tested
            assert mock_streamable.call_count == 3
            assert mock_sse.call_count == 0  # No fallback needed
