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
# 1. Transport Detection with Caching
#    - Tests Streamable HTTP support (preferred)
#    - Falls back to HTTP+SSE if needed
#    - Caches successful transport choices for performance
#
# 2. Protocol Testing (No MCP SDK Dependencies)
#    - Direct HTTP connection tests for each transport type
#    - Fast timeout-based detection
#    - Graceful error handling with detailed diagnostics
#
# 3. Intelligent Selection Strategy
#    - Priority order: Streamable HTTP > HTTP+SSE
#    - URL pattern recognition and smart defaults
#    - Comprehensive error reporting with fallback paths
#
# 4. Developer Experience
#    - Single URL input from developer
#    - Automatic transport selection and caching
#    - Seamless fallback without manual intervention
#
# This module implements the enhanced transport detection logic for Phase 4.1
# of the MCP implementation plan.
# =============================================================================

import aiohttp
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
import hashlib

from .base import MCPConnectionError


class TransportCache:
    """
    Cache for successful transport connections to improve performance.
    """

    def __init__(self, cache_ttl_minutes: int = 60):
        """
        Initialize transport cache.

        Args:
            cache_ttl_minutes: Cache TTL in minutes (default: 60)
        """
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def get_cached_transport(self, url: str) -> Optional[str]:
        """
        Get cached transport for URL if still valid.

        Args:
            url: Server URL

        Returns:
            Cached transport type or None if not cached/expired
        """
        cache_key = self._get_cache_key(url)

        if cache_key in self._cache:
            entry = self._cache[cache_key]

            # Check if cache entry is still valid
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - cached_time < self._cache_ttl:
                return entry["transport_type"]
            else:
                # Cache expired, remove entry
                del self._cache[cache_key]

        return None

    def cache_transport(
        self, url: str, transport_type: str, metadata: Optional[Dict] = None
    ) -> None:
        """
        Cache successful transport connection.

        Args:
            url: Server URL
            transport_type: Successful transport type
            metadata: Optional metadata about the connection
        """
        cache_key = self._get_cache_key(url)

        self._cache[cache_key] = {
            "url": url,
            "transport_type": transport_type,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

    def clear_cache(self) -> None:
        """Clear all cached transport data."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        valid_entries = 0
        expired_entries = 0

        for entry in self._cache.values():
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - cached_time < self._cache_ttl:
                valid_entries += 1
            else:
                expired_entries += 1

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": expired_entries,
            "cache_ttl_minutes": self._cache_ttl.total_seconds() / 60,
        }


class TransportDetector:
    """
    Intelligent transport detection and selection for MCP servers.

    Features:
    - Automatic transport detection with caching
    - Smart URL pattern recognition
    - Seamless fallback between transport types
    - No broken MCP SDK dependencies
    """

    # Singleton cache instance
    _cache = TransportCache()

    @staticmethod
    async def detect_best_transport(
        url: str,
        timeout: int = 10,
        use_cache: bool = True,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Detect the best available transport for an MCP server.

        Strategy:
        1. Check cache for previously successful transport
        2. Try Streamable HTTP first (preferred for new connections)
        3. Fall back to HTTP+SSE if streamable fails
        4. Cache successful transport for future use

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for each transport test
            use_cache: Whether to use cached transport results
            credentials: Optional authentication credentials for the server

        Returns:
            Transport type string ("streamable_http" or "http_sse")

        Raises:
            MCPConnectionError: If no supported transport is found
        """

        # Check cache first if enabled
        if use_cache:
            cached_transport = TransportDetector._cache.get_cached_transport(url)
            if cached_transport:
                return cached_transport

        # Smart URL pattern recognition for quick detection
        detected_transport = TransportDetector._detect_from_url_pattern(url)
        if detected_transport:
            # If we can detect from URL pattern, test that transport first
            if await TransportDetector._test_transport(
                url, detected_transport, timeout, credentials
            ):
                TransportDetector._cache.cache_transport(
                    url, detected_transport, {"detection_method": "url_pattern"}
                )
                return detected_transport

        # Try all transports in priority order
        transports_to_try = ["streamable_http", "http_sse"]

        for transport_type in transports_to_try:
            if await TransportDetector._test_transport(url, transport_type, timeout, credentials):
                # Cache successful transport
                TransportDetector._cache.cache_transport(
                    url, transport_type, {"detection_method": "connection_test"}
                )
                return transport_type

        # No transport worked
        raise MCPConnectionError(
            f"Server {url} doesn't support any known MCP transport",
            {
                "tested_transports": transports_to_try,
                "url": url,
                "timestamp": datetime.now().isoformat(),
                "suggestion": "Verify server is running and supports MCP protocol",
            },
        )

    @staticmethod
    def _detect_from_url_pattern(url: str) -> Optional[str]:
        """
        Detect transport type from URL patterns.

        Args:
            url: Server URL

        Returns:
            Transport type if detectable from URL, None otherwise
        """
        url_lower = url.lower()

        # Known patterns for specific transport types
        if "/sse" in url_lower or ":8001" in url_lower:
            return "http_sse"
        elif "/mcp" in url_lower or ":8002" in url_lower:
            return "streamable_http"

        return None

    @staticmethod
    async def _test_transport(
        url: str, transport_type: str, timeout: int, credentials: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Test a specific transport type against a URL.

        Args:
            url: Server URL
            transport_type: Transport type to test
            timeout: Timeout in seconds
            credentials: Optional authentication credentials for the server

        Returns:
            True if transport is supported, False otherwise
        """
        if transport_type == "streamable_http":
            return await TransportDetector._test_streamable_http(url, timeout, credentials)
        elif transport_type == "http_sse":
            return await TransportDetector._test_http_sse(url, timeout, credentials)
        else:
            return False

    @staticmethod
    def _build_auth_headers(
        credentials: Optional[Dict[str, Any]], base_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Build authentication headers from credentials.

        Args:
            credentials: Credential configuration with type and authentication details
            base_headers: Base headers to extend (optional)

        Returns:
            Dictionary of headers including authentication if credentials provided
        """
        headers = base_headers.copy() if base_headers else {}

        if credentials:
            auth_type = credentials.get("type", "bearer").lower()
            if auth_type == "bearer" and "token" in credentials:
                headers["Authorization"] = f"Bearer {credentials['token']}"
            elif auth_type == "api_key":
                if "header_name" in credentials:
                    headers[credentials["header_name"]] = credentials["key"]
                else:
                    headers["X-API-Key"] = credentials.get("key", "")

        return headers

    @staticmethod
    async def _test_streamable_http(
        url: str, timeout: int, credentials: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Test Streamable HTTP transport using direct HTTP communication.

        NOTE: Does not use broken MCP SDK streamablehttp_client.

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for the test
            credentials: Optional authentication credentials for the server

        Returns:
            True if Streamable HTTP is supported, False otherwise
        """
        try:
            # Ensure URL has /mcp endpoint for streamable servers
            test_url = url.rstrip("/")
            if not test_url.endswith("/mcp"):
                test_url += "/mcp"

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                # Test with a simple JSON-RPC ping request
                test_request = {
                    "jsonrpc": "2.0",
                    "id": "transport_test",
                    "method": "ping",
                    "params": {},
                }

                # Build headers with authentication if provided
                headers = TransportDetector._build_auth_headers(
                    credentials, base_headers={"Content-Type": "application/json"}
                )

                async with session.post(test_url, json=test_request, headers=headers) as response:
                    # Accept any response that's not a hard connection error
                    # Streamable servers should respond to POST requests
                    return response.status in [200, 400, 404, 405]  # Not 500+ or connection error

        except Exception:
            return False

    @staticmethod
    async def _test_http_sse(
        url: str, timeout: int, credentials: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Test HTTP+SSE transport using direct HTTP communication.

        Args:
            url: The MCP server URL to test
            timeout: Timeout in seconds for the test
            credentials: Optional authentication credentials for the server

        Returns:
            True if HTTP+SSE is supported, False otherwise
        """
        try:
            # Ensure URL has /sse endpoint for SSE servers
            test_url = url.rstrip("/")
            if not test_url.endswith("/sse"):
                test_url += "/sse"

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as session:
                # Build headers with authentication if provided
                headers = TransportDetector._build_auth_headers(
                    credentials, base_headers={"Accept": "text/event-stream"}
                )

                # Test SSE endpoint with proper headers
                async with session.get(test_url, headers=headers) as response:
                    # SSE servers should respond favorably to event-stream requests
                    return response.status in [200, 404]  # Not hard errors

        except Exception:
            return False

    @staticmethod
    async def detect_with_fallback(
        url: str,
        timeout: int = 10,
        use_cache: bool = True,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict]:
        """
        Detect transport with detailed fallback information.

        Args:
            url: Server URL
            timeout: Timeout in seconds
            use_cache: Whether to use cached results
            credentials: Optional authentication credentials for the server

        Returns:
            Tuple of (transport_type, detection_metadata)
        """
        detection_metadata = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "cache_used": False,
            "tests_performed": [],
            "fallback_applied": False,
        }

        try:
            # Check cache first
            if use_cache:
                cached_transport = TransportDetector._cache.get_cached_transport(url)
                if cached_transport:
                    detection_metadata["cache_used"] = True
                    detection_metadata["transport_type"] = cached_transport
                    return cached_transport, detection_metadata

            # Try detection
            transport_type = await TransportDetector.detect_best_transport(
                url, timeout, use_cache=False, credentials=credentials
            )

            detection_metadata["transport_type"] = transport_type
            return transport_type, detection_metadata

        except MCPConnectionError as e:
            detection_metadata["error"] = str(e)
            detection_metadata["fallback_applied"] = True
            raise

    @staticmethod
    def get_cache_stats() -> Dict:
        """Get transport cache statistics."""
        return TransportDetector._cache.get_cache_stats()

    @staticmethod
    def clear_transport_cache() -> None:
        """Clear all cached transport data."""
        TransportDetector._cache.clear_cache()

    @staticmethod
    def get_recommended_url(base_url: str, transport_type: str) -> str:
        """
        Get the recommended URL for a specific transport type.

        Args:
            base_url: Base server URL
            transport_type: Transport type

        Returns:
            Recommended URL with correct endpoint
        """
        base = base_url.rstrip("/")

        if transport_type == "streamable_http":
            return f"{base}/mcp" if not base.endswith("/mcp") else base
        elif transport_type == "http_sse":
            return f"{base}/sse" if not base.endswith("/sse") else base
        else:
            return base
