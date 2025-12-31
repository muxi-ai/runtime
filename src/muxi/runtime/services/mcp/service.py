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
import re
from typing import Any, Dict, Optional, List
from ...utils.datetime_utils import utc_now_iso

from ..llm import LLM
from .handler import MCPHandler, MCPConnectionError
from .transports import TransportDetector, ModernProtocolFeatures
from .resources.discovery import MCPResourceDiscovery
from .prompts.discovery import MCPPromptDiscovery
from .sampling.creator import MCPSamplingCreator
from .templates.discovery import MCPTemplateDiscovery
from .health.monitor import MCPHealthMonitor, MCPCapabilitiesNegotiator
from .. import observability, streaming
from ...datatypes.observability import InitEventFormatter
from ...formation.credentials import (
    MissingCredentialError,
    AmbiguousCredentialError,
)


class CredentialSelectionNeededError(Exception):
    """Raised when multiple credentials exist and LLM cannot determine which to use."""

    def __init__(
        self,
        service: str,
        user_id: str,
        available_credentials: list,
        ordered_credentials: list = None,
    ):
        self.service = service
        self.user_id = user_id
        self.available_credentials = available_credentials
        self.ordered_credentials = ordered_credentials or []
        # Handle both list of dicts and list of strings
        if available_credentials and isinstance(available_credentials[0], dict):
            names = [c['name'] for c in available_credentials]
        else:
            names = available_credentials

        super().__init__(
            f"Multiple credentials found for {service}, selection needed. "
            f"Available: {names}"
        )


# Regex pattern for user credential placeholders
USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")


