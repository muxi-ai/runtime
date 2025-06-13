# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Service - Tool Provider Registry and Orchestration
# Description:  Central service for managing MCP server connections and tools
# Role:         Coordinates access to external tools across the framework
# Usage:        Used to register, access, and manage MCP tool providers
# Author:       Muxi Framework Team
#
# The MCP Service provides a central registry and access point for interacting
# with MCP (Model Context Protocol) servers and their tools. Key features include:
#
# 1. Server Connection Management
#    - Registration of HTTP and command-line MCP servers
#    - Credential and authentication handling
#    - Connection lifecycle management
#
# 2. Tool Registry and Discovery
#    - Automatic tool discovery from connected servers
#    - Centralized tool registry and documentation
#    - Tool capability querying
#
# 3. Managed Tool Execution
#    - Transparent request routing to appropriate servers
#    - Timeout and cancellation support
#    - Error handling and reconnection logic
#
# This service acts as the core coordinator for all external tool interactions
# in the framework, providing a unified interface regardless of where tools
# are actually implemented or hosted.
# =============================================================================

import asyncio
from typing import Any, Dict, Optional

from ..llm import LLM
from .handler import MCPHandler


class MCPService:
    """
    Service for interacting with MCP servers.

    This class provides methods for registering, managing, and interacting with
    MCP servers. It maintains a registry of available servers and their tools,
    and provides a unified interface for invoking tools regardless of which
    server hosts them.
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        """
        Get or create the singleton instance.

        This method implements the singleton pattern, ensuring that only one
        instance of the MCPService exists in the application.

        Returns:
            The singleton MCPService instance
        """
        if cls._instance is None:
            cls._instance = MCPService()
        return cls._instance

    def __init__(self):
        """
        Initialize the MCP service.

        Sets up the internal data structures for tracking servers, handlers,
        connections, and tools.
        """
        # Dictionary of registered servers
        self.servers = {}

        # Dictionary of registered MCP handlers
        self.mcp_handlers = {}

        # Dictionary to store handler instances
        self.handlers = {}

        # Dictionary to store connection details
        self.connections = {}

        # Dictionary to store locks for each handler
        self.locks = {}

        # Dictionary to store discovered tools
        self.tool_registry = {}

    async def register_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: Optional[int] = None,
    ) -> str:
        """
        Register an MCP server.

        This is a simple registration method that records server details without
        actually establishing a connection. Use register_mcp_server for full
        connection establishment.

        Args:
            server_id: Unique identifier for the server
            url: URL of the server
            command: Command to start the server
            credentials: Credentials for authentication
            model: Model to use for the server
            request_timeout: Timeout for requests

        Returns:
            The server ID
        """
        # This is just a placeholder implementation
        # Emit system event for server registration
        try:
            from ..observability import SystemEventType, EventLevel, ObservabilityManager
            observability_manager = ObservabilityManager.get_instance()
            if observability_manager:
                await observability_manager.emit_system_event(
                    SystemEventType.MCP_SERVER_REGISTRATION_COMPLETED,
                    level=EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "url": url,
                        "command": command,
                        "has_credentials": bool(credentials),
                        "request_timeout": request_timeout or 60,
                    },
                    description=f"MCP server registered: {server_id}"
                )
        except Exception:
            pass  # Don't let observability errors break the flow

        self.servers[server_id] = {
            "url": url,
            "command": command,
            "credentials": credentials or {},
            "model": model,
            "request_timeout": request_timeout or 60,
        }
        return server_id

    async def register_mcp_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
    ) -> str:
        """
        Register an MCP server with the service.

        This method establishes an actual connection to the MCP server and
        discovers available tools. It handles both HTTP/SSE and command-line
        based MCP servers.

        Args:
            server_id: Unique identifier for the MCP server
            url: URL for HTTP/SSE MCP servers
            command: Command for command-line MCP servers
            credentials: Optional credentials for authentication
            model: Optional model to use for this MCP handler
            request_timeout: Timeout in seconds for requests to this server

        Returns:
            The server_id of the registered server

        Raises:
            Exception: If the server registration fails
        """
        # Create lock for this handler
        self.locks[server_id] = asyncio.Lock()

        # Emit MCP server registration started event
        try:
            from ..observability import (
                SystemEventType,
                EventLevel,
                ObservabilityManager,
            )

            observability_manager = ObservabilityManager.get_instance()
            if observability_manager:
                await observability_manager.event_logger.emit_event(
                    SystemEventType.MCP_SERVER_REGISTRATION_STARTED,
                    level=EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "url": url,
                        "command": command,
                        "has_credentials": bool(credentials),
                        "request_timeout": request_timeout,
                    },
                    description=f"MCP server registration started: {server_id}",
                )
        except Exception:
            pass  # Don't let observability errors break the flow

        # Initialize the handler
        async with self.locks[server_id]:
            try:
                # Create and initialize the MCP handler
                handler = MCPHandler(model=model)

                # Set up connection with the transport factory
                # This establishes actual connection to the server
                server_name = server_id.replace("-", "_").lower()

                # Connect to the server using the appropriate transport
                await handler.connect_server(
                    name=server_name,
                    url=url,
                    command=command,
                    credentials=credentials,
                    request_timeout=request_timeout,  # Pass the timeout parameter
                )

                # Store the handler
                self.handlers[server_id] = handler
                self.connections[server_id] = {
                    "status": "connected",
                    "url": url,
                    "command": command,
                    "credentials": credentials,
                    "server_name": server_name,
                    "request_timeout": request_timeout,
                }

                # Discover available tools
                try:
                    tools = await handler.list_tools(server_name)
                    self.tool_registry[server_id] = {
                        tool.get("name", f"unknown_{i}"): tool for i, tool in enumerate(tools)
                    }
                    # Emit tool discovery completed event
                    try:
                        from ..observability import SystemEventType, EventLevel, ObservabilityManager
                        observability_manager = ObservabilityManager.get_instance()
                        if observability_manager:
                            await observability_manager.emit_system_event(
                                SystemEventType.MCP_TOOL_DISCOVERY_COMPLETED,
                                level=EventLevel.INFO,
                                data={
                                    "server_id": server_id,
                                    "tools_count": len(tools),
                                    "tools": [
                                        tool.get("name", f"unknown_{i}")
                                        for i, tool in enumerate(tools)
                                    ]
                                },
                                description=(
                                    f"Discovered {len(tools)} tools from MCP server: {server_id}"
                                )
                            )
                    except Exception:
                        pass
                except Exception as e:
                    # Emit tool discovery failed event
                    try:
                        from ..observability import SystemEventType, EventLevel, ObservabilityManager
                        observability_manager = ObservabilityManager.get_instance()
                        if observability_manager:
                            await observability_manager.emit_system_event(
                                SystemEventType.MCP_TOOL_DISCOVERY_COMPLETED,
                                level=EventLevel.WARNING,
                                data={
                                    "server_id": server_id,
                                    "error": str(e),
                                    "tools_count": 0
                                },
                                description=f"Unable to discover tools from MCP server {server_id}: {str(e)}"
                            )
                    except Exception:
                        pass
                    self.tool_registry[server_id] = {}

                # Emit MCP server registration completed event
                try:
                    from ..observability import (
                        SystemEventType,
                        EventLevel,
                        ObservabilityManager,
                    )

                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.event_logger.emit_event(
                            SystemEventType.MCP_SERVER_REGISTRATION_COMPLETED,
                            level=EventLevel.INFO,
                            data={
                                "server_id": server_id,
                                "tools_discovered": len(self.tool_registry.get(server_id, {})),
                                "connection_status": "connected",
                            },
                            description=f"MCP server registration completed: {server_id}",
                        )
                except Exception:
                    pass  # Don't let observability errors break the flow

                # Final registration success event already emitted above
                return server_id

            except Exception as e:
                # Emit MCP server registration failed event
                try:
                    from ..observability import (
                        SystemEventType,
                        EventLevel,
                        ObservabilityManager,
                    )

                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.event_logger.emit_event(
                            SystemEventType.MCP_SERVER_REGISTRATION_FAILED,
                            level=EventLevel.ERROR,
                            data={
                                "server_id": server_id,
                                "error": str(e),
                                "url": url,
                                "command": command,
                            },
                            description=f"MCP server registration failed: {server_id} - {e}",
                        )
                except Exception:
                    pass  # Don't let observability errors break the flow

                # Clean up if something went wrong
                if server_id in self.locks:
                    del self.locks[server_id]
                # Error event already emitted above
                raise

    async def invoke_tool(
        self,
        server_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        request_timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a tool on an MCP server.

        This method executes a tool on the specified MCP server with the given
        parameters, handling locking to prevent concurrent issues and managing
        timeouts.

        Args:
            server_id: The ID of the server to use
            tool_name: The name of the tool to invoke
            parameters: The parameters to pass to the tool
            request_timeout: Optional timeout override for this specific request

        Returns:
            The result of the tool invocation as a dictionary with status and result

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        # Emit MCP tool invocation started event
        try:
            from ..observability import (
                ConversationEventType,
                EventLevel,
                ObservabilityManager,
            )

            observability_manager = ObservabilityManager.get_instance()
            if observability_manager:
                await observability_manager.event_logger.emit_event(
                    ConversationEventType.MCP_TOOL_CALL_STARTED,
                    level=EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "request_timeout": request_timeout,
                    },
                    description=f"MCP tool invocation started: {tool_name} on {server_id}",
                )
        except Exception:
            pass  # Don't let observability errors break the flow

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Acquire lock for this handler to prevent concurrent issues
        async with self.locks[server_id]:
            try:
                # Use request timeout from parameters,
                # or fall back to the one saved during server registration
                default_timeout = self.connections[server_id].get("request_timeout", 60)
                timeout = request_timeout if request_timeout is not None else default_timeout

                # Check if we need to temporarily modify the timeout
                restore_timeout = False
                original_timeout = None

                if request_timeout is not None and server_name in handler.active_connections:
                    client = handler.active_connections[server_name]
                    if client.request_timeout != request_timeout:
                        # Store original timeout to restore later
                        original_timeout = client.request_timeout
                        client.request_timeout = timeout
                        restore_timeout = True

                # Process the tool call through the handler directly to the server
                result = await handler.execute_tool(
                    server_name=server_name,
                    tool_name=tool_name,
                    params=parameters,
                    cancellation_token=None,
                )

                # Emit MCP tool invocation completed event
                try:
                    from ..observability import (
                        ConversationEventType,
                        EventLevel,
                        ObservabilityManager,
                    )

                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.event_logger.emit_event(
                            ConversationEventType.MCP_TOOL_CALL_COMPLETED,
                            level=EventLevel.INFO,
                            data={
                                "server_id": server_id,
                                "tool_name": tool_name,
                                "result_type": type(result).__name__,
                                "success": True,
                            },
                            description=(
                                f"MCP tool invocation completed: {tool_name} on {server_id}"
                            ),
                        )
                except Exception:
                    pass  # Don't let observability errors break the flow

                return {"result": result, "status": "success"}

            except Exception as e:
                # Emit MCP tool invocation failed event
                try:
                    from ..observability import (
                        ConversationEventType,
                        EventLevel,
                        ObservabilityManager,
                    )

                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.event_logger.emit_event(
                            ConversationEventType.MCP_TOOL_CALL_FAILED,
                            level=EventLevel.ERROR,
                            data={
                                "server_id": server_id,
                                "tool_name": tool_name,
                                "error": str(e),
                                "error_type": type(e).__name__,
                            },
                            description=(
                                f"MCP tool invocation failed: {tool_name} on {server_id} - {e}"
                            ),
                        )
                except Exception:
                    pass  # Don't let observability errors break the flow

                # Error event already emitted above
                return {"error": str(e), "status": "error"}
            finally:
                # Restore the original timeout if we changed it
                if restore_timeout and server_name in handler.active_connections:
                    handler.active_connections[server_name].request_timeout = original_timeout

    async def disconnect_server(self, server_id: str) -> bool:
        """
        Disconnect from an MCP server.

        This method closes the connection to an MCP server and cleans up
        all associated resources and registry entries.

        Args:
            server_id: The ID of the server to disconnect

        Returns:
            True if disconnection was successful, False otherwise
        """
        if server_id not in self.handlers:
            return False

        async with self.locks[server_id]:
            try:
                handler = self.handlers[server_id]
                server_name = self.connections[server_id]["server_name"]

                # Disconnect from the server
                await handler.disconnect_server(server_name)

                # Remove from registry
                del self.handlers[server_id]
                del self.connections[server_id]
                del self.locks[server_id]
                if server_id in self.tool_registry:
                    del self.tool_registry[server_id]

                # Emit disconnection success event
                try:
                    from ..observability import SystemEventType, EventLevel, ObservabilityManager
                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.emit_system_event(
                            SystemEventType.MCP_SERVER_DISCONNECTED,
                            level=EventLevel.INFO,
                            data={"server_id": server_id},
                            description=f"Disconnected from MCP server: {server_id}"
                        )
                except Exception:
                    pass
                return True

            except Exception as e:
                # Emit disconnection error event
                try:
                    from ..observability import SystemEventType, EventLevel, ObservabilityManager
                    observability_manager = ObservabilityManager.get_instance()
                    if observability_manager:
                        await observability_manager.emit_system_event(
                            SystemEventType.MCP_SERVER_DISCONNECTED,
                            level=EventLevel.ERROR,
                            data={"server_id": server_id, "error": str(e)},
                            description=f"Error disconnecting from MCP server {server_id}: {str(e)}"
                        )
                except Exception:
                    pass
                return False
