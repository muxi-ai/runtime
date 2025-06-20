"""MCP Health monitoring and capabilities negotiation implementation."""

import asyncio
import datetime
from typing import Dict, Any, Optional, Callable
from ..transports.base import BaseTransport
from ..protocol.message_handler import MCPMessageHandler
from ....datatypes.exceptions import MCPRequestError, MCPTimeoutError


class MCPHealthMonitor:
    """MCP Health monitoring with ping/keepalive functionality."""

    def __init__(self, ping_interval: float = 30.0, timeout: float = 10.0):
        """Initialize health monitor.

        Args:
            ping_interval: Interval between ping requests in seconds
            timeout: Timeout for ping requests in seconds
        """
        self.message_handler = MCPMessageHandler()
        self.ping_interval = ping_interval
        self.timeout = timeout
        self.ping_task: Optional[asyncio.Task] = None
        self.is_monitoring = False
        self.last_ping_time: Optional[float] = None
        self.last_pong_time: Optional[float] = None
        self.ping_count = 0
        self.failed_pings = 0
        self.on_connection_lost: Optional[Callable] = None

    async def ping(self, transport: BaseTransport, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Send ping request to MCP server.

        Args:
            transport: MCP transport to use for communication
            timeout: Optional timeout for ping request

        Returns:
            Ping result with success status and response time

        Raises:
            MCPRequestError: If ping fails
        """
        try:
            # Record start time for response time calculation
            start_time = asyncio.get_event_loop().time()

            # Send ping request to MCP server
            if timeout:
                response = await asyncio.wait_for(
                    transport.send_request({
                        "method": "ping",
                        "params": {}
                    }),
                    timeout=timeout
                )
            else:
                response = await transport.send_request({
                    "method": "ping",
                    "params": {}
                })

            # Calculate response time
            end_time = asyncio.get_event_loop().time()
            response_time_ms = (end_time - start_time) * 1000

            # Update statistics
            self._update_ping_stats(True, response_time_ms)

            # Log successful ping response
            ping_result = response.get("result", {})

            return {
                "success": True,
                "response_time_ms": response_time_ms,
                "timestamp": asyncio.get_event_loop().time(),
                "response": ping_result
            }

        except asyncio.TimeoutError:
            self._update_ping_stats(False, None)
            return {
                "success": False,
                "error": "Ping timeout",
                "timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            self._update_ping_stats(False, None)
            return {
                "success": False,
                "error": str(e),
                "timestamp": asyncio.get_event_loop().time()
            }

    async def start_monitoring(self, transport: BaseTransport, on_connection_lost: Optional[Callable] = None):
        """Start continuous health monitoring with ping.

        Args:
            transport: MCP transport to monitor
            on_connection_lost: Optional callback for connection loss
        """
        if self.is_monitoring:
            raise MCPRequestError("Health monitoring already started")

        self.is_monitoring = True
        self.on_connection_lost = on_connection_lost
        self.ping_task = asyncio.create_task(self._ping_loop(transport))

    async def stop_monitoring(self):
        """Stop health monitoring."""
        self.is_monitoring = False
        if self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass
            self.ping_task = None

    async def _ping_loop(self, transport: BaseTransport):
        """Internal ping loop for continuous monitoring."""
        consecutive_failures = 0
        max_failures = 3

        while self.is_monitoring:
            try:
                # Wait for ping interval
                await asyncio.sleep(self.ping_interval)

                if not self.is_monitoring:
                    break

                # Send ping and check result
                ping_result = await self.ping(transport)

                # Check if ping was actually successful
                if ping_result.get("success", False):
                    consecutive_failures = 0
                else:
                    # Ping failed without raising exception (e.g., timeout)
                    consecutive_failures += 1
                    error_msg = ping_result.get("error", "Unknown ping failure")
                    print(f"Health check failed ({consecutive_failures}/{max_failures}): {error_msg}")

                    # Check if we've failed too many times
                    if consecutive_failures >= max_failures:
                        self.is_monitoring = False
                        if self.on_connection_lost:
                            try:
                                await self.on_connection_lost()
                            except Exception as callback_error:
                                print(f"Error in connection lost callback: {callback_error}")
                        break

            except (MCPRequestError, MCPTimeoutError) as e:
                consecutive_failures += 1
                print(f"Health check failed ({consecutive_failures}/{max_failures}): {e}")

                # If we've failed too many times, consider connection lost
                if consecutive_failures >= max_failures:
                    self.is_monitoring = False
                    if self.on_connection_lost:
                        try:
                            await self.on_connection_lost()
                        except Exception as callback_error:
                            print(f"Error in connection lost callback: {callback_error}")
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Unexpected error in ping loop: {e}")
                await asyncio.sleep(1)  # Brief pause before retrying

    def get_health_stats(self) -> Dict[str, Any]:
        """Get health monitoring statistics.

        Returns:
            Dictionary containing health stats
        """
        stats = {
            "is_monitoring": self.is_monitoring,
            "ping_interval": self.ping_interval,
            "timeout": self.timeout,
            "ping_count": self.ping_count,
            "failed_pings": self.failed_pings,
            "success_rate": 0.0,
            "last_ping_time": self.last_ping_time,
            "last_pong_time": self.last_pong_time,
            "last_rtt_ms": None
        }

        # Calculate success rate
        if self.ping_count > 0:
            stats["success_rate"] = (self.ping_count - self.failed_pings) / self.ping_count

        # Calculate last RTT if we have timing data
        if self.last_ping_time and self.last_pong_time:
            stats["last_rtt_ms"] = (self.last_pong_time - self.last_ping_time) * 1000

        return stats

    def format_health_summary(self) -> str:
        """Format a human-readable health summary.

        Returns:
            Formatted health summary string
        """
        stats = self.get_health_stats()

        status = "🟢 Monitoring" if stats["is_monitoring"] else "🔴 Not monitoring"
        success_rate = stats["success_rate"] * 100

        summary_lines = [
            f"🏥 MCP Health Status: {status}",
            f"📊 Success Rate: {success_rate:.1f}% ({stats['ping_count'] - stats['failed_pings']}/{stats['ping_count']})"
        ]

        if stats["last_rtt_ms"] is not None:
            summary_lines.append(f"⏱️  Last RTT: {stats['last_rtt_ms']:.1f}ms")

        if stats["last_ping_time"]:
            last_ping = datetime.datetime.fromtimestamp(stats["last_ping_time"])
            summary_lines.append(f"🕐 Last ping: {last_ping.strftime('%H:%M:%S')}")

        summary_lines.extend([
            f"⏰ Ping interval: {stats['ping_interval']}s",
            f"⏳ Timeout: {stats['timeout']}s"
        ])

        return "\n".join(summary_lines)

    def _update_ping_stats(self, success: bool, response_time_ms: Optional[float]):
        """Update health monitoring statistics based on ping result.

        Args:
            success: Whether the ping was successful
            response_time_ms: Response time of the ping in milliseconds
        """
        # Always increment total ping count on every attempt
        self.ping_count += 1

        if success:
            self.last_ping_time = asyncio.get_event_loop().time()
            self.last_pong_time = self.last_ping_time + (response_time_ms / 1000) if response_time_ms else None
        else:
            self.failed_pings += 1


class MCPCapabilitiesNegotiator:
    """MCP Capabilities negotiation handler."""

    def __init__(self):
        """Initialize capabilities negotiator."""
        self.message_handler = MCPMessageHandler()

    async def initialize_connection(self, transport: BaseTransport, client_info: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize MCP connection with capabilities negotiation.

        Args:
            transport: MCP transport to use
            client_info: Client information and capabilities

        Returns:
            Server capabilities and information

        Raises:
            MCPRequestError: If initialization fails
        """
        try:
            # Send initialize request
            request = self.message_handler.create_request("initialize", {
                "protocolVersion": client_info.get("protocolVersion", "2024-11-05"),
                "capabilities": client_info.get("capabilities", {}),
                "clientInfo": {
                    "name": client_info.get("name", "MUXI MCP Client"),
                    "version": client_info.get("version", "1.0.0")
                }
            })

            response = await transport.send_message(request)

            # Validate response
            self.message_handler.validate_response(response)

            result = response.get("result", {})

            # Validate initialization result
            self._validate_initialization_result(result)

            # Send initialized notification
            await self._send_initialized_notification(transport)

            return result

        except Exception as e:
            if isinstance(e, MCPRequestError):
                raise
            raise MCPRequestError(f"Failed to initialize MCP connection: {e}")

    async def _send_initialized_notification(self, transport: BaseTransport):
        """Send initialized notification to server.

        Args:
            transport: MCP transport to use
        """
        notification = self.message_handler.create_notification("notifications/initialized", {})
        await transport.send_message(notification)

    def _validate_initialization_result(self, result: Dict[str, Any]) -> None:
        """Validate initialization result.

        Args:
            result: Initialization result to validate

        Raises:
            MCPRequestError: If result is invalid
        """
        # Check for required fields
        if "protocolVersion" not in result:
            raise MCPRequestError("Initialize result missing 'protocolVersion' field")

        if "capabilities" not in result:
            raise MCPRequestError("Initialize result missing 'capabilities' field")

        if "serverInfo" not in result:
            raise MCPRequestError("Initialize result missing 'serverInfo' field")

        # Validate server info
        server_info = result["serverInfo"]
        if not isinstance(server_info, dict):
            raise MCPRequestError("Server info must be an object")

        if "name" not in server_info:
            raise MCPRequestError("Server info missing 'name' field")

    def get_supported_capabilities(self) -> Dict[str, Any]:
        """Get the capabilities supported by this client.

        Returns:
            Dictionary of supported capabilities
        """
        return {
            "experimental": {},
            "sampling": {},
            "tools": {
                "listChanged": True
            },
            "resources": {
                "subscribe": True,
                "listChanged": True
            },
            "prompts": {
                "listChanged": True
            },
            "roots": {
                "listChanged": True
            }
        }

    def format_capabilities_summary(self, server_capabilities: Dict[str, Any]) -> str:
        """Format server capabilities summary.

        Args:
            server_capabilities: Server capabilities from initialization

        Returns:
            Formatted capabilities summary
        """
        summary_lines = ["🔧 Server Capabilities:"]

        capabilities = server_capabilities.get("capabilities", {})

        # Check for main capability categories
        categories = ["tools", "resources", "prompts", "sampling", "experimental", "roots"]

        for category in categories:
            if category in capabilities:
                category_caps = capabilities[category]
                if category_caps:
                    summary_lines.append(f"  ✅ {category.title()}: {self._format_capability_details(category_caps)}")
                else:
                    summary_lines.append(f"  ➖ {category.title()}: Basic support")

        return "\n".join(summary_lines)

    def _format_capability_details(self, capabilities: Dict[str, Any]) -> str:
        """Format capability details.

        Args:
            capabilities: Capability object

        Returns:
            Formatted capability string
        """
        if not capabilities:
            return "Basic"

        details = []
        for key, value in capabilities.items():
            if value is True:
                details.append(key)
            elif isinstance(value, dict) and value:
                details.append(f"{key}({len(value)} features)")

        return ", ".join(details) if details else "Advanced"

    async def send_logs_subscription(self, transport: BaseTransport, level: str = "info") -> None:
        """Send notification to subscribe to server logs.

        Args:
            transport: MCP transport to use for communication
            level: Minimum log level to receive

        Raises:
            MCPRequestError: If notification sending fails
        """
        try:
            # Send logs subscription notification
            await transport.send_request({
                "method": "notifications/logs/setLevel",
                "params": {"level": level}
            })

        except Exception as e:
            raise MCPRequestError(f"Failed to send logs subscription: {e}")
