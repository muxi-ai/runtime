"""
MCP (Model Context Protocol) coordination for the Overlord.

This module handles all MCP server registration, tool discovery, and coordination
that was previously embedded in the main Overlord class.
"""

from typing import Dict, List, Optional, Any
import re

from ...services.mcp.service import MCPService
from ...services.llm import LLM
from ...datatypes.schema import MCPServiceSchema
from ...datatypes import observability
from ..credentials import MissingCredentialError


class MCPCoordinator:
    """
    Handles MCP server coordination for the Overlord.

    This class encapsulates all MCP-related functionality that was previously
    embedded in the main Overlord class, providing cleaner separation of concerns
    and better maintainability for Model Context Protocol operations.
    """

    # Pattern to match user credential placeholders in configuration
    USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")

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

    async def _resolve_user_credentials(
        self, auth: Dict[str, Any], user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Resolve user credentials in auth configuration.

        This method handles ${{ user.credentials.SERVICE }} placeholders by
        fetching user-specific credentials from the database at runtime.

        Args:
            auth: Authentication configuration that may contain credential placeholders
            user_id: The user ID for credential resolution

        Returns:
            Auth config with credentials resolved

        Raises:
            MissingCredentialError: If required credentials are not found
        """
        if not auth or not user_id or not self.overlord.credential_resolver:
            return auth

        async def resolve_auth_recursive(data: Any) -> Any:
            """Recursively resolve credential placeholders in nested data structures."""
            if isinstance(data, dict):
                # Process dictionary recursively
                resolved_dict = {}
                for key, value in data.items():
                    resolved_dict[key] = await resolve_auth_recursive(value)
                return resolved_dict
            elif isinstance(data, list):
                # Process list recursively
                return [await resolve_auth_recursive(item) for item in data]
            elif isinstance(data, str):
                # Check if this is a user credential placeholder
                match = self.USER_CREDENTIAL_PATTERN.match(data)
                if match:
                    service = match.group(1).lower()  # Normalize to lowercase

                    # Resolve credential from database
                    credentials = await self.overlord.credential_resolver.resolve(user_id, service)

                    if credentials is None:
                        # Trigger clarification flow by raising error
                        raise MissingCredentialError(service, user_id)

                    # If we got multiple credentials, use the first one for now
                    # (MCP coordinator doesn't have access to user message context)
                    if isinstance(credentials, list):
                        credentials = credentials[0]["credentials"]

                    # Replace placeholder with actual credential
                    # If credentials is a dict, extract the appropriate field
                    if isinstance(credentials, dict):
                        # Common patterns: token, api_key, access_token, key
                        for field in ["token", "api_key", "access_token", "key", "password"]:
                            if field in credentials:
                                return credentials[field]
                        # If no standard field found, use the whole dict
                        return credentials
                    else:
                        # If it's a string or other type, use directly
                        return credentials
                else:
                    # Not a user credential, keep as-is
                    return data
            else:
                # Non-string, non-dict, non-list values pass through
                return data

        return await resolve_auth_recursive(auth)

    async def resolve_mcp_auth_for_execution(
        self, server_id: str, auth: Dict[str, Any], user_id: str
    ) -> Dict[str, Any]:
        """
        Resolve authentication for MCP tool execution.

        This method is called at tool execution time when we have user context.
        It resolves any ${{ user.credentials.* }} placeholders in the auth config.

        Args:
            server_id: The MCP server ID
            auth: Authentication configuration that may contain credential placeholders
            user_id: The user ID for credential resolution

        Returns:
            Auth config with all credentials resolved

        Raises:
            MissingCredentialError: If required credentials are not found
        """
        if not auth or not user_id:
            return auth

        try:
            # Resolve user credentials now that we have user context
            resolved_auth = await self._resolve_user_credentials(auth, user_id)
            return resolved_auth
        except MissingCredentialError:
            # Re-raise to trigger clarification flow
            raise
        except Exception as e:
            # Log credential resolution failure
            # Error logged via observability
            raise ValueError(
                f"Failed to resolve user credentials for MCP server {server_id}: {str(e)}"
            ) from e

    async def _resolve_initialization_credentials(
        self, auth_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Replace user.credentials.X with secrets.USER_CREDENTIALS_X for initialization.

        This method transforms user credential placeholders to initialization secret patterns
        that can be resolved during formation startup when there's no user context.

        Args:
            auth_config: Authentication configuration that may contain user credential placeholders

        Returns:
            Auth config with user credential patterns replaced by initialization secret patterns

        Example:
            Input:  {"token": "${{ user.credentials.github }}"}
            Output: {"token": "${{ secrets.USER_CREDENTIALS_GITHUB }}"}
        """
        if not auth_config:
            return auth_config

        def transform_recursive(data: Any) -> Any:
            """Recursively transform credential placeholders in nested data structures."""
            if isinstance(data, dict):
                # Process dictionary recursively
                transformed_dict = {}
                for key, value in data.items():
                    transformed_dict[key] = transform_recursive(value)
                return transformed_dict
            elif isinstance(data, list):
                # Process list recursively
                return [transform_recursive(item) for item in data]
            elif isinstance(data, str):
                # Check if this is a user credential placeholder
                match = self.USER_CREDENTIAL_PATTERN.match(data)
                if match:
                    service_name = match.group(1)
                    # Transform to initialization secret pattern
                    # user.credentials.github -> secrets.USER_CREDENTIALS_GITHUB
                    initialization_secret = f"USER_CREDENTIALS_{service_name.upper()}"
                    return f"${{{{ secrets.{initialization_secret} }}}}"
                else:
                    return data
            else:
                # Non-string, non-dict, non-list values pass through
                return data

        return transform_recursive(auth_config)

    def _validate_credential_format(self, credential: str, service_name: str) -> bool:
        """
        Validate that a credential has the expected format for the service.

        Args:
            credential: The credential value to validate
            service_name: The service name (e.g., 'github', 'linear')

        Returns:
            bool: True if valid, False otherwise

        Raises:
            ValueError: If credential format is invalid
        """
        if not credential or not isinstance(credential, str) or not credential.strip():
            raise ValueError(f"Invalid {service_name} credential: empty or not a string")

        # Service-specific validation
        if service_name.lower() == "github":
            # GitHub tokens start with ghp_ or github_pat_
            if not (credential.startswith("ghp_") or credential.startswith("github_pat_")):
                raise ValueError(
                    "Invalid GitHub credential format. GitHub tokens should start with 'ghp_' or 'github_pat_'"
                )

        return True

    async def _validate_resolved_credentials(
        self, auth: Dict[str, Any], final_auth: Dict[str, Any], server_id: str
    ) -> None:
        """
        Validate resolved credentials for MCP server authentication.

        This method extracts service names from the original auth configuration,
        finds the resolved token values, and validates their format.

        Args:
            auth: Original auth configuration with potential user.credentials.* references
            final_auth: Resolved auth configuration with actual credential values
            server_id: The MCP server ID for error messages

        Raises:
            ValueError: If credential format validation fails
        """
        # Pattern to match user credential references
        USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}}")

        def find_services(obj):
            """Recursively find service names in auth config."""
            services = []
            if isinstance(obj, str):
                match = USER_CREDENTIAL_PATTERN.match(obj)
                if match:
                    services.append(match.group(1))
            elif isinstance(obj, dict):
                for value in obj.values():
                    services.extend(find_services(value))
            elif isinstance(obj, list):
                for item in obj:
                    services.extend(find_services(item))
            return services

        # Find which service credentials were referenced
        services = find_services(auth)

        if services and final_auth:
            # Extract the resolved credential value (look for token field specifically)
            if isinstance(final_auth, dict):
                # For bearer auth, the token is in the 'token' field
                token_value = final_auth.get("token")
                if (
                    token_value
                    and isinstance(token_value, str)
                    and not token_value.startswith("${{")
                ):
                    # This is a resolved credential - validate format
                    for service in services:
                        try:
                            self._validate_credential_format(token_value, service)
                        except ValueError as ve:
                            raise ValueError(
                                f"MCP server '{server_id}' initialization failed: {str(ve)}"
                            ) from ve

    async def register_mcp_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        auth: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: Optional[int] = None,
        transport_type: Optional[str] = None,
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
            args: Optional list of arguments for command-line MCP servers.
            auth: Optional authentication configuration for the MCP server.
                Supports secrets interpolation with ${{ secrets.NAME }} syntax.
                User credentials (${{ user.credentials.SERVICE }}) are stored
                but resolved later at tool execution time.
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

        # Process auth configuration - only interpolate secrets at registration time
        # User credentials will be resolved later at tool execution time
        final_auth = auth
        if auth:
            try:
                # First, transform user.credentials.* to USER_CREDENTIALS_* for initialization
                initialization_auth = await self._resolve_initialization_credentials(auth)

                # Then interpolate all secrets (including transformed ones)
                final_auth = await self.overlord.secrets_interpolator.interpolate_secrets(
                    initialization_auth
                )

                # Validate credential format if we resolved any initialization credentials
                if final_auth != auth:  # Credentials were transformed/resolved
                    await self._validate_resolved_credentials(auth, final_auth, server_id)

            except Exception as e:
                # Log secret interpolation failure - this is critical for auth debugging
                error_msg = f"Secret interpolation failed for MCP server {server_id}: {str(e)}"

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_REGISTRATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "server_id": server_id,
                        "url": url,
                        "command": command,
                        "error_type": "secret_interpolation_failed",
                        "error": str(e),
                    },
                    description=f"MCP server '{server_id}' registration failed due to secret interpolation error",
                )

                # Do NOT continue with original auth - this would cause silent auth failures
                # Instead, raise the error so the caller knows secrets interpolation failed
                raise ValueError(
                    f"Failed to interpolate secrets for MCP server {server_id}: {str(e)}"
                ) from e

        # Register the server with the MCP service
        try:

            res = await self.mcp_service.register_mcp_server(
                server_id=server_id,
                url=url,
                command=command,
                args=args,
                transport_type=transport_type,
                credentials=final_auth,
                original_credentials=auth,  # Pass original auth with user credential placeholders
                model=model,
                request_timeout=timeout,
            )

            # Verify that the server was successfully registered
            # The register_mcp_server call will throw if connection fails
            # Just verify the server exists in our registry
            servers = await self.mcp_service.list_servers()
            if server_id not in servers:
                raise ConnectionError(
                    f"MCP server '{server_id}' registration failed - server not found after registration"
                )

            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_REGISTERED,
                level=observability.EventLevel.INFO,
                data={"server_id": server_id, "tool_count": len(res.get('tools', []))},
                description=f"MCP server '{server_id}' registered successfully",
            )
            return res

        except Exception as e:
            # Fail fast on any MCP server connection/query errors
            error_msg = f"Failed to query MCP server '{server_id}': {str(e)}"
            # Error logged via observability

            # Re-raise with clear error message
            raise ConnectionError(error_msg) from e

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

        pass  # REMOVED: init-phase observe() call
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

        observability.observe(
            event_type=observability.SystemEvents.MCP_SERVER_UNREGISTERED,
            level=observability.EventLevel.INFO,
            data={"server_id": server_id},
            description=f"MCP server '{server_id}' unregistered successfully",
        )

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
