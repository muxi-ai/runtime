# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Transport Detector - Intelligent Transport Selection
# Description:  Automatic detection and selection of optimal MCP transport types
# Role:         Determines best available transport for MCP server connections
# Usage:        Used by MCPService to auto-select transport with fallback
# Author:       Muxi Framework Team
#
# The Transport Detector provides intelligent transport detection for MCP servers,
# automatically determining the best available protocol:
#
# 1. Transport Detection
#    - Tests Streamable HTTP support (preferred)
#    - Falls back to HTTP+SSE if needed
#    - Handles connection timeouts and failures
#
# 2. Protocol Testing
#    - Minimal connection tests for each transport type
#    - Fast timeout-based detection
#    - Graceful error handling
#
# 3. Selection Strategy
#    - Priority order: Streamable HTTP > HTTP+SSE
#    - Comprehensive error reporting
#    - Support for manual override
#
# This module implements the transport detection logic specified in the
# Streamable HTTP implementation plan Phase 2.1.
# =============================================================================

import asyncio
import httpx
from datetime import datetime

from .base import MCPConnectionError

# MCP SDK imports - Streamable HTTP available in MCP >=1.9.0
from mcp.client.streamable_http import streamablehttp_client


class TransportDetector:
    """
    Intelligent transport detection and selection for MCP servers.
    """

    @staticmethod
    async def detect_best_transport(url: str, timeout: int = 10) -> str:
        """
        Detect the best available transport for an MCP server.

        Priority Order:
        1. Streamable HTTP (preferred)
        2. HTTP+SSE (fallback)

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for each transport test

        Returns:
            Transport type string ("streamable_http" or "http_sse")

        Raises:
            MCPConnectionError: If no supported transport is found
        """

        # Test Streamable HTTP first (preferred)
        if await TransportDetector._test_streamable_http(url, timeout):
            return "streamable_http"

        # Fall back to HTTP+SSE
        if await TransportDetector._test_http_sse(url, timeout):
            return "http_sse"

        raise MCPConnectionError(
            f"Server {url} doesn't support any known MCP transport",
            {
                "tested_transports": ["streamable_http", "http_sse"],
                "url": url,
                "timestamp": datetime.now().isoformat()
            }
        )

    @staticmethod
    async def _test_streamable_http(url: str, timeout: int) -> bool:
        """
        Quick connectivity test for Streamable HTTP.

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for the test

        Returns:
            True if Streamable HTTP is supported, False otherwise
        """
        try:
            async with asyncio.timeout(timeout):
                # Attempt minimal Streamable HTTP connection
                client = streamablehttp_client(url=url, timeout=timeout)
                await client.connect()

                # Basic connection test - if we got here, it worked
                await client.disconnect()
                return True

        except Exception:
            # Any exception means Streamable HTTP is not supported
            return False

    @staticmethod
    async def _test_http_sse(url: str, timeout: int) -> bool:
        """
        Quick connectivity test for HTTP+SSE.

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for the test

        Returns:
            True if HTTP+SSE is supported, False otherwise
        """
        try:
            async with asyncio.timeout(timeout):
                # Test SSE endpoint availability
                async with httpx.AsyncClient(timeout=timeout) as client:
                    sse_url = f"{url.rstrip('/')}/sse"
                    response = await client.get(sse_url, headers={
                        "Accept": "text/event-stream"
                    })
                    return response.status_code == 200

        except Exception:
            # Any exception means HTTP+SSE is not supported
            return False
