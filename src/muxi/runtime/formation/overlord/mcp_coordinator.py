"""
MCP (Model Context Protocol) coordination for the Overlord.

This module handles all MCP server registration, tool discovery, and coordination
that was previously embedded in the main Overlord class.
"""

from typing import Dict, List, Optional, Any

from ...services.mcp.service import MCPService
from ...services.llm import LLM


class MCPCoordinator:
    """
    Handles MCP server coordination for the Overlord.

    This class encapsulates all MCP-related functionality that was previously
    embedded in the main Overlord class, providing cleaner separation of concerns
    and better maintainability for Model Context Protocol operations.
    """

    def __init__(self, overlord):
        """
        Initialize the MCP coordinator.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord
        self.mcp_service = MCPService.get_instance()

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
                Defaults to the overlord's global timeout setting if not specified.

        Returns:
            The server_id of the registered server, confirming successful registration.

        Raises:
            ValueError: If neither url nor command is provided, or if both are provided.
            ConnectionError: If the MCP server cannot be contacted during registration.
        """
        # Use overlord's default timeout if none specified
        timeout = request_timeout if request_timeout is not None else self.overlord.request_timeout

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
