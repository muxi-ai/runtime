# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Handler - Model Context Protocol Implementation
# Description:  Core implementation of the Model Context Protocol (MCP)
# Role:         Enables agents to interact with external tools and services
# Usage:        Used by Overlord to connect agents with external tools
# Author:       Muxi Framework Team
#
# The MCP Handler provides a robust implementation of the Model Context Protocol,
# enabling agents to communicate with external tools and services. It includes:
#
# 1. Connection Management
#    - Secure establishment of MCP server connections
#    - Session tracking and maintenance
#    - Error handling and recovery
#
# 2. Request/Response Cycle
#    - Formatting and sending MCP messages
#    - Processing tool responses
#    - Handling asynchronous operations
#
# 3. Error Handling
#    - Specialized error types for different failure modes
#    - Graceful degradation on connection issues
#    - Detailed logging for troubleshooting
#
# The MCP implementation enables agents to:
# - Discover and use external tools dynamically
# - Execute complex operations beyond LLM capabilities
# - Interact with real-world systems and data sources
# - Maintain persistent connections to tool servers
#
# This module implements the official Model Context Protocol specification,
# using the MCP Python SDK for transport and message handling.
#
# Example usage:
#
#   # Create handler with model for extracting tool calls
#   handler = MCPHandler(model=openai_model)
#
#   # Connect to an MCP server
#   await handler.connect_server(
#       name="file_tools",
#       url="http://localhost:8080/api/mcp"
#   )
#
#   # Execute a tool
#   result = await handler.execute_tool(
#       server_name="file_tools",
#       tool_name="read_file",
#       params={"path": "config.json"}
#   )
# =============================================================================

from ...utils.id_generator import generate_nanoid
from typing import Any, Dict, List, Optional
from datetime import datetime
from .. import observability
import asyncio

# Import all transport classes from the new modular structure
from .transports import MCPTransportFactory, MCPConnectionError, CancellationToken


