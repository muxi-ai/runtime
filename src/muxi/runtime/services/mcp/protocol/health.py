"""MCP Health monitoring implementation."""

import time
import asyncio
import logging
from typing import Dict, Any, List
from ..transports.base import BaseTransport
from .message_handler import MCPMessageHandler

logger = logging.getLogger(__name__)


class MCPHealthMonitor:
    """MCP Health monitoring using ping protocol and connection status."""

    def __init__(self):
        """Initialize health monitor."""
        self.message_handler = MCPMessageHandler()
        self.health_history: Dict[str, List[Dict[str, Any]]] = {}

    async def ping(
        self,
        transport: BaseTransport,
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Ping MCP server to check responsiveness.

        Args:
            transport: MCP transport to use for communication
            timeout: Timeout for ping request in seconds

        Returns:
            Ping result with timing and status information

        Raises:
            MCPRequestError: If ping fails
        """
        start_time = time.time()

        try:
            # Create ping request
            request = self.message_handler.create_request("ping", {})

            # Send ping with timeout
            response = await asyncio.wait_for(
                transport.send_message(request),
                timeout=timeout
            )

            # Calculate timing
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # Convert to milliseconds

            # Validate response
            self.message_handler.validate_response(response)

            # Extract result (ping response is typically empty)
            result = response.get("result", {})

            return {
                "success": True,
                "response_time_ms": response_time,
                "timestamp": end_time,
                "result": result
            }

        except asyncio.TimeoutError:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000

            return {
                "success": False,
                "error": "Ping timeout",
                "response_time_ms": response_time,
                "timestamp": end_time,
                "timeout": timeout
            }

        except Exception as e:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000

            return {
                "success": False,
                "error": str(e),
                "response_time_ms": response_time,
                "timestamp": end_time
            }

    async def check_server_health(
        self,
        transport: BaseTransport,
        server_id: str = None
    ) -> Dict[str, Any]:
        """Comprehensive health check for MCP server.

        Args:
            transport: MCP transport to use for communication
            server_id: Optional server ID for tracking

        Returns:
            Comprehensive health status
        """
        health_status = {
            "server_id": server_id,
            "timestamp": time.time(),
            "overall_status": "unknown",
            "ping_result": None,
            "connection_status": "unknown",
            "capabilities": [],
            "errors": []
        }

        try:
            # Check basic connectivity with ping
            ping_result = await self.ping(transport, timeout=5.0)
            health_status["ping_result"] = ping_result

            if ping_result["success"]:
                health_status["connection_status"] = "connected"

                # Try to get server capabilities/info
                try:
                    await self._check_capabilities(transport, health_status)
                except Exception as e:
                    health_status["errors"].append(f"Capability check failed: {e}")

                # Determine overall status
                if health_status["errors"]:
                    health_status["overall_status"] = "degraded"
                else:
                    health_status["overall_status"] = "healthy"
            else:
                health_status["connection_status"] = "disconnected"
                health_status["overall_status"] = "unhealthy"
                health_status["errors"].append(f"Ping failed: {ping_result.get('error', 'Unknown error')}")

        except Exception as e:
            health_status["connection_status"] = "error"
            health_status["overall_status"] = "unhealthy"
            health_status["errors"].append(f"Health check failed: {e}")

        # Store in history if server_id provided
        if server_id:
            self._store_health_history(server_id, health_status)

        return health_status

    async def _check_capabilities(
        self,
        transport: BaseTransport,
        health_status: Dict[str, Any]
    ) -> None:
        """Check server capabilities by testing common MCP methods.

        Args:
            transport: MCP transport to use
            health_status: Health status dict to update
        """
        capabilities = []

        # Test tools capability
        try:
            tools_request = self.message_handler.create_request("tools/list", {})
            await asyncio.wait_for(transport.send_message(tools_request), timeout=5.0)
            capabilities.append("tools")
        except Exception as e:
            logger.debug(f"Tools capability check failed: {type(e).__name__}: {e}")
            pass

        # Test resources capability
        try:
            resources_request = self.message_handler.create_request("resources/list", {})
            await asyncio.wait_for(transport.send_message(resources_request), timeout=5.0)
            capabilities.append("resources")
        except Exception as e:
            logger.debug(f"Resources capability check failed: {type(e).__name__}: {e}")
            pass

        # Test prompts capability
        try:
            prompts_request = self.message_handler.create_request("prompts/list", {})
            await asyncio.wait_for(transport.send_message(prompts_request), timeout=5.0)
            capabilities.append("prompts")
        except Exception as e:
            logger.debug(f"Prompts capability check failed: {type(e).__name__}: {e}")
            pass

        # Test sampling capability
        try:
            # This is a more complex check, so we just test if the method exists
            # by sending a minimal request that should fail gracefully
            sampling_request = self.message_handler.create_request("sampling/createMessage", {
                "messages": [{"role": "user", "content": "test"}]
            })
            await asyncio.wait_for(transport.send_message(sampling_request), timeout=5.0)
            # If we get a response (even an error), the capability exists
            capabilities.append("sampling")
        except Exception as e:
            logger.debug(f"Sampling capability check failed: {type(e).__name__}: {e}")
            pass

        health_status["capabilities"] = capabilities

    def _store_health_history(
        self,
        server_id: str,
        health_status: Dict[str, Any]
    ) -> None:
        """Store health status in history.

        Args:
            server_id: Server identifier
            health_status: Health status to store
        """
        if server_id not in self.health_history:
            self.health_history[server_id] = []

        # Add to history
        self.health_history[server_id].append(health_status)

        # Keep only last 50 entries
        if len(self.health_history[server_id]) > 50:
            self.health_history[server_id] = self.health_history[server_id][-50:]

    def get_health_history(
        self,
        server_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get health history for a server.

        Args:
            server_id: Server identifier
            limit: Maximum number of entries to return

        Returns:
            List of recent health status entries
        """
        if server_id not in self.health_history:
            return []

        return self.health_history[server_id][-limit:]

    def get_health_summary(
        self,
        server_id: str
    ) -> Dict[str, Any]:
        """Get health summary for a server.

        Args:
            server_id: Server identifier

        Returns:
            Health summary with statistics
        """
        history = self.health_history.get(server_id, [])

        if not history:
            return {
                "server_id": server_id,
                "status": "no_data",
                "checks_count": 0
            }

        # Calculate statistics
        recent_checks = history[-10:]  # Last 10 checks
        successful_pings = len([h for h in recent_checks if h.get("ping_result", {}).get("success", False)])
        healthy_checks = len([h for h in recent_checks if h.get("overall_status") == "healthy"])

        # Calculate average response time
        response_times = [
            h.get("ping_result", {}).get("response_time_ms", 0)
            for h in recent_checks
            if h.get("ping_result", {}).get("success", False)
        ]

        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # Get latest status
        latest = history[-1]

        return {
            "server_id": server_id,
            "latest_status": latest.get("overall_status", "unknown"),
            "latest_timestamp": latest.get("timestamp", 0),
            "checks_count": len(history),
            "success_rate": successful_pings / len(recent_checks) if recent_checks else 0,
            "health_rate": healthy_checks / len(recent_checks) if recent_checks else 0,
            "avg_response_time_ms": avg_response_time,
            "capabilities": latest.get("capabilities", []),
            "recent_errors": [
                error for h in recent_checks[-3:]  # Last 3 checks
                for error in h.get("errors", [])
            ]
        }

    async def monitor_server_health(
        self,
        transport: BaseTransport,
        server_id: str,
        interval: float = 60.0,
        max_checks: int = None
    ) -> None:
        """Continuously monitor server health.

        Args:
            transport: MCP transport to use
            server_id: Server identifier
            interval: Check interval in seconds
            max_checks: Maximum number of checks (None for infinite)
        """
        checks_performed = 0

        while max_checks is None or checks_performed < max_checks:
            try:
                await self.check_server_health(transport, server_id)
                checks_performed += 1

                if max_checks is None or checks_performed < max_checks:
                    await asyncio.sleep(interval)

            except Exception as e:
                # Log error but continue monitoring
                print(f"Health monitoring error for {server_id}: {e}")
                await asyncio.sleep(interval)

    def clear_health_history(self, server_id: str = None) -> None:
        """Clear health history.

        Args:
            server_id: Server to clear history for (None for all servers)
        """
        if server_id:
            if server_id in self.health_history:
                del self.health_history[server_id]
        else:
            self.health_history.clear()

    def format_health_status(self, health_status: Dict[str, Any]) -> str:
        """Format health status for human readability.

        Args:
            health_status: Health status dict

        Returns:
            Formatted health status string
        """
        server_id = health_status.get("server_id", "Unknown")
        overall_status = health_status.get("overall_status", "unknown")
        timestamp = health_status.get("timestamp", 0)

        # Status emoji
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
            "unknown": "❓"
        }.get(overall_status, "❓")

        lines = [
            f"{status_emoji} Server: {server_id}",
            f"Status: {overall_status.upper()}",
            f"Checked: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}"
        ]

        # Ping information
        ping_result = health_status.get("ping_result")
        if ping_result:
            if ping_result.get("success"):
                response_time = ping_result.get("response_time_ms", 0)
                lines.append(f"Ping: {response_time:.1f}ms")
            else:
                error = ping_result.get("error", "Failed")
                lines.append(f"Ping: {error}")

        # Capabilities
        capabilities = health_status.get("capabilities", [])
        if capabilities:
            lines.append(f"Capabilities: {', '.join(capabilities)}")

        # Errors
        errors = health_status.get("errors", [])
        if errors:
            lines.append(f"Errors: {len(errors)}")
            for error in errors[:2]:  # Show first 2 errors
                lines.append(f"  • {error}")

        return "\n".join(lines)
