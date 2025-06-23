"""
MCP (Model Context Protocol) coordination for the Overlord.

This module handles all MCP server registration, tool discovery, and coordination
that was previously embedded in the main Overlord class.
"""

from typing import Dict, List, Optional, Any

from ...services.mcp.service import MCPService
from ...services.llm import LLM
from ...datatypes.schema import MCPServiceSchema


class MCPCoordinator:
    """
    Handles MCP server coordination for the Overlord.

    This class encapsulates all MCP-related functionality that was previously
    embedded in the main Overlord class, providing cleaner separation of concerns
    and better maintainability for Model Context Protocol operations.
    """

    def __init__(self, overlord, config: Optional[MCPServiceSchema] = None):
        """
        Initialize the MCP coordinator with standardized configuration.

        Args:
            overlord: Reference to the overlord instance
            config: Optional MCP service configuration. If not provided,
                    defaults will be used.
        """
        self.overlord = overlord

        # Use provided config or create default
        self.config = config or MCPServiceSchema()

        # Validate configuration
        self.config.validate()

        # Get singleton MCP service instance
        self.mcp_service = MCPService.get_instance()

        # Apply configuration
        self._apply_configuration()

    def _apply_configuration(self) -> None:
        """Apply the standardized configuration to internal settings."""
        # Server limits
        self.max_concurrent_servers = self.config.max_concurrent_servers

        # Timeout settings
        self.default_timeout = self.config.default_timeout
        self.operation_timeout = self.config.timeout or 30.0

        # Retry settings
        self.retry_attempts = self.config.retry_attempts
        self.retry_delay = self.config.retry_delay

    async def register_mcp_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        auth: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: Optional[int] = None,
    ) -> str:
        """
        Register an MCP server with the centralized MCP service with secrets support.

        This method adds a Model Context Protocol (MCP) server to the overlord,
        making its tools available to agents. Supports GitHub Actions-style secrets
        interpolation in credentials. MCP servers can be external HTTP services,
        local command-line tools, or other tool providers that implement the MCP protocol.

        Args:
            server_id: Unique identifier for the MCP server. Used to reference the
                server when invoking tools or updating its configuration.
            url: URL for HTTP/SSE MCP servers. Required for web-based MCP servers,
                providing the endpoint to send MCP requests to.
            command: Command for command-line MCP servers. Required for CLI-based MCP
                servers, specifying the command to execute.
            auth: Optional authentication configuration for the MCP server.
                Supports secrets interpolation with ${{ secrets.NAME }} syntax.
                Format depends on the server's requirements.
            model: Optional model to use for this MCP handler. Some MCP servers
                require a model for processing tool invocations.
            request_timeout: Optional timeout in seconds for requests to this server.
                Defaults to the coordinator's default timeout if not specified.

        Returns:
            The server_id of the registered server, confirming successful registration.

        Raises:
            ValueError: If neither url nor command is provided, or if both are provided.
            ConnectionError: If the MCP server cannot be contacted during registration.
        """
        # Check if we've reached max concurrent servers
        current_server_count = len(await self.mcp_service.list_servers())
        if current_server_count >= self.max_concurrent_servers:
            raise ValueError(
                f"Maximum concurrent MCP servers ({self.max_concurrent_servers}) reached. "
                f"Increase max_concurrent_servers in configuration or remove unused servers."
            )

        # Use configured default timeout if none specified
        timeout = request_timeout if request_timeout is not None else self.default_timeout

        # Interpolate secrets in auth if provided
        final_auth = auth
        if auth:
            try:
                final_auth = await self.overlord.interpolate_secrets(auth)
            except Exception as e:
                #  Warning - TODO: add observability
                # SystemEvents.MCP_SERVER_REGISTRATION_FAILED
                _ = e  # remove this after implementing observability
                # Continue with original auth

        # Register the server with the MCP service
        res = await self.mcp_service.register_mcp_server(
            server_id=server_id,
            url=url,
            command=command,
            credentials=final_auth,
            model=model,
            request_timeout=timeout,
        )

        #  Info - TODO: add observability
        # ConversationEvents.MCP_SERVER_REGISTERED
        return res

    async def list_mcp_tools(
        self, server_id: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        List available tools from MCP servers.

        This method retrieves information about the tools available from registered
        MCP servers, including their names, descriptions, parameters, and the servers
        they belong to.

        Args:
            server_id: Optional server ID to list tools from a specific server.
                If not provided, lists tools from all registered servers.

        Returns:
            Dictionary mapping server IDs to lists of available tools, where each
            tool is represented as a dictionary with:
            - "name": The tool's name
            - "description": The tool's description
            - "parameters": The tool's parameter schema (if any)
            - "returns": The tool's return type schema (if available)

            Example:
            {
                "weather_server": [
                    {
                        "name": "get_weather",
                        "description": "Get current weather for a location",
                        "parameters": {...}
                    }
                ]
            }
        """
        res = await self.mcp_service.list_tools(server_id=server_id)

        # Info - TODO: add observability
        # SystemEvents.MCP_TOOL_DISCOVERY_COMPLETED
        return res

    def get_mcp_service(self) -> MCPService:
        """
        Get the centralized MCP service.

        This method provides access to the underlying MCPService instance that
        manages all MCP servers and tool invocations.

        Returns:
            The MCPService instance used by this overlord.
        """
        return self.mcp_service

    def get_configuration(self) -> MCPServiceSchema:
        """
        Get the current MCP service configuration.

        Returns:
            The current MCPServiceSchema instance
        """
        return self.config

    def update_configuration(self, config: MCPServiceSchema) -> None:
        """
        Update the MCP service configuration.

        Args:
            config: New MCP service configuration

        Raises:
            ValueError: If configuration validation fails
        """
        # Validate new configuration
        config.validate()

        # Update configuration
        self.config = config

        # Apply new configuration
        self._apply_configuration()

    async def unregister_mcp_server(self, server_id: str) -> None:
        """
        Unregister an MCP server.

        Args:
            server_id: ID of the server to unregister

        Raises:
            KeyError: If server_id is not registered
        """
        await self.mcp_service.unregister_server(server_id)

        #  Info - TODO: add observability
        # ConversationEvents.MCP_SERVER_UNREGISTERED

    async def get_server_status(self, server_id: str) -> Dict[str, Any]:
        """
        Get the status of a specific MCP server.

        Args:
            server_id: ID of the server to check

        Returns:
            Dict with server status information including:
            - "connected": Whether the server is connected
            - "tools_count": Number of tools available
            - "last_error": Last error message if any
            - "uptime": Server uptime in seconds
        """
        servers = await self.mcp_service.list_servers()
        if server_id not in servers:
            raise KeyError(f"MCP server '{server_id}' not found")

        server_info = servers[server_id]
        tools = await self.mcp_service.list_tools(server_id=server_id)

        return {
            "connected": server_info.get("connected", False),
            "tools_count": len(tools.get(server_id, [])),
            "last_error": server_info.get("last_error"),
            "uptime": server_info.get("uptime", 0),
        }