class MCPServerClient:
    """
    Client for a single MCP server connection.

    This class manages the connection to a single MCP server and provides
    methods for sending messages and executing tools on that server.
    """

    def __init__(
        self,
        name: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        request_timeout: int = 60,
    ):
        """
        Initialize the MCP server client.

        Args:
            name: Unique name for this server connection
            url: URL for HTTP-based MCP servers (mutually exclusive with command)
            command: Command for command-line based MCP servers (mutually exclusive with url)
            args: Optional list of arguments for command-line MCP servers
            credentials: Optional authentication credentials (not yet implemented)
            request_timeout: Timeout for requests in seconds
        """
        self.name = name
        self.url = url
        self.command = command
        self.args = args
        self.credentials = credentials
        self.request_timeout = request_timeout
        self.transport = None
        self.connected = False
        self.last_activity = None

        # Request tracking using overlord request_id as primary key
        # Maps request_id -> {json_rpc_id, task, start_time, cancellation_token}
        self.active_requests: Dict[str, Dict[str, Any]] = {}
        self.request_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self) -> bool:
        """
        Establish connection to the MCP server.

        Creates an appropriate transport and establishes the connection.
        Uses the factory to automatically select the best transport type.

        Returns:
            bool: True if connection was successful

        Raises:
            MCPConnectionError: If connection fails
        """
        pass  # REMOVED: init-phase observe() call

        try:
            # Create transport using factory with automatic type selection
            # For HTTP servers, use the fallback method to auto-detect SSE
            if self.url:
                self.transport = await MCPTransportFactory.create_transport_with_fallback(
                    url=self.url,
                    auth=self.credentials,
                    request_timeout=self.request_timeout,
                )
            else:
                self.transport = MCPTransportFactory.create_transport(
                    command=self.command,
                    args=self.args,
                    auth=self.credentials,
                    request_timeout=self.request_timeout,
                )

            # Attempt connection
            success = await self.transport.connect()

            if success:
                self.connected = True
                self.last_activity = datetime.now()

                pass  # REMOVED: init-phase observe() call

            return success

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_CONNECTION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to connect to MCP server '{self.name}': {str(e)}",
                data={
                    "server_name": self.name,
                    "url": self.url,
                    "command": self.command,
                    "error": str(e),
                },
            )
            raise

    async def disconnect(self) -> bool:
        """
        Disconnect from the MCP server.

        Properly closes the transport connection and cleans up resources.

        Returns:
            bool: True if disconnection was successful

        Raises:
            MCPConnectionError: If disconnection fails
        """
        if not self.transport:
            self.connected = False
            return True

        try:
            success = await self.transport.disconnect()
            self.connected = False

            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                level=observability.EventLevel.INFO,
                description=f"Disconnected from MCP server '{self.name}'",
                data={
                    "server_name": self.name,
                    "url": self.url,
                    "command": self.command,
                    "transport_stats": self.transport.get_connection_stats(),
                },
            )

            return success

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to disconnect from MCP server '{self.name}': {str(e)}",
                data={
                    "server_name": self.name,
                    "url": self.url,
                    "command": self.command,
                    "error": str(e),
                },
            )
            raise

    async def send_message(
        self,
        method: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Send a JSON-RPC message to the MCP server.

        Args:
            method: The method name to call
            params: Parameters for the method
            request_id: Request ID from overlord for lifecycle tracking
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the response from the server

        Raises:
            MCPConnectionError: If not connected or connection fails
            MCPRequestError: If the request is invalid or fails
        """
        if not self.connected or not self.transport:
            raise MCPConnectionError(
                f"Not connected to MCP server '{self.name}'",
                {"server_name": self.name, "url": self.url, "command": self.command},
            )

        # Create JSON-RPC request (internal protocol ID)
        json_rpc_id = f"rpc_{generate_nanoid()}"
        request_data = {
            "jsonrpc": "2.0",
            "id": json_rpc_id,
            "method": method,
            "params": params,
        }

        # Use overlord request_id as primary tracking key (fallback to json_rpc_id)
        tracking_id = request_id or json_rpc_id
        start_time = datetime.now()

        # Track this request using overlord's request lifecycle
        request_info = {
            "json_rpc_id": json_rpc_id,
            "method": method,
            "start_time": start_time,
            "cancellation_token": cancellation_token,
            "request_id": request_id,
        }

        self.active_requests[tracking_id] = request_info

        # Build observability data
        obs_data = {
            "server_name": self.name,
            "server_id": self.name,  # Include server ID
            "method": method,
            "json_rpc_id": json_rpc_id,
            "request_id": request_id,
            "tracking_id": tracking_id,
            "params": params,
        }

        # Add tool name if this is a tool call
        if method == "tools/call" and params and "name" in params:
            obs_data["tool_name"] = params["name"]

        observability.observe(
            event_type=observability.SystemEvents.MCP_MESSAGE_SENT,
            level=observability.EventLevel.DEBUG,
            description=f"Sending MCP message '{method}' to server '{self.name}'",
            data=obs_data,
        )

        try:
            # Create task for the actual request
            task = asyncio.create_task(
                self.transport.send_request(request_data, cancellation_token)
            )

            # Store task for cancellation purposes
            self.request_tasks[tracking_id] = task
            request_info["task"] = task

            # Wait for completion
            response = await task
            self.last_activity = datetime.now()

            # Build observability data for response
            resp_data = {
                "server_name": self.name,
                "server_id": self.name,  # Include server ID
                "method": method,
                "json_rpc_id": json_rpc_id,
                "request_id": request_id,
                "tracking_id": tracking_id,
                "response": response,
            }

            # Add tool name if this is a tool call
            if method == "tools/call" and params and "name" in params:
                resp_data["tool_name"] = params["name"]

            observability.observe(
                event_type=observability.SystemEvents.MCP_MESSAGE_RECEIVED,
                level=observability.EventLevel.DEBUG,
                description=f"Received MCP response for '{method}' from server '{self.name}'",
                data=resp_data,
            )

            return response

        except asyncio.CancelledError:
            # Build observability data for cancellation
            cancel_data = {
                "server_name": self.name,
                "server_id": self.name,  # Include server ID
                "method": method,
                "json_rpc_id": json_rpc_id,
                "request_id": request_id,
                "tracking_id": tracking_id,
            }

            # Add tool name if this is a tool call
            if method == "tools/call" and params and "name" in params:
                cancel_data["tool_name"] = params["name"]

            observability.observe(
                event_type=observability.SystemEvents.OPERATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"MCP request '{method}' was cancelled for server '{self.name}'",
                data=cancel_data,
            )
            raise
        except Exception as e:
            # Build observability data for error
            error_data = {
                "server_name": self.name,
                "server_id": self.name,  # Include server ID
                "method": method,
                "json_rpc_id": json_rpc_id,
                "request_id": request_id,
                "tracking_id": tracking_id,
                "error": str(e),
            }

            # Add tool name if this is a tool call
            if method == "tools/call" and params and "name" in params:
                error_data["tool_name"] = params["name"]

            observability.observe(
                event_type=observability.SystemEvents.MCP_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"MCP message '{method}' failed for server '{self.name}': {str(e)}",
                data=error_data,
            )
            raise
        finally:
            # Clean up tracking
            self.active_requests.pop(tracking_id, None)
            self.request_tasks.pop(tracking_id, None)

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            request_id: Request ID from overlord for lifecycle tracking
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the tool execution result
        """
        return await self.send_message(
            "tools/call",
            {"name": tool_name, "arguments": params},
            request_id=request_id,
            cancellation_token=cancellation_token,
        )

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about this server connection.

        Returns:
            Dict with connection statistics and transport details
        """
        stats = {
            "server_name": self.name,
            "url": self.url,
            "command": self.command,
            "connected": self.connected,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }

        if self.transport:
            stats["transport"] = self.transport.get_connection_stats()

        return stats

    def cancel_all_requests(self) -> int:
        """
        Cancel all outstanding requests to this server.

        Uses the overlord request_id tracking system for graceful cancellation.
        Cancels both by overlord request_id (preferred) and individual requests.

        Returns:
            int: Number of requests cancelled
        """
        if not self.active_requests:
            return 0

        cancelled_count = 0
        requests_to_cancel = list(
            self.active_requests.keys()
        )  # Copy to avoid modification during iteration

        for tracking_id in requests_to_cancel:
            if self.cancel_request(tracking_id):
                cancelled_count += 1

        observability.observe(
            event_type=observability.SystemEvents.OPERATION_COMPLETED,
            level=observability.EventLevel.INFO,
            description=f"Cancelled {cancelled_count} pending requests for server '{self.name}'",
            data={
                "server_name": self.name,
                "cancelled_count": cancelled_count,
                "total_requests": len(requests_to_cancel),
            },
        )

        return cancelled_count

    def cancel_request(self, tracking_id: str) -> bool:
        """
        Cancel a specific request by tracking ID (overlord request_id or json_rpc_id).

        Args:
            tracking_id: The tracking ID of the request to cancel

        Returns:
            bool: True if request was cancelled, False if not found or already completed
        """
        if tracking_id not in self.active_requests:
            return False

        request_info = self.active_requests[tracking_id]
        task = self.request_tasks.get(tracking_id)

        if not task or task.done():
            # Request already completed, clean up tracking
            self._cleanup_request(tracking_id)
            return False

        # Cancel the task
        task.cancel()

        # Use cancellation token if available
        cancellation_token = request_info.get("cancellation_token")
        if cancellation_token:
            cancellation_token.cancel()

        observability.observe(
            event_type=observability.SystemEvents.OPERATION_COMPLETED,
            level=observability.EventLevel.INFO,
            description=f"Cancelled request {tracking_id} on server '{self.name}'",
            data={
                "server_name": self.name,
                "tracking_id": tracking_id,
                "request_id": request_info.get("request_id"),
                "json_rpc_id": request_info.get("json_rpc_id"),
                "method": request_info.get("method"),
            },
        )

        return True

    def cancel_requests_by_overlord_id(self, request_id: str) -> int:
        """
        Cancel all requests associated with a specific overlord request_id.

        This enables cancelling all MCP operations for a specific user request,
        supporting the overlord's graceful shutdown and request lifecycle management.

        Args:
            request_id: The overlord request ID to cancel

        Returns:
            int: Number of requests cancelled
        """
        if not request_id:
            return 0

        cancelled_count = 0
        requests_to_cancel = []

        # Find all requests for this overlord request_id
        for tracking_id, request_info in self.active_requests.items():
            if request_info.get("request_id") == request_id:
                requests_to_cancel.append(tracking_id)

        # Cancel each matching request
        for tracking_id in requests_to_cancel:
            if self.cancel_request(tracking_id):
                cancelled_count += 1

        if cancelled_count > 0:
            observability.observe(
                event_type=observability.SystemEvents.OPERATION_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description=(
                    f"Cancelled {cancelled_count} MCP requests for overlord "
                    f"request {request_id} on server '{self.name}'"
                ),
                data={
                    "server_name": self.name,
                    "request_id": request_id,
                    "cancelled_count": cancelled_count,
                },
            )

        return cancelled_count

    def _cleanup_request(self, tracking_id: str) -> None:
        """Clean up tracking for a completed/cancelled request."""
        self.active_requests.pop(tracking_id, None)
        self.request_tasks.pop(tracking_id, None)

    def get_pending_requests(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all pending requests.

        Returns:
            Dict mapping tracking IDs to request information including overlord request_id
        """
        result = {}

        for tracking_id, request_info in self.active_requests.items():
            task = self.request_tasks.get(tracking_id)
            start_time = request_info.get("start_time")
            duration = None

            if start_time:
                duration = (datetime.now() - start_time).total_seconds()

            result[tracking_id] = {
                "request_id": request_info.get("request_id"),
                "json_rpc_id": request_info.get("json_rpc_id"),
                "method": request_info.get("method"),
                "status": "running" if task and not task.done() else "completed",
                "cancelled": task.cancelled() if task and task.done() else False,
                "start_time": start_time.isoformat() if start_time else None,
                "duration_seconds": duration,
                "has_cancellation_token": bool(request_info.get("cancellation_token")),
            }

        return result


class MCPHandler:
    """
    Main handler for Model Context Protocol (MCP) operations.

    Manages multiple MCP server connections and provides a unified interface
    for tool discovery and execution across all connected servers.
    """

    def __init__(
        self,
        model,
        tool_registry: Optional[Dict[str, Dict[str, Any]]] = None,
        allow_fallback: bool = False,
    ):
        """
        Initialize the MCP handler with a model for LLM integration.

        Args:
            model: The language model to use for extracting tool calls
            tool_registry: Reference to the shared tool registry from MCPService
            allow_fallback: Whether to allow fallback to any connected server if tool not found in registry
        """
        self.model = model
        self.servers: Dict[str, MCPServerClient] = {}
        self.active_connections: Dict[str, MCPServerClient] = {}
        self.tool_registry = tool_registry or {}
        self.allow_fallback = allow_fallback

        # Explicit mapping between server IDs and server names
        self.server_id_to_name: Dict[str, str] = {}
        self.server_name_to_id: Dict[str, str] = {}

    async def connect_server(
        self,
        name: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        request_timeout: int = 60,
        server_id: Optional[str] = None,
    ) -> bool:
        """
        Connect to an MCP server.

        Args:
            name: Unique name for this server
            url: URL for HTTP-based servers (mutually exclusive with command)
            command: Command for command-line based servers (mutually exclusive with url)
            args: Optional list of arguments for command-line MCP servers
            credentials: Optional authentication credentials
            request_timeout: Timeout for requests in seconds
            server_id: Optional server ID for explicit mapping to tool registry

        Returns:
            bool: True if connection was successful

        Raises:
            ValueError: If both url and command are provided, or neither is provided
            MCPConnectionError: If connection fails
        """
        if (url is None) == (command is None):
            raise ValueError("Must provide exactly one of 'url' or 'command'")

        if name in self.servers:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_RECONNECTING,
                level=observability.EventLevel.WARNING,
                description=f"Reconnecting to existing MCP server '{name}'",
                data={"server_name": name, "existing_connection": True},
            )
            # Disconnect existing server first
            await self.disconnect_server(name)

        # Create new server client
        server = MCPServerClient(
            name=name,
            url=url,
            command=command,
            args=args,
            credentials=credentials,
            request_timeout=request_timeout,
        )

        try:
            success = await server.connect()
            if success:
                self.servers[name] = server
                self.active_connections[name] = server

                # Maintain explicit server ID to name mapping
                if server_id:
                    self.server_id_to_name[server_id] = name
                    self.server_name_to_id[name] = server_id

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTERED,
                    level=observability.EventLevel.INFO,
                    description=f"Successfully registered MCP server '{name}' (total: {len(self.servers)})",
                    data={
                        "server_name": name,
                        "server_id": server_id,
                        "total_servers": len(self.servers),
                    },
                )
            return success

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to register MCP server '{name}': {str(e)}",
                data={"server_name": name, "error": str(e)},
            )
            raise

    async def disconnect_server(self, name: str) -> bool:
        """
        Disconnect from an MCP server.

        Args:
            name: Name of the server to disconnect from

        Returns:
            bool: True if disconnection was successful

        Raises:
            ValueError: If server name is not found
        """
        if name not in self.servers:
            raise ValueError(f"Server '{name}' not found")

        server = self.servers[name]

        try:
            success = await server.disconnect()
            del self.servers[name]
            if name in self.active_connections:
                del self.active_connections[name]

            # Clean up server ID mappings
            server_id = self.server_name_to_id.pop(name, None)
            if server_id:
                self.server_id_to_name.pop(server_id, None)

            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_UNREGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Unregistered MCP server '{name}' (remaining: {len(self.servers)})",
                data={
                    "server_name": name,
                    "server_id": server_id,
                    "remaining_servers": len(self.servers),
                },
            )

            return success

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_UNREGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to unregister MCP server '{name}': {str(e)}",
                data={"server_name": name, "error": str(e)},
            )
            raise

    async def process_message(
        self, message: Dict[str, Any], cancellation_token: Optional[CancellationToken] = None
    ) -> Dict[str, Any]:
        """
        Process a message and execute any tool calls.

        Args:
            message: Message containing potential tool calls
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the response with tool execution results
        """
        if not isinstance(message, dict):
            return {"error": "Invalid message format"}

        # Extract tool calls from the message using the model
        tool_calls = self.model.extract_tool_calls(message)

        if not tool_calls:
            return {"status": "no_tools", "message": "No tool calls found in message"}

        results = []
        for tool_call in tool_calls:
            try:
                tool_name = tool_call.get("name")
                params = tool_call.get("parameters", {})

                # Find which server has this tool
                server_name = self._get_server_for_tool(tool_name)
                if not server_name:
                    results.append(
                        {
                            "tool": tool_name,
                            "error": f"Tool '{tool_name}' not found on any connected server",
                        }
                    )
                    continue

                # Execute the tool
                result = await self.execute_tool(server_name, tool_name, params, cancellation_token)
                results.append({"tool": tool_name, "result": result})

            except Exception as e:
                results.append({"tool": tool_call.get("name", "unknown"), "error": str(e)})

        return {"status": "completed", "tool_results": results}

    async def execute_tool(
        self,
        server_name: str,
        tool_name: str,
        params: Dict[str, Any],
        request_id: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool on a specific server.

        Args:
            server_name: Name of the server to execute the tool on
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            request_id: Request ID from overlord for lifecycle tracking
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the tool execution result

        Raises:
            ValueError: If server is not found
            MCPRequestError: If tool execution fails
        """
        if server_name not in self.servers:
            raise ValueError(f"Server '{server_name}' not found")

        server = self.servers[server_name]
        return await server.execute_tool(tool_name, params, request_id, cancellation_token)

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """
        List available tools on a server.

        Args:
            server_name: Name of the server to list tools for

        Returns:
            List of tool definitions

        Raises:
            ValueError: If server is not found
        """
        if server_name not in self.servers:
            raise ValueError(f"Server '{server_name}' not found")

        server = self.servers[server_name]
        response = await server.send_message("tools/list", {})

        # Handle nested JSON-RPC response structure
        # Response structure: {"status": "success", "result": {"jsonrpc": "2.0",
        # "id": "...", "result": {"tools": [...]}}}
        tools = []

        if response.get("status") == "success":
            result = response.get("result", {})

            # Handle different response structures
            if "result" in result and isinstance(result["result"], dict):
                # Nested JSON-RPC response
                tools = result["result"].get("tools", [])
            elif "tools" in result:
                # Direct tools in result
                tools = result.get("tools", [])
            elif isinstance(result, list):
                # Direct list of tools
                tools = result

        # Fallback: try to extract from any level of the response
        if not tools:
            # Deep search for tools in the response
            def find_tools(obj):
                if isinstance(obj, dict):
                    if "tools" in obj and isinstance(obj["tools"], list):
                        return obj["tools"]
                    for value in obj.values():
                        result = find_tools(value)
                        if result:
                            return result
                return []

            tools = find_tools(response)

        return tools if isinstance(tools, list) else []

    def _get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """
        Find which server provides a specific tool using explicit server ID mapping.

        Args:
            tool_name: Name of the tool to find

        Returns:
            Server name that provides the tool, or None if not found
        """
        # Search through the tool registry for the tool
        for server_id, tools in self.tool_registry.items():
            if tool_name in tools:
                # Use explicit mapping to convert server_id to server_name
                server_name = self.server_id_to_name.get(server_id)

                # Validate the mapping and connection
                if server_name and self._validate_server_connection(server_name, server_id):
                    return server_name

                # If explicit mapping failed, log warning and continue searching
                if server_name:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        description=(
                            f"Server '{server_name}' (ID: {server_id}) found in registry "
                            f"but not connected for tool '{tool_name}'"
                        ),
                        data={
                            "server_id": server_id,
                            "server_name": server_name,
                            "tool_name": tool_name,
                        },
                    )

        # Configurable fallback behavior
        if self.allow_fallback:
            observability.observe(
                event_type=observability.SystemEvents.MCP_TOOL_FALLBACK_USED,
                level=observability.EventLevel.WARNING,
                description=f"Tool '{tool_name}' not found in registry, using fallback to first connected server",
                data={"tool_name": tool_name, "connected_servers": list(self.servers.keys())},
            )

            # Return first connected server as fallback
            for server_name, server in self.servers.items():
                if server.connected:
                    return server_name

        return None

    def _validate_server_connection(self, server_name: str, server_id: str) -> bool:
        """
        Validate that a server name is correctly mapped and connected.

        Args:
            server_name: The server name to validate
            server_id: The server ID for additional validation

        Returns:
            bool: True if server is correctly mapped and connected
        """
        # Check if server exists and is connected
        if server_name not in self.servers:
            return False

        server = self.servers[server_name]
        if not server.connected:
            return False

        # Validate bidirectional mapping consistency
        if self.server_name_to_id.get(server_name) != server_id:
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_MAPPING_INCONSISTENT,
                level=observability.EventLevel.ERROR,
                description=f"Inconsistent server mapping: name '{server_name}' -> ID '{server_id}'",
                data={
                    "server_name": server_name,
                    "expected_id": server_id,
                    "actual_id": self.server_name_to_id.get(server_name),
                },
            )
            return False

        return True

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all server connections.

        Returns:
            Dict with overall connection statistics
        """
        stats = {
            "total_servers": len(self.servers),
            "connected_servers": sum(1 for s in self.servers.values() if s.connected),
            "servers": {},
        }

        for name, server in self.servers.items():
            stats["servers"][name] = server.get_connection_stats()

        return stats

    def cancel_all_operations(self) -> int:
        """
        Cancel all outstanding operations on all servers.

        Returns:
            int: Total number of operations cancelled
        """
        total_cancelled = 0
        for server in self.servers.values():
            total_cancelled += server.cancel_all_requests()
        return total_cancelled

    def cancel_operations_by_overlord_id(self, request_id: str) -> int:
        """
        Cancel all operations associated with a specific overlord request_id.

        This enables the overlord to cancel all MCP operations for a specific
        user request during graceful shutdown or request lifecycle management.

        Args:
            request_id: The overlord request ID to cancel

        Returns:
            int: Total number of operations cancelled across all servers
        """
        if not request_id:
            return 0

        total_cancelled = 0
        for server_name, server in self.servers.items():
            cancelled = server.cancel_requests_by_overlord_id(request_id)
            if cancelled > 0:
                total_cancelled += cancelled
                observability.observe(
                    event_type=observability.SystemEvents.OPERATION_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    description=(
                        f"Cancelled {cancelled} operations on server '{server_name}' "
                        f"for overlord request {request_id}"
                    ),
                    data={
                        "server_name": server_name,
                        "cancelled_count": cancelled,
                        "request_id": request_id,
                    },
                )

        return total_cancelled

    def get_all_pending_requests(self) -> Dict[str, Dict[str, Any]]:
        """Get pending requests from all servers with overlord request_id tracking."""
        result = {}

        for server_name, server in self.servers.items():
            pending = server.get_pending_requests()
            if pending:
                result[server_name] = pending

        return result
