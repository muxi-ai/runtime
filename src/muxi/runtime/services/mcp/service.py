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
from .handler import MCPHandler, MCPConnectionError
from .transports import TransportDetector, ModernProtocolFeatures
from .resources.discovery import MCPResourceDiscovery
from .prompts.discovery import MCPPromptDiscovery
from .sampling.creator import MCPSamplingCreator
from .templates.discovery import MCPTemplateDiscovery
from .health.monitor import MCPHealthMonitor, MCPCapabilitiesNegotiator
from .. import observability


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
        connections, and tools. Also initializes the new MCP specification features.
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

        # Initialize MCP specification feature handlers
        self.resource_discovery = MCPResourceDiscovery()
        self.prompt_discovery = MCPPromptDiscovery()
        self.sampling_creator = MCPSamplingCreator()
        self.template_discovery = MCPTemplateDiscovery()
        self.health_monitor = MCPHealthMonitor()
        self.capabilities_negotiator = MCPCapabilitiesNegotiator()

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
        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "server_id": server_id,
                "url": url,
                "command": command,
                "has_credentials": bool(credentials),
                "request_timeout": request_timeout or 60,
            },
            description=f"MCP server registered: {server_id}",
        )

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
        transport_type: Optional[str] = "auto",
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
    ) -> str:
        """
        Register an MCP server with the service.

        This method establishes an actual connection to the MCP server and
        discovers available tools. It handles both HTTP/SSE and command-line
        based MCP servers with intelligent transport detection.

        Args:
            server_id: Unique identifier for the MCP server
            url: URL for HTTP/SSE MCP servers
            command: Command for command-line MCP servers
            transport_type: Transport type selection ("auto", "streamable_http", "http_sse", "command")
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
        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_STARTED,
            level=observability.EventLevel.INFO,
            data={
                "server_id": server_id,
                "url": url,
                "command": command,
                "transport_type": transport_type,
                "has_credentials": bool(credentials),
                "request_timeout": request_timeout,
            },
            description=f"MCP server registration started: {server_id}",
        )

        # Auto-detect transport if not explicitly specified
        if url and transport_type == "auto":
            try:
                detected_transport = await TransportDetector.detect_best_transport(url)

                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_DETECTED,
                    level=observability.EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "detected_transport": detected_transport,
                        "url": url
                    },
                    description=f"MCP transport detected: {detected_transport} for {server_id}",
                )

                transport_type = detected_transport

            except Exception as e:
                # If detection fails, default to Streamable HTTP with fallback
                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_DETECTION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "server_id": server_id,
                        "error": str(e),
                        "fallback_strategy": "streamable_http_with_fallback"
                    },
                    description=f"Transport detection failed for {server_id}, using fallback",
                )

                return await self._connect_with_fallback(server_id, url, credentials, model, request_timeout)

        # Proceed with determined transport type
        return await self._connect_single_transport(
            server_id, url, command, transport_type, credentials, model, request_timeout
        )

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

            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_STARTED,
                level=observability.EventLevel.INFO,
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

                # Enhanced tool execution with modern protocol support
                result = await handler.execute_tool(
                    server_name=server_name,
                    tool_name=tool_name,
                    params=parameters,
                    cancellation_token=None,
                )

                # Process result using modern protocol features
                processed_result = ModernProtocolFeatures.process_structured_output(result)

                # Enhanced observability with structured output info
                observability.observe(
                    event_type=observability.ConversationEvents.MCP_TOOL_CALL_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "tool_name": tool_name,
                        "result_type": processed_result["type"],
                        "has_links": len(processed_result["links"]) > 0,
                        "is_error": processed_result["isError"],
                        "success": not processed_result["isError"],
                        "protocol_version": "2025-06-18"
                    },
                    description=f"MCP tool invocation completed with modern protocol: {tool_name} on {server_id}",
                )

                return {
                    "result": processed_result,
                    "status": "success" if not processed_result["isError"] else "error"
                }

            except Exception as e:
                # Emit MCP tool invocation failed event
                observability.observe(
                    event_type=observability.ConversationEvents.MCP_TOOL_CALL_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "server_id": server_id,
                        "tool_name": tool_name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=(f"MCP tool invocation failed: {tool_name} on {server_id} - {e}"),
                )

                # Error event already emitted above
                return {"error": str(e), "status": "error"}
            finally:
                # Restore the original timeout if we changed it
                if restore_timeout and server_name in handler.active_connections:
                    handler.active_connections[server_name].request_timeout = original_timeout

    async def _connect_with_fallback(
        self,
        server_id: str,
        url: str,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
    ) -> str:
        """
        Attempt connection with automatic fallback between transports.
        """
        transports_to_try = ["streamable_http", "http_sse"]

        for transport_type in transports_to_try:
            try:
                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_ATTEMPT,
                    level=observability.EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "transport_type": transport_type,
                        "attempt_number": transports_to_try.index(transport_type) + 1
                    },
                    description=f"Attempting {transport_type} transport for {server_id}",
                )

                return await self._connect_single_transport(
                    server_id, url, None, transport_type, credentials, model, request_timeout
                )

            except Exception as e:
                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "server_id": server_id,
                        "transport_type": transport_type,
                        "error": str(e),
                        "will_retry": transport_type != transports_to_try[-1]
                    },
                    description=f"Transport {transport_type} failed for {server_id}",
                )

                if transport_type == transports_to_try[-1]:
                    # Last transport failed
                    raise MCPConnectionError(
                        f"Unable to connect to {server_id} with any transport",
                        {
                            "tried_transports": transports_to_try,
                            "last_error": str(e)
                        }
                    )

                continue  # Try next transport

    async def _connect_single_transport(
        self,
        server_id: str,
        url: Optional[str],
        command: Optional[str],
        transport_type: str,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
    ) -> str:
        """
        Connect using a specific transport type.
        """
        # Initialize the handler
        async with self.locks[server_id]:
            try:
                # Create and initialize the MCP handler
                handler = MCPHandler(model=model)

                # Set up connection with the transport factory
                server_name = server_id.replace("-", "_").lower()

                # Connect to the server using the specified transport type
                await handler.connect_server(
                    name=server_name,
                    url=url,
                    command=command,
                    credentials=credentials,
                    request_timeout=request_timeout,
                )

                # Store the handler
                self.handlers[server_id] = handler
                self.connections[server_id] = {
                    "status": "connected",
                    "url": url,
                    "command": command,
                    "credentials": credentials,
                    "server_name": server_name,
                    "transport_type": transport_type,
                    "request_timeout": request_timeout,
                }

                # Discover available tools with modern protocol features
                try:
                    tools = await handler.list_tools(server_name)

                    # Enhanced tool registry with display names and metadata
                    self.tool_registry[server_id] = {}
                    for i, tool in enumerate(tools):
                        tool_name = tool.get("name", f"unknown_{i}")

                        # Use modern protocol features for better UX
                        self.tool_registry[server_id][tool_name] = {
                            **tool,
                            "display_name": ModernProtocolFeatures.extract_display_name(tool),
                            "supports_structured_output": True,  # Assume modern servers support this
                            "supports_elicitation": True,        # New 2025-06-18 feature
                            "_meta": tool.get("_meta", {}),
                            "protocol_version": "2025-06-18"
                        }

                    # Enhanced observability with modern features
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={
                            "server_id": server_id,
                            "tools_count": len(tools),
                            "transport_type": transport_type,
                            "protocol_features": {
                                "structured_output": True,
                                "elicitation": True,
                                "resource_links": True,
                                "title_fields": True
                            },
                            "tools": [
                                {
                                    "name": tool.get("name", f"unknown_{i}"),
                                    "display_name": ModernProtocolFeatures.extract_display_name(tool)
                                }
                                for i, tool in enumerate(tools)
                            ]
                        },
                        description=(f"Discovered {len(tools)} tools with modern protocol features from {server_id}"),
                    )
                except Exception as e:
                    # Emit tool discovery failed event
                    observability.observe(
                        event_type=observability.SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED,
                        level=observability.EventLevel.WARNING,
                        data={"server_id": server_id, "error": str(e), "tools_count": 0},
                        description=f"Unable to discover tools from MCP server {server_id}: {str(e)}",
                    )
                    self.tool_registry[server_id] = {}

                # Emit MCP server registration completed event
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={
                        "server_id": server_id,
                        "transport_type": transport_type,
                        "tools_discovered": len(self.tool_registry.get(server_id, {})),
                        "connection_status": "connected",
                    },
                    description=f"MCP server registration completed: {server_id}",
                )

                return server_id

            except Exception as e:
                # Emit MCP server registration failed event
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "server_id": server_id,
                        "transport_type": transport_type,
                        "error": str(e),
                        "url": url,
                        "command": command,
                    },
                    description=f"MCP server registration failed: {server_id} - {e}",
                )

                # Clean up if something went wrong
                if server_id in self.locks:
                    del self.locks[server_id]
                raise

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
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                    level=observability.EventLevel.INFO,
                    data={"server_id": server_id},
                    description=f"Disconnected from MCP server: {server_id}",
                )
                return True

            except Exception as e:
                # Emit disconnection error event
                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                    level=observability.EventLevel.ERROR,
                    data={"server_id": server_id, "error": str(e)},
                    description=f"Error disconnecting from MCP server {server_id}: {str(e)}",
                )
                return False

    # =============================
    # MCP Specification Features
    # =============================

    async def list_resources(self, server_id: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        """List available resources from an MCP server.

        Args:
            server_id: The ID of the server to query
            cursor: Optional cursor for pagination

        Returns:
            Dictionary containing resources list and optional nextCursor

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.resource_discovery.list_resources(transport, cursor)

    async def read_resource(self, server_id: str, uri: str) -> Dict[str, Any]:
        """Read a specific resource from an MCP server.

        Args:
            server_id: The ID of the server to query
            uri: URI of the resource to read

        Returns:
            Resource content with text/blob data and metadata

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.resource_discovery.read_resource(transport, uri)

    async def list_prompts(self, server_id: str) -> list[Dict[str, Any]]:
        """List available prompts from an MCP server.

        Args:
            server_id: The ID of the server to query

        Returns:
            List of prompt definitions

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.prompt_discovery.list_prompts(transport)

    async def get_prompt(self, server_id: str, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get a specific prompt from an MCP server.

        Args:
            server_id: The ID of the server to query
            name: Name of the prompt to retrieve
            arguments: Optional arguments for prompt template substitution

        Returns:
            Prompt content with messages and metadata

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.prompt_discovery.get_prompt(transport, name, arguments)

    async def create_message(
        self,
        server_id: str,
        messages: list[Dict[str, Any]],
        model_preferences: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a message using MCP sampling/createMessage.

        Args:
            server_id: The ID of the server to use
            messages: List of messages for the conversation
            model_preferences: Optional model preferences
            system_prompt: Optional system prompt
            temperature: Optional temperature setting (0.0-1.0)
            max_tokens: Optional maximum tokens to generate

        Returns:
            Response containing the generated message and metadata

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.sampling_creator.create_message(
            transport=transport,
            messages=messages,
            model_preferences=model_preferences,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )

    async def list_templates(self, server_id: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        """List available templates from an MCP server.

        Args:
            server_id: The ID of the server to query
            cursor: Optional cursor for pagination

        Returns:
            Dictionary containing templates list and optional nextCursor

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.template_discovery.list_templates(transport, cursor)

    async def get_template(self, server_id: str, name: str) -> Dict[str, Any]:
        """Get a specific template from an MCP server.

        Args:
            server_id: The ID of the server to query
            name: Name of the template to retrieve

        Returns:
            Template content with template data and metadata

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.template_discovery.get_template(transport, name)

    async def ping_server(self, server_id: str, data: Optional[str] = None) -> Dict[str, Any]:
        """Send a ping to an MCP server.

        Args:
            server_id: The ID of the server to ping
            data: Optional data to include with ping

        Returns:
            Response containing pong and timing information

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        return await self.health_monitor.ping(transport, data)

    async def start_health_monitoring(self, server_id: str, ping_interval: float = 30.0) -> None:
        """Start continuous health monitoring for a server.

        Args:
            server_id: The ID of the server to monitor
            ping_interval: Interval between ping requests in seconds

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        # Update health monitor settings
        self.health_monitor.ping_interval = ping_interval

        # Start monitoring with connection lost callback
        async def on_connection_lost():
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_CONNECTION_LOST,
                level=observability.EventLevel.WARNING,
                data={"server_id": server_id},
                description=f"Connection lost to MCP server: {server_id}",
            )

        await self.health_monitor.start_monitoring(transport, on_connection_lost)

    async def stop_health_monitoring(self) -> None:
        """Stop health monitoring."""
        await self.health_monitor.stop_monitoring()

    def get_health_stats(self) -> Dict[str, Any]:
        """Get health monitoring statistics.

        Returns:
            Dictionary containing health stats
        """
        return self.health_monitor.get_health_stats()

    async def initialize_server_capabilities(
        self,
        server_id: str,
        client_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Initialize MCP connection with capabilities negotiation.

        Args:
            server_id: The ID of the server to initialize
            client_info: Optional client information and capabilities

        Returns:
            Server capabilities and information

        Raises:
            ValueError: If the server ID is not valid
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        transport = client.transport

        # Default client info if not provided
        if client_info is None:
            client_info = {
                "name": "MUXI MCP Client",
                "version": "1.0.0",
                "protocolVersion": "2024-11-05",
                "capabilities": self.capabilities_negotiator.get_supported_capabilities()
            }

        return await self.capabilities_negotiator.initialize_connection(transport, client_info)