def extract_service_name(server_id: str) -> str:
    """
    Extract the base service name from a server ID using robust regex pattern.

    Handles various formats:
    - "github_123" -> "github"
    - "github-prod" -> "github"
    - "github.com" -> "github"
    - "api-gateway-v2" -> "api"
    - None or empty -> "unknown"

    Args:
        server_id: The server identifier string

    Returns:
        The extracted service name or fallback
    """
    if not server_id:
        return "unknown"

    # First try to extract leading alphanumeric token
    match = re.match(r'^([A-Za-z0-9]+)', server_id)
    if match:
        return match.group(1).lower()

    # Fallback to full server_id if no match
    return server_id.lower()


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

        # Dictionary to store user-specific credentials per server
        # Structure: {server_id: {user_id: credentials}}
        self.user_credentials = {}

        # Dictionary to store discovered tools
        self.tool_registry = {}

        # Dictionary to store agent-specific tool registries
        # Structure: {"_shared": {server_id: tools}, "agent_id": {server_id: tools}}
        self.agent_tool_registry = {"_shared": {}}

        # Dictionary to store server configurations for ephemeral connections
        self.server_configs = {}

        # Transport cache to remember which transport worked for each server
        # Maps server_id to resolved transport type: "command", "streamable_http", or "http_sse"
        self.transport_cache = {}

        # Initialize MCP specification feature handlers
        self.resource_discovery = MCPResourceDiscovery()
        self.prompt_discovery = MCPPromptDiscovery()
        self.sampling_creator = MCPSamplingCreator()
        self.template_discovery = MCPTemplateDiscovery()
        self.health_monitor = MCPHealthMonitor()
        self.capabilities_negotiator = MCPCapabilitiesNegotiator()

    def get_tool_registry(self, agent_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get the tool registry for a specific agent.

        Args:
            agent_id: The ID of the agent. If None, returns all tools.

        Returns:
            Dictionary of server_id -> tools for the agent. Only returns agent-specific tools.
        """
        # If no agent_id provided, return all tools (backward compatibility)
        if agent_id is None:
            return self.tool_registry

        # Return both agent-specific tools AND shared tools
        # This allows agents to access global MCP servers while maintaining agent-specific ones
        result = {}

        # First, add shared tools if they exist
        if "_shared" in self.agent_tool_registry:
            result.update(self.agent_tool_registry["_shared"])

        # Then, add agent-specific tools (these can override shared ones if same server_id)
        if agent_id in self.agent_tool_registry:
            result.update(self.agent_tool_registry[agent_id])

        if result:
            # Successfully found tools for agent (including shared)
            return result
        else:
            # No tools found for agent
            return {}

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
        pass  # REMOVED: init-phase observe() call

        self.servers[server_id] = {
            "url": url,
            "command": command,
            "credentials": credentials or {},
            "model": model,
            "request_timeout": request_timeout or 60,
        }
        return server_id

    async def list_servers(self) -> List[str]:
        """
        List all registered server IDs.

        Returns:
            List of server IDs
        """
        return list(self.connections.keys())

    async def register_mcp_server(
        self,
        server_id: str,
        url: Optional[str] = None,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        transport_type: Optional[str] = "auto",
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
        original_credentials: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Register an MCP server with the service.

        This method establishes an actual connection to the MCP server and
        discovers available tools. It handles both HTTP/SSE and command-line
        based MCP servers with intelligent transport detection and caching.

        Args:
            server_id: Unique identifier for the MCP server
            url: URL for HTTP/SSE MCP servers
            command: Command for command-line MCP servers
            args: Optional list of arguments for command-line MCP servers
            transport_type: Transport type ('auto', 'streamable_http', 'http_sse', 'command')
            credentials: Resolved credentials for initial connection
            model: Optional model to use for this MCP handler
            request_timeout: Request timeout in seconds
            original_credentials: Original credentials with user placeholders (if any)
            agent_id: Optional agent ID for agent-specific MCP servers

        Returns:
            The server_id of the registered server

        Raises:
            Exception: If the server registration fails
        """
        # Create lock for this handler
        self.locks[server_id] = asyncio.Lock()

        # Handle command-line transport directly
        if command or transport_type == "command":
            return await self._connect_single_transport(
                server_id,
                url,
                command,
                args,
                "command",
                credentials,
                model,
                request_timeout,
                original_credentials,
                agent_id,
            )

        # Enhanced auto-detection with caching for HTTP-based servers
        if url and transport_type == "auto":
            try:
                # Use enhanced transport detector with caching
                (
                    detected_transport,
                    detection_metadata,
                ) = await TransportDetector.detect_with_fallback(
                    url=url,
                    timeout=min(request_timeout // 2, 30),
                    use_cache=True,
                    credentials=credentials,
                )

                # Get recommended URL for the detected transport
                recommended_url = TransportDetector.get_recommended_url(url, detected_transport)

                return await self._connect_single_transport(
                    server_id,
                    recommended_url,
                    command,
                    args,
                    detected_transport,
                    credentials,
                    model,
                    request_timeout,
                    original_credentials,
                    agent_id,
                )

            except MCPConnectionError as e:
                # Enhanced error handling with suggestion for manual override
                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_DETECTION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "server_id": server_id,
                        "error": str(e),
                        "url": url,
                        "suggestion": "Try specifying transport_type explicitly",
                    },
                    description=f"Transport detection failed for {server_id}: {e}",
                )

                raise MCPConnectionError(
                    f"Failed to auto-detect transport for {server_id}: {e}",
                    {
                        "server_id": server_id,
                        "url": url,
                        "suggestion": (
                            "Try specifying transport_type explicitly "
                            "('streamable_http', 'http_sse', or 'command')"
                        ),
                        "available_transports": [
                            "streamable_http",
                            "http_sse",
                            "command",
                        ],
                    },
                )

        # Handle generic "http" transport type with fallback
        if transport_type == "http" and url:
            return await self._connect_with_fallback(
                server_id,
                url,
                credentials,
                model,
                request_timeout,
                original_credentials,
                agent_id,
            )

        # Proceed with explicitly specified transport type
        return await self._connect_single_transport(
            server_id,
            url,
            command,
            args,
            transport_type,
            credentials,
            model,
            request_timeout,
            original_credentials,
            agent_id,
        )

    async def invoke_tool(
        self,
        server_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        request_timeout: Optional[int] = None,
        user_id: Optional[str] = None,
        credential_resolver: Optional[Any] = None,
        conversation_context: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a tool on an MCP server using ephemeral connection.

        This method executes a tool on the specified MCP server with the given
        parameters, using ephemeral connections for better security and isolation.
        It handles runtime credential resolution for user-specific authentication.

        Args:
            server_id: The ID of the server to use
            tool_name: The name of the tool to invoke
            parameters: The parameters to pass to the tool
            request_timeout: Optional timeout override for this specific request
            user_id: Optional user ID for credential resolution
            credential_resolver: Optional credential resolver for user-specific auth

        Returns:
            The result of the tool invocation as a dictionary with status and result

        Raises:
            ValueError: If the server ID is not valid
            MissingCredentialError: If required user credentials are not found
        """
        if server_id not in self.server_configs:
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

        # Get server configuration
        config = self.server_configs[server_id]
        resolved_auth = None

        # Check if this server requires user-specific credentials by looking for the pattern
        stored_creds = config.get("stored_credentials", {})
        has_user_placeholder = False

        # Check if stored credentials contain user credential placeholders
        def contains_user_placeholder(data):
            if isinstance(data, dict):
                for value in data.values():
                    if contains_user_placeholder(value):
                        return True
            elif isinstance(data, str):
                if USER_CREDENTIAL_PATTERN.search(data):
                    return True
            return False

        has_user_placeholder = contains_user_placeholder(stored_creds)

        # Check if this server requires user-specific credentials
        if has_user_placeholder:
            if not user_id:
                raise ValueError(
                    f"User ID required for MCP server '{server_id}' that uses user credentials"
                )

            # Check if we have cached credentials for this user
            if server_id not in self.user_credentials:
                self.user_credentials[server_id] = {}

            if user_id in self.user_credentials[server_id]:
                # Use cached credentials
                resolved_auth = self.user_credentials[server_id][user_id]
            else:
                # Need to resolve credentials from database
                if not credential_resolver:
                    raise ValueError(
                        f"Credential resolver required for MCP server '{server_id}' that uses user credentials"
                    )

                try:
                    # Extract service name from the user credential pattern in stored credentials
                    service_name = None

                    # Search for credential pattern in stored_creds
                    def find_service_name(data):
                        if isinstance(data, dict):
                            for value in data.values():
                                result = find_service_name(value)
                                if result:
                                    return result
                        elif isinstance(data, str):
                            match = USER_CREDENTIAL_PATTERN.match(data)
                            if match:
                                return match.group(1).lower()
                        return None

                    service_name = find_service_name(stored_creds)

                    if not service_name:
                        # Fallback: try to extract from server_id
                        service_name = extract_service_name(server_id)

                    # Resolve credentials from database
                    credentials = await credential_resolver.resolve(user_id, service_name)

                    if credentials is None:
                        # Trigger clarification flow
                        raise MissingCredentialError(service_name, user_id)

                    # If we got multiple credentials, use LLM to pick the best one
                    if isinstance(credentials, list):
                        try:
                            credentials = await self._select_best_credential_with_llm(
                                credentials,
                                parameters,
                                service_name,
                                conversation_context,
                                user_id,
                            )
                        except CredentialSelectionNeededError as e:
                            # LLM determined the request is ambiguous - pass it up to agent
                            e.user_id = user_id
                            raise

                        # If we reach here, LLM successfully selected a credential
                        # credentials now contains the selected credential

                    # Only format and cache credentials if we have a valid single credential
                    # At this point, credentials should be a single credential dict, not a list
                    if credentials and not isinstance(credentials, list):
                        # Format credentials based on stored_creds structure
                        # Replace the user credential placeholder with actual value
                        resolved_auth = self._replace_credential_in_auth(stored_creds, credentials)

                        # Cache the credentials
                        self.user_credentials[server_id][user_id] = resolved_auth
                    else:
                        raise ValueError("No valid credentials after selection")

                except MissingCredentialError:
                    # Re-raise to trigger clarification flow
                    raise
                except AmbiguousCredentialError:
                    # Re-raise to trigger clarification flow with credential options
                    raise
                except CredentialSelectionNeededError:
                    # Re-raise to let agent handle clarification
                    raise
                except Exception as e:
                    error_msg = (
                        f"Failed to resolve user credentials for MCP server '{server_id}': {str(e)}"
                    )
                    raise ValueError(error_msg) from e
        else:
            # Not using user credentials, use the stored credentials
            resolved_auth = config.get("stored_credentials")

        observability.observe(
            event_type=observability.ConversationEvents.MCP_TOOL_CALL_STARTED,
            level=observability.EventLevel.DEBUG,
            data={
                "server_id": server_id,
                "tool_name": tool_name,
                "has_user_credentials": resolved_auth is not None,
                "auth_type": (
                    "none" if resolved_auth is None
                    else resolved_auth.get("type") if isinstance(resolved_auth, dict)
                    else "string"
                ),
            },
            description=f"Executing MCP tool '{tool_name}' on server '{server_id}' with user credentials",
        )

        try:
            # Emit streaming event for tool execution (abstract tool names)
            # Extract service name from server_id
            service_name = extract_service_name(server_id)

            streaming.stream(
                "tool_call",
                f"Using {service_name} to complete this task...",
                stage="tool_execution",
                service=service_name,
                tool_name=tool_name,
                has_params=bool(parameters)
            )

            # Execute tool using ephemeral connection
            result = await self._execute_tool_ephemeral(
                server_id=server_id,
                tool_name=tool_name,
                params=parameters,
                user_credentials=resolved_auth,
                request_timeout=request_timeout,
            )

            # First check if we have a parsed response from the message handler
            if isinstance(result, dict):
                # Check for JSON-RPC error structure from message handler
                if result.get("status") == "error":
                    # Extract the error message from the JSON-RPC error structure
                    error_info = result.get("error", {})
                    if isinstance(error_info, dict):
                        error_message = error_info.get("message", "Unknown error")
                        error_data = error_info.get("data")
                        if error_data:
                            error_message = f"{error_message}: {error_data}"
                    else:
                        error_message = str(error_info) if error_info else "Unknown error"

                    # Emit error event
                    observability.observe(
                        event_type=observability.ConversationEvents.MCP_TOOL_CALL_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "server_id": server_id,
                            "tool_name": tool_name,
                            "error": error_message,
                            "error_code": (
                                error_info.get("code") if isinstance(error_info, dict) else None
                            ),
                        },
                        description=(f"MCP tool returned error: {tool_name} on {server_id}"),
                    )

                    return {"error": error_message, "status": "error"}

                # Check if it's a successful parsed response with a nested result
                if result.get("status") == "success" and "result" in result:
                    # Extract the actual result from the parsed response
                    result = result["result"]

                # Process result using modern protocol features
                # This handles structured output with isError field
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
                        "protocol_version": "2025-06-18",
                    },
                    description=(
                        f"MCP tool invocation completed with modern protocol: "
                        f"{tool_name} on {server_id}"
                    ),
                )

                return {
                    "result": processed_result,
                    "status": "success" if not processed_result["isError"] else "error",
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

    async def _connect_with_fallback(
        self,
        server_id: str,
        url: str,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
        original_credentials: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Attempt connection with automatic fallback between transports.
        """
        transports_to_try = ["streamable_http", "http_sse"]
        errors = {}

        for transport_type in transports_to_try:
            try:
                result = await self._connect_single_transport(
                    server_id,
                    url,
                    None,
                    None,
                    transport_type,
                    credentials,
                    model,
                    request_timeout,
                    original_credentials,
                    agent_id,  # Pass through agent_id for proper tool isolation
                )

                # Success - the transport type is already stored in cache by _connect_single_transport
                return result

            except Exception as e:
                errors[transport_type] = str(e)

                observability.observe(
                    event_type=observability.SystemEvents.MCP_TRANSPORT_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "server_id": server_id,
                        "transport_type": transport_type,
                        "error": str(e),
                        "will_retry": transport_type != transports_to_try[-1],
                    },
                    description=f"Transport {transport_type} failed for {server_id}",
                )

                if transport_type == transports_to_try[-1]:
                    # Both transports failed - create detailed error message
                    error_details = "\n".join([f"  - {t}: {errors[t]}" for t in transports_to_try])

                    # Check if this is an authentication error
                    is_auth_error = any("401" in str(e) or "unauthorized" in str(e).lower() for e in errors.values())

                    error_msg = (
                        f"Failed to register MCP server '{server_id}': Unable to connect to {url}\n"
                        f"Tried:\n{error_details}\n"
                        f"Check: {'Authentication credentials' if is_auth_error else 'URL accessibility, credentials, server status'}"  # noqa: E501
                    )

                    raise MCPConnectionError(
                        error_msg,
                        {
                            "server_id": server_id,
                            "url": url,
                            "tried_transports": transports_to_try,
                            "errors": errors,
                            "is_auth_error": is_auth_error,
                        },
                    )

                continue  # Try next transport

    async def _connect_single_transport(
        self,
        server_id: str,
        url: Optional[str],
        command: Optional[str],
        args: Optional[List[str]],
        transport_type: str,
        credentials: Optional[Dict[str, Any]] = None,
        model: Optional[LLM] = None,
        request_timeout: int = 60,
        original_credentials: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Connect using a specific transport type.
        """
        # Initialize the handler
        async with self.locks[server_id]:
            try:
                # Create and initialize the MCP handler
                handler = MCPHandler(model=model, tool_registry=self.tool_registry)

                # Set up connection with the transport factory
                server_name = server_id.replace("-", "_").lower()

                # Connect to the server using the specified transport type
                await handler.connect_server(
                    name=server_name,
                    url=url,
                    command=command,
                    args=args,
                    credentials=credentials,
                    request_timeout=request_timeout,
                    server_id=server_id,
                )

                # Store the handler
                self.handlers[server_id] = handler

                # Store connection info
                # If original_credentials were provided, it means user placeholders were detected
                # In this case, we used formation secrets for initial connection but need to
                # use user credentials at runtime
                stored_credentials = (
                    "$MUXI_USER_CREDENTIALS$" if original_credentials else credentials
                )

                self.connections[server_id] = {
                    "status": "connected",
                    "url": url,
                    "command": command,
                    "credentials": stored_credentials,
                    "server_name": server_name,
                    "transport_type": transport_type,
                    "request_timeout": request_timeout,
                }

                # Store original credentials if provided
                if original_credentials:
                    self.connections[server_id]["original_credentials"] = original_credentials

                # Discover available tools with modern protocol features
                try:
                    tools = await handler.list_tools(server_name)

                    # Enhanced tool registry with display names and metadata
                    self.tool_registry[server_id] = {}

                    # Also register in agent-specific registry if agent_id provided
                    if agent_id:
                        if agent_id not in self.agent_tool_registry:
                            self.agent_tool_registry[agent_id] = {}
                        self.agent_tool_registry[agent_id][server_id] = {}
                    else:
                        # Register in shared registry if no agent_id
                        self.agent_tool_registry["_shared"][server_id] = {}

                    for i, tool in enumerate(tools):
                        tool_name = tool.get("name", f"unknown_{i}")

                        # Use modern protocol features for better UX
                        tool_data = {
                            **tool,
                            "display_name": (ModernProtocolFeatures.extract_display_name(tool)),
                            "supports_structured_output": True,
                            "supports_elicitation": True,
                            "_meta": tool.get("_meta", {}),
                        }

                        # Register in main registry (for backward compatibility)
                        self.tool_registry[server_id][tool_name] = tool_data

                        # Register in agent-specific or shared registry
                        if agent_id:
                            self.agent_tool_registry[agent_id][server_id][tool_name] = tool_data
                        else:
                            self.agent_tool_registry["_shared"][server_id][tool_name] = tool_data

                except Exception:
                    self.tool_registry[server_id] = {}

                    # Also set empty registry in agent-specific registry
                    if agent_id:
                        if agent_id not in self.agent_tool_registry:
                            self.agent_tool_registry[agent_id] = {}
                        self.agent_tool_registry[agent_id][server_id] = {}
                    else:
                        self.agent_tool_registry["_shared"][server_id] = {}

                # Store server configuration for ephemeral connections
                # IMPORTANT: Store the original credentials format, not the transformed one
                self.server_configs[server_id] = {
                    "url": url,
                    "command": command,
                    "args": args,
                    "transport_type": transport_type,
                    "request_timeout": request_timeout,
                    "original_credentials": original_credentials,
                    # For ephemeral connections, store the original credentials
                    # which contain the user placeholders for runtime resolution
                    "stored_credentials": (
                        original_credentials if original_credentials else credentials
                    ),
                    # Flag to indicate if this server uses user-specific credentials
                    "uses_user_credentials": bool(original_credentials),
                }

                # Store the resolved transport type in cache
                self.transport_cache[server_id] = transport_type

                # Disconnect after tool discovery (Phase 1 of ephemeral connections)
                await handler.disconnect_server(server_name)

                # Remove the persistent handler but keep the configuration
                del self.handlers[server_id]

                # Emit MCP server registration completed event
                tools_count = len(self.tool_registry.get(server_id, {}))
                pass  # REMOVED: init-phase observe() call

                # Print clean formatted line
                details = f"{tools_count} tools available via {transport_type.replace('_', ' ')}"
                print(InitEventFormatter.format_ok(f"Connected to MCP '{server_id}'", details))

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

    async def _execute_tool_ephemeral(
        self,
        server_id: str,
        tool_name: str,
        params: Dict[str, Any],
        user_credentials: Optional[Dict[str, Any]] = None,
        request_timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a tool using ephemeral connection.

        Creates a fresh connection with user credentials, executes the tool,
        then immediately disconnects.

        Args:
            server_id: The ID of the server
            tool_name: The name of the tool to execute
            params: Parameters for the tool
            user_credentials: User-specific credentials to use
            request_timeout: Optional timeout for this request

        Returns:
            The tool execution result
        """
        if server_id not in self.server_configs:
            raise ValueError(f"Unknown MCP server: {server_id}")

        # Get server configuration
        config = self.server_configs[server_id]
        server_name = server_id.replace("-", "_").lower()

        # Ensure lock exists for ephemeral connections
        if server_id not in self.locks:
            self.locks[server_id] = asyncio.Lock()

        # Serialize connect/execute/disconnect sequence per server
        async with self.locks[server_id]:
            # Create fresh MCPHandler instance
            handler = MCPHandler(model=None, tool_registry=self.tool_registry)

            try:
                # Connect with user credentials using stored configuration
                await handler.connect_server(
                    name=server_name,
                    url=config.get("url"),
                    command=config.get("command"),
                    args=config.get("args"),
                    credentials=user_credentials,
                    request_timeout=request_timeout or config.get("request_timeout", 60),
                    server_id=server_id,
                )

                # Execute the tool
                result = await handler.execute_tool(
                    server_name=server_name,
                    tool_name=tool_name,
                    params=params,
                    cancellation_token=None,
                )

                return result

            finally:
                # Always disconnect, even if tool execution failed
                try:
                    await handler.disconnect_server(server_name)
                except Exception:
                    pass  # Ignore disconnect errors

    async def disconnect_server(self, server_id: str) -> bool:
        """
        Disconnect from an MCP server (cleans up registration).

        Since we use ephemeral connections, this method just cleans up
        the server registration and cached data.

        Args:
            server_id: The ID of the server to disconnect

        Returns:
            True if cleanup was successful, False otherwise
        """
        if server_id not in self.server_configs:
            return False

        try:
            # Remove from registries
            if server_id in self.server_configs:
                del self.server_configs[server_id]
            if server_id in self.connections:
                del self.connections[server_id]
            if server_id in self.locks:
                del self.locks[server_id]
            if server_id in self.tool_registry:
                del self.tool_registry[server_id]

            # Clear cached user credentials for this server
            if server_id in self.user_credentials:
                del self.user_credentials[server_id]

            # Emit disconnection success event
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                level=observability.EventLevel.INFO,
                data={"server_id": server_id},
                description=f"Unregistered MCP server: {server_id}",
            )
            return True

        except Exception as e:
            # Emit disconnection error event
            observability.observe(
                event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                level=observability.EventLevel.ERROR,
                data={"server_id": server_id, "error": str(e)},
                description=(f"Error unregistering MCP server {server_id}: {str(e)}"),
            )
            return False

    def clear_user_credentials_cache(
        self, server_id: Optional[str] = None, user_id: Optional[str] = None
    ):
        """
        Clear cached user credentials.

        Args:
            server_id: If provided, clear only for this server
            user_id: If provided, clear only for this user (requires server_id)
        """
        if server_id and user_id:
            # Clear specific user's credentials for a specific server
            if server_id in self.user_credentials:
                self.user_credentials[server_id].pop(user_id, None)
        elif server_id:
            # Clear all users' credentials for a specific server
            self.user_credentials.pop(server_id, None)
        else:
            # Clear all cached credentials
            self.user_credentials.clear()

    # =============================
    # MCP Specification Features
    # =============================

    def _get_transport_for_server(self, server_id: str):
        """Get transport object for a server with validation.

        Args:
            server_id: The ID of the server

        Returns:
            Transport object for the server

        Raises:
            ValueError: If server_id is invalid or not connected
        """
        if server_id not in self.handlers:
            raise ValueError(f"Unknown MCP server: {server_id}")

        handler = self.handlers[server_id]
        server_name = self.connections[server_id]["server_name"]

        # Get transport from the handler
        if server_name not in handler.active_connections:
            raise ValueError(f"Server {server_id} is not connected")

        client = handler.active_connections[server_name]
        return client.transport

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
        transport = self._get_transport_for_server(server_id)
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
        transport = self._get_transport_for_server(server_id)
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
        transport = self._get_transport_for_server(server_id)
        return await self.prompt_discovery.list_prompts(transport)

    async def get_prompt(
        self, server_id: str, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
        transport = self._get_transport_for_server(server_id)
        return await self.prompt_discovery.get_prompt(transport, name, arguments)

    async def create_message(
        self,
        server_id: str,
        messages: list[Dict[str, Any]],
        model_preferences: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
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
        transport = self._get_transport_for_server(server_id)
        return await self.sampling_creator.create_message(
            transport=transport,
            messages=messages,
            model_preferences=model_preferences,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
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
        transport = self._get_transport_for_server(server_id)
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
        transport = self._get_transport_for_server(server_id)
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
        transport = self._get_transport_for_server(server_id)
        return await self.health_monitor.ping(transport, data)

    async def start_health_monitoring(self, server_id: str, ping_interval: float = 30.0) -> None:
        """Start continuous health monitoring for a server.

        Args:
            server_id: The ID of the server to monitor
            ping_interval: Interval between ping requests in seconds

        Raises:
            ValueError: If the server ID is not valid
        """
        transport = self._get_transport_for_server(server_id)

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
        self, server_id: str, client_info: Optional[Dict[str, Any]] = None
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
        transport = self._get_transport_for_server(server_id)

        # Default client info if not provided
        if client_info is None:
            client_info = {
                "name": "MUXI MCP Client",
                "version": "1.0.0",
                "protocolVersion": "2024-11-05",
                "capabilities": self.capabilities_negotiator.get_supported_capabilities(),
            }

        return await self.capabilities_negotiator.initialize_connection(transport, client_info)

    def get_transport_cache_stats(self) -> Dict[str, Any]:
        """
        Get transport detection cache statistics.

        Returns:
            Dictionary with cache statistics and performance metrics
        """
        cache_stats = TransportDetector.get_cache_stats()

        return {
            "cache_statistics": cache_stats,
            "performance_impact": {
                "cache_hit_benefit": "Skips transport detection (~2-10 seconds)",
                "cache_miss_cost": "Performs transport detection tests",
                "cache_ttl_minutes": cache_stats.get("cache_ttl_minutes", 60),
            },
            "recommendations": {
                "clear_cache_if": "Transport detection seems incorrect",
                "disable_cache_if": "Debugging transport issues",
                "cache_is_helpful_when": "Connecting to same servers repeatedly",
            },
        }

    def clear_transport_cache(self) -> Dict[str, Any]:
        """
        Clear all cached transport detection data.

        Use this if transport detection seems to be using incorrect cached results.

        Returns:
            Status of cache clearing operation
        """
        try:
            old_stats = TransportDetector.get_cache_stats()
            TransportDetector.clear_transport_cache()

            observability.observe(
                event_type=observability.SystemEvents.MCP_TRANSPORT_CACHE_CLEARED,
                level=observability.EventLevel.INFO,
                data={
                    "cleared_entries": old_stats.get("total_entries", 0),
                    "reason": "manual_clear_requested",
                },
                description="MCP transport cache cleared manually",
            )

            return {
                "status": "success",
                "cleared_entries": old_stats.get("total_entries", 0),
                "message": "Transport cache cleared successfully",
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to clear transport cache",
            }

    async def test_transport_connectivity(
        self,
        url: str,
        transport_type: Optional[str] = None,
        timeout: int = 10,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Test connectivity to an MCP server with specific or auto-detected transport.

        This is useful for debugging connectivity issues before registering a server.

        Args:
            url: Server URL to test
            transport_type: Specific transport to test, or None for auto-detection
            timeout: Timeout in seconds for the test
            credentials: Optional authentication credentials for the server

        Returns:
            Detailed connectivity test results
        """
        test_results = {
            "url": url,
            "timestamp": utc_now_iso(),
            "timeout": timeout,
            "tests_performed": [],
            "recommended_action": None,
        }

        try:
            if transport_type:
                # Test specific transport
                test_passed = await TransportDetector._test_transport(
                    url, transport_type, timeout, credentials
                )

                test_results["tests_performed"].append(
                    {
                        "transport_type": transport_type,
                        "passed": test_passed,
                        "method": "specific_transport_test",
                    }
                )

                if test_passed:
                    recommended_url = TransportDetector.get_recommended_url(url, transport_type)
                    test_results["status"] = "success"
                    test_results["recommended_transport"] = transport_type
                    test_results["recommended_url"] = recommended_url
                    test_results["recommended_action"] = f"Use transport_type='{transport_type}'"
                else:
                    test_results["status"] = "failed"
                    test_results["recommended_action"] = "Try auto-detection or different transport"

            else:
                # Auto-detect best transport
                (
                    detected_transport,
                    detection_metadata,
                ) = await TransportDetector.detect_with_fallback(
                    url,
                    timeout,
                    use_cache=False,  # Don't use cache for testing
                    credentials=credentials,
                )

                test_results["status"] = "success"
                test_results["recommended_transport"] = detected_transport
                test_results["recommended_url"] = TransportDetector.get_recommended_url(
                    url, detected_transport
                )
                test_results["detection_metadata"] = detection_metadata
                test_results["recommended_action"] = (
                    f"Use transport_type='{detected_transport}' or 'auto'"
                )

        except Exception as e:
            test_results["status"] = "error"
            test_results["error"] = str(e)
            test_results["recommended_action"] = "Check server is running and accessible"

        return test_results

    async def disconnect_all(self) -> Dict[str, Any]:
        """
        Disconnect all connected MCP servers.

        This method is called during overlord shutdown to ensure proper cleanup
        of all MCP server connections and avoid async cleanup errors.

        Returns:
            Dict with disconnection results for each server
        """
        results = {
            "total_servers": len(self.handlers),
            "disconnected": 0,
            "failed": 0,
            "servers": {},
        }

        # Disconnect all handlers
        for server_id, handler in list(self.handlers.items()):
            try:
                # Cancel any pending requests first
                handler.cancel_all_requests()

                # Disconnect all servers in the handler
                for server_name in list(handler.servers.keys()):
                    await handler.disconnect_server(server_name)

                # Clean up handler reference
                del self.handlers[server_id]

                # Clean up connection info
                if server_id in self.connections:
                    del self.connections[server_id]

                # Clean up tool registry
                if server_id in self.tool_registry:
                    del self.tool_registry[server_id]

                results["disconnected"] += 1
                results["servers"][server_id] = "disconnected"

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTED,
                    level=observability.EventLevel.INFO,
                    data={"server_id": server_id},
                    description=f"Disconnected MCP server during shutdown: {server_id}",
                )

            except Exception as e:
                results["failed"] += 1
                results["servers"][server_id] = f"error: {str(e)}"

                observability.observe(
                    event_type=observability.SystemEvents.MCP_SERVER_DISCONNECTION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={"server_id": server_id, "error": str(e)},
                    description=f"Failed to disconnect MCP server during shutdown: {server_id}",
                )

        # Clear all registries
        self.handlers.clear()
        self.connections.clear()
        self.tool_registry.clear()

        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,  # Using SERVICE_STARTED as there's no STOPPED event
            level=observability.EventLevel.INFO,
            data={"service": "mcp", "action": "shutdown", **results},
            description="MCP service shutdown complete",
        )

        return results

    def _replace_credential_in_auth(
        self, auth_config: Dict[str, Any], credential_value: Any
    ) -> Dict[str, Any]:
        """
        Replace user credential placeholders in auth config with placeholders
            auth_config: Original auth config with placeholders
            credential_value: The actual credential value from database

        Returns:
            Auth config with placeholders replaced
        """
        USER_CREDENTIAL_PATTERN = re.compile(r"\$\{\{\s*user\.credentials\.([a-zA-Z0-9_-]+)\s*\}\}")

        def replace_recursive(data: Any, cred_val: Any = credential_value) -> Any:
            if isinstance(data, dict):
                # Process dictionary recursively
                result = {}
                for key, value in data.items():
                    result[key] = replace_recursive(value)
                return result
            elif isinstance(data, list):
                # Process list recursively
                return [replace_recursive(item) for item in data]
            elif isinstance(data, str):
                # Check if this is a user credential placeholder
                match = USER_CREDENTIAL_PATTERN.match(data)
                if match:
                    # Replace with actual credential
                    if isinstance(cred_val, dict):
                        # If credential is a dict, try to extract the token
                        for field in [
                            "token",
                            "api_key",
                            "access_token",
                            "key",
                            "password",
                        ]:
                            if field in cred_val:
                                token_value = cred_val[field]
                                # Strip quotes if present
                                if isinstance(token_value, str):
                                    token_value = token_value.strip().strip('"').strip("'")
                                return token_value
                        # If no standard field found, return as is
                        return cred_val
                    else:
                        # String or other type, use directly
                        # Strip quotes if it's a string
                        if isinstance(cred_val, str):
                            cred_val = cred_val.strip().strip('"').strip("'")
                        return cred_val
                else:
                    return data
            else:
                # Non-string, non-dict, non-list values pass through
                return data

        result = replace_recursive(auth_config)

        return result

    def get_user_credential_servers(self) -> List[str]:
        """
        Get list of MCP servers that use user credentials.

        Returns:
            List of server IDs that authenticate using user-specific credentials
        """
        return [
            server_id
            for server_id, config in self.server_configs.items()
            if config.get("uses_user_credentials", False)
        ]

    async def _select_best_credential_with_llm(
        self,
        credential_list: List[Dict[str, Any]],
        parameters: Dict[str, Any],
        service_name: str,
        conversation_context: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Use LLM to select the best credential from multiple options based on user parameters and conversation context.

        Args:
            credential_list: List of credentials with names and credential data
            parameters: Tool parameters that may contain user intent
            service_name: Name of the service (e.g., 'github')
            conversation_context: Recent conversation messages for context
            user_id: Optional user identifier used only for error context and caching; not included in LLM prompts

        Returns:
            Selected credential data or None if LLM can't decide
        """
        try:
            # Extract user intent from parameters
            user_intent = ""
            for key, value in parameters.items():
                if isinstance(value, str):
                    user_intent += f"{key}: {value} "

            # Build conversation context
            context_text = ""
            if conversation_context and len(conversation_context) > 0:
                context_text = "\n".join(conversation_context[-5:])  # Last 5 messages

                # Also extract the most recent user message for better context
                for msg in reversed(conversation_context):
                    if "User:" in msg or "list" in msg.lower():
                        user_intent = msg + " " + user_intent
                        break

            # Always ask the LLM to decide when there are multiple credentials
            # The LLM can determine if the request is ambiguous even without clear user intent

            # Create LLM prompt
            credential_names = [cred["name"] for cred in credential_list]

            prompt_parts = [f"The user wants to use {service_name}."]

            if context_text.strip():
                prompt_parts.append(f"Recent conversation context:\n{context_text}")

            if user_intent.strip():
                prompt_parts.append(f"Current request details: {user_intent.strip()}")

            prompt_parts.extend(
                [
                    f"\nThey have the following {service_name} credentials available:",
                    '\n'.join(f"{i+1}. {name}" for i, name in enumerate(credential_names)),
                    "\nWhich credential should be used?",
                    "\nPRIORITY ORDER (most important first):",
                    "1. Use the MOST RECENTLY mentioned account in the conversation context",
                    "2. If user says 'use my [account name]', prioritize that account for all future requests",
                    "3. Exact name matches in the current request",
                    "4. Partial matches when the request contains the beginning of the credential name (e.g. 'lily' matches both 'lily account' AND 'lily acme')",  # noqa: E501
                    "5. Account ownership references (e.g. 'my acme account')",
                    "\n",
                    "If the conversation shows the user previously specified an account preference, use that account.",
                    "If no clear match or ambiguous, set selection to 0 to trigger clarification.",
                    "IMPORTANT: Match partial names from the beginning - 'lily' matches 'lily acme'. However, if user asks for 'acme account' but only has 'lily acme', this is AMBIGUOUS since 'acme' is not at the beginning. Return selection: 0.",  # noqa: E501
                    "IMPORTANT: If user uses generic terms like 'my account', 'my repositories', 'my GitHub' without specifying which account, this is AMBIGUOUS with multiple credentials. Return selection: 0.",  # noqa: E501
                    "\n",
                    "Reply with JSON format:",
                    "{",
                    '  "selection": 2,  // number 1-N for clear match, or 0 if ambiguous',  # noqa: E501
                    '  "ordered_credentials": [2, 1]  // all credentials ordered from most likely to least likely match',  # noqa: E501
                    "}",
                    "\n",
                    "If selection is 0 (ambiguous), the ordered_credentials should rank all options from most likely match to least likely match based on the user's request.",  # noqa: E501
                ]
            )

            prompt = "\n".join(prompt_parts)

            # Use the standard LLM class with default configuration from formation
            try:
                # Create LLM instance - it will use the default model from formation YAML
                llm = LLM()

                # Use the standard chat method with specific parameters for this use case
                messages = [{"role": "user", "content": prompt}]
                response = await llm.chat(messages, max_tokens=100, temperature=0.1)
            except Exception:
                # If LLM fails, we should raise an error to trigger clarification
                # Return None to indicate we couldn't select, which should trigger clarification
                # Use the correct constructor signature for CredentialSelectionNeededError
                raise CredentialSelectionNeededError(
                    service=service_name,
                    user_id=user_id or "unknown",
                    available_credentials=credential_names,
                    ordered_credentials=list(range(1, len(credential_names) + 1))
                )

            # Parse the JSON response
            import json
            import re

            try:
                # Extract JSON from response (might have extra text)
                json_match = re.search(r"\{[^}]*\}", response.strip())
                if json_match:
                    json_str = json_match.group(0)
                    result = json.loads(json_str)

                    selection = result.get("selection", 0)
                    ordered_credentials = result.get(
                        "ordered_credentials", list(range(1, len(credential_list) + 1))
                    )

                    if 1 <= selection <= len(credential_list):
                        # Clear selection - use the selected credential
                        selected_cred = credential_list[selection - 1]
                        return selected_cred["credentials"]
                    elif selection == 0:
                        # Ambiguous - trigger credential selection needed error
                        # The agent will decide whether to trigger clarification
                        # Pass only the credential names, not the full dict objects
                        raise CredentialSelectionNeededError(
                            service=service_name,
                            user_id=str(user_id or ""),  # Ensure user_id is always a string
                            available_credentials=credential_names,  # Use names list, not full dicts
                            ordered_credentials=ordered_credentials,
                        )

            except (json.JSONDecodeError, KeyError):
                # Fallback to old number parsing
                match = re.search(r"\b([0-9]+)\b", response.strip())
                if match:
                    choice = int(match.group(1))
                    if 1 <= choice <= len(credential_list):
                        selected_cred = credential_list[choice - 1]
                        return selected_cred["credentials"]

            # If LLM didn't give a clear answer, raise CredentialSelectionNeededError
            raise CredentialSelectionNeededError(
                service=service_name,
                user_id=str(user_id or ""),  # Ensure user_id is always a string
                available_credentials=credential_names,  # Use names list, not full dicts
                ordered_credentials=list(range(1, len(credential_list) + 1)),
            )

        except Exception:
            # LLM credential selection failed
            # Don't fallback - raise the error to trigger proper handling
            raise
