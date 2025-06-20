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

import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from .. import observability

# Import all transport classes from the new modular structure
from .transports import (
    MCPTransportFactory,
    MCPConnectionError,
    CancellationToken
)


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
        credentials: Optional[Dict[str, Any]] = None,
        request_timeout: int = 60,
    ):
        """
        Initialize the MCP server client.

        Args:
            name: Unique name for this server connection
            url: URL for HTTP-based MCP servers (mutually exclusive with command)
            command: Command for command-line based MCP servers (mutually exclusive with url)
            credentials: Optional authentication credentials (not yet implemented)
            request_timeout: Timeout for requests in seconds
        """
        self.name = name
        self.url = url
        self.command = command
        self.credentials = credentials
        self.request_timeout = request_timeout
        self.transport = None
        self.connected = False
        self.last_activity = None

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
        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_CONNECTING,
            level=observability.EventLevel.INFO,
            description=f"Connecting to MCP server '{self.name}'",
            data={"server_name": self.name, "url": self.url, "command": self.command},
        )

        try:
            # Create transport using factory with automatic type selection
            self.transport = MCPTransportFactory.create_transport(
                url=self.url,
                command=self.command,
                request_timeout=self.request_timeout,
            )

            # Attempt connection
            success = await self.transport.connect()

            if success:
                self.connected = True
                self.last_activity = datetime.now()

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_CONNECTED,
                    level=observability.EventLevel.INFO,
                    description=f"Successfully connected to MCP server '{self.name}'",
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
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Send a JSON-RPC message to the MCP server.

        Args:
            method: The method name to call
            params: Parameters for the method
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

        # Create JSON-RPC request
        request_data = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }

        observability.observe(
            event_type=observability.SystemEvents.MCP_MESSAGE_SENT,
            level=observability.EventLevel.DEBUG,
            description=f"Sending MCP message '{method}' to server '{self.name}'",
            data={
                "server_name": self.name,
                "method": method,
                "request_id": request_data["id"],
                "params": params,
            },
        )

        try:
            response = await self.transport.send_request(request_data, cancellation_token)
            self.last_activity = datetime.now()

            observability.observe(
                event_type=observability.SystemEvents.MCP_MESSAGE_RECEIVED,
                level=observability.EventLevel.DEBUG,
                description=f"Received MCP response for '{method}' from server '{self.name}'",
                data={
                    "server_name": self.name,
                    "method": method,
                    "request_id": request_data["id"],
                    "response": response,
                },
            )

            return response

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.MCP_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"MCP message '{method}' failed for server '{self.name}': {str(e)}",
                data={
                    "server_name": self.name,
                    "method": method,
                    "request_id": request_data["id"],
                    "error": str(e),
                },
            )
            raise

    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            cancellation_token: Optional token to cancel the operation

        Returns:
            Dict containing the tool execution result
        """
        return await self.send_message("tools/call", {"name": tool_name, "arguments": params}, cancellation_token)

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

        Returns:
            int: Number of requests cancelled
        """
        # TODO: Implement request tracking and cancellation
        return 0


class MCPHandler:
    """
    Main handler for Model Context Protocol (MCP) operations.

    Manages multiple MCP server connections and provides a unified interface
    for tool discovery and execution across all connected servers.
    """

    def __init__(self, model):
        """
        Initialize the MCP handler with a model for LLM integration.

        Args:
            model: The language model to use for extracting tool calls
        """
        self.model = model
        self.servers: Dict[str, MCPServerClient] = {}
        self.active_connections: Dict[str, MCPServerClient] = {}

    async def connect_server(
        self,
        name: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        credentials: Optional[Dict[str, Any]] = None,
        request_timeout: int = 60,
    ) -> bool:
        """
        Connect to an MCP server.

        Args:
            name: Unique name for this server
            url: URL for HTTP-based servers (mutually exclusive with command)
            command: Command for command-line based servers (mutually exclusive with url)
            credentials: Optional authentication credentials
            request_timeout: Timeout for requests in seconds

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
            credentials=credentials,
            request_timeout=request_timeout,
        )

        try:
            success = await server.connect()
            if success:
                self.servers[name] = server
                self.active_connections[name] = server

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTERED,
                    level=observability.EventLevel.INFO,
                    description=f"Successfully registered MCP server '{name}' (total: {len(self.servers)})",
                    data={"server_name": name, "total_servers": len(self.servers)},
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

            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_UNREGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Unregistered MCP server '{name}' (remaining: {len(self.servers)})",
                data={"server_name": name, "remaining_servers": len(self.servers)},
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
        cancellation_token: Optional[CancellationToken] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool on a specific server.

        Args:
            server_name: Name of the server to execute the tool on
            tool_name: Name of the tool to execute
            params: Parameters for the tool
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
        return await server.execute_tool(tool_name, params, cancellation_token)

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
        Find which server provides a specific tool.

        Args:
            tool_name: Name of the tool to find

        Returns:
            Server name that provides the tool, or None if not found
        """
        # TODO: Implement tool discovery and caching
        # For now, return the first connected server
        for server_name, server in self.servers.items():
            if server.connected:
                return server_name
        return None

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
