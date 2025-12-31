"""
A2A (Agent-to-Agent) coordination for the Overlord.

This module handles all A2A communication coordination, including agent discovery,
external registry management, and A2A server operations that were previously
embedded in the main Overlord class.
"""

import asyncio
import time
from typing import Dict, List, Optional, Any

from ...datatypes.schema import A2AServiceSchema
from ...datatypes.observability import InitEventFormatter
from ...services import observability
from ...services.a2a.models import AgentCard
from ...services.a2a.models_adapter import ModelsAdapter


class A2ACoordinator:
    """
    Handles A2A communication coordination for the Overlord.

    This class encapsulates all A2A-related functionality that was previously
    embedded in the main Overlord class, providing cleaner separation of concerns
    and better maintainability for Agent-to-Agent communication operations.
    """

    def __init__(self, overlord, config: Optional[A2AServiceSchema] = None):
        """
        Initialize the A2A coordinator with standardized configuration.

        Args:
            overlord: Reference to the overlord instance
            config: Optional A2A service configuration. If not provided,
                    defaults will be used.
        """
        self.overlord = overlord

        # Use provided config or create default
        self.config = config or A2AServiceSchema()

        # Validate configuration
        self.config.validate()

        # Apply configuration
        self._apply_configuration()

        # Planning filter will be initialized later when request_analyzer is available
        self.planning_filter = None

    def initialize_planning_filter(self) -> None:
        """Initialize planning filter after request_analyzer is available."""
        if self.planning_filter is not None:
            return  # Already initialized

        formation_config = getattr(self.overlord, "formation_config", {})
        filtering_config = formation_config.get("a2a", {}).get("filtering", {})

        # Initialize if filtering is enabled and dependencies are available
        if filtering_config.get("enabled", False):
            if (
                hasattr(self.overlord, "a2a_cache_manager")
                and self.overlord.a2a_cache_manager
                and hasattr(self.overlord, "request_analyzer")
                and self.overlord.request_analyzer
            ):
                from ...services.a2a.planning_filter import PlanningAgentFilter
                self.planning_filter = PlanningAgentFilter(self.overlord, filtering_config)
            else:
                missing = []
                if not hasattr(self.overlord, "a2a_cache_manager"):
                    missing.append("a2a_cache_manager")
                if not hasattr(self.overlord, "request_analyzer"):
                    missing.append("request_analyzer")
                if missing:
                    # Fail fast: A2A filtering is configured but dependencies are missing
                    # This indicates a configuration or initialization order problem
                    raise RuntimeError(
                        f"A2A filtering is enabled but required components are missing: {', '.join(missing)}. "
                        f"Check that these components are initialized before A2A coordinator."
                    )

    def _apply_configuration(self) -> None:
        """Apply the standardized configuration to internal settings."""
        # Server settings
        self.server_enabled = self.config.server_enabled
        self.server_host = self.config.server_host
        self.server_port = self.config.server_port

        # Registry settings
        self.external_registry_enabled = self.config.external_registry_enabled
        self.registry_url = self.config.registry_url
        self.registration_timeout = self.config.registration_timeout

        # Security settings
        self.require_auth = self.config.require_auth
        self.allowed_origins = self.config.allowed_origins or []

        # Timeout settings from base config
        self.operation_timeout = self.config.timeout or 30.0

    def get_available_agents_for_a2a(
        self, requesting_agent_id: str, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get available agents for A2A (Agent-to-Agent) communication.

        This is the simple discovery mechanism for local formations where all agents
        are managed by the same Overlord. Agents can call this to discover other
        agents they can communicate with.

        Args:
            requesting_agent_id: ID of the agent making the discovery request
            capability_filter: Optional list of required capabilities to filter by

        Returns:
            Dict mapping agent_id to normalized agent information:
            - agent_id: Unique identifier for the agent
            - description: Agent's description
            - capabilities: List of agent capabilities
            - type: "internal" (always internal for this method)
            - url: agent:// URL for direct agent communication (e.g., "agent://calendar-agent")
            - transport: Transport hint ("agent" for internal agents)
            - formation: Formation name
            - preference_score: 0.0 (internal agents are always preferred)
            - status: 'active' (always active if in registry)

        Example:
            >>> # Agent A discovers other agents
            >>> available = overlord.get_available_agents_for_a2a('weather-agent')
            >>> print(available)
            {
                'calendar-agent': {
                    'agent_id': 'calendar-agent',
                    'description': 'Manages calendar events',
                    'capabilities': ['calendar_lookup', 'schedule_meeting'],
                    'type': 'internal',
                    'url': 'agent://calendar-agent',
                    'formation': 'my-formation',
                    'preference_score': 0.0,
                    'status': 'active'
                }
            }
        """
        available_agents = {}

        for agent_id, agent in self.overlord.agents.items():
            # Don't include the requesting agent
            if agent_id == requesting_agent_id:
                continue

            # Check if agent participates in internal A2A communication
            # Default to True if not specified
            if not getattr(agent, "a2a_internal", True):
                continue

            # Get agent capabilities if available
            capabilities = []
            if hasattr(agent, "get_capabilities"):
                capabilities = agent.get_capabilities()
            elif hasattr(agent, "capabilities"):
                capabilities = agent.capabilities
            elif hasattr(agent, "specialties"):
                # Use specialties as capabilities
                capabilities = agent.specialties if agent.specialties else []

            # Apply capability filter if specified
            if capability_filter:
                if not capabilities or not any(cap in capabilities for cap in capability_filter):
                    continue

            # Add agent to available list with normalized format
            available_agents[agent_id] = {
                "agent_id": agent_id,
                "description": self.overlord.agent_descriptions.get(agent_id, ""),
                "capabilities": capabilities,
                "type": "internal",
                "url": f"agent://{agent_id}",  # Agent URL for internal agents
                "transport": "agent",  # Transport hint for internal agents
                "formation": self.overlord.formation_id,
                "preference_score": 0.0,  # Internal agents are always preferred
                "status": "active",  # If it's in the registry, it's active
            }

        return available_agents

    async def _start_a2a_server(self) -> None:
        """
        Start the A2A formation server.

        This method starts the FastAPI-based HTTP server that hosts A2A services,
        allowing external formations to discover and communicate with this formation's
        agents. The server runs asynchronously and provides REST endpoints for:
        - Agent discovery and capability queries
        - Message routing to local agents
        - Health checks and status monitoring

        The server only starts if it was enabled in the configuration.
        If startup fails, an error is logged but the overlord continues operating
        without A2A server capabilities.

        Side Effects:
            - Starts HTTP server on configured host/port
            - Emits observability events for server startup success/failure
            - Makes local agents discoverable to external formations
        """
        try:

            # Only start if server is enabled in config
            if not self.server_enabled:
                return

            # Create the A2A server if it doesn't exist
            if not self.overlord.a2a_server:
                from ...services.a2a.server import A2AServer

                self.overlord.a2a_server = A2AServer(
                    overlord=self.overlord,
                    port=self.server_port,
                    host=self.server_host,
                    auth_mode=self.config.auth_mode if self.config.auth_mode else "none",
                    shared_key=self.config.shared_key,
                    formation_name=self.overlord.formation_id,
                )

            # Start the server
            await self.overlord.a2a_server.start()

            # Emit success event
            auth_mode = self.config.auth_mode if self.config.auth_mode else "none"
            pass  # REMOVED: init-phase observe() call

            # Print clean formatted line
            details = f"{self.server_host}:{self.server_port}, auth={auth_mode}"
            print(InitEventFormatter.format_ok("A2A server", details))

        except Exception as e:
            # Emit error event with full exception details
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to start A2A server: {str(e)}",
                data={
                    "host": self.server_host,
                    "port": self.server_port,
                    "formation": self.overlord.formation_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )

    def _get_agent_url(self, agent_id: str) -> str:
        """
        Helper method to construct the agent URL consistently.

        Args:
            agent_id: The ID of the agent

        Returns:
            The full URL for the agent
        """
        # Use configured host or fallback to localhost
        host = self.server_host if self.server_host and self.server_host != "0.0.0.0" else "localhost"

        port = (
            self.overlord.a2a_server.port
            if hasattr(self.overlord, "a2a_server") and self.overlord.a2a_server
            else self.server_port
        )
        return f"http://{host}:{port}/agents/{agent_id}/message"

    def _determine_transport_from_url(self, url: str) -> str:
        """
        Determine the transport type from the URL scheme.

        Args:
            url: The agent URL

        Returns:
            The transport type hint (agent, jsonrpc, rest, grpc)
        """
        if url.startswith("agent://"):
            return "agent"
        elif url.startswith("grpc://"):
            return "grpc"
        elif url.startswith("ws://") or url.startswith("wss://"):
            return "websocket"
        elif url.startswith("http://") or url.startswith("https://"):
            # For HTTP URLs, we default to jsonrpc as it's the most common
            # In a real implementation, this could be determined from agent metadata
            return "jsonrpc"
        else:
            return "unknown"

    async def process_pending_registrations(self) -> None:
        """
        Public method to process pending external agent registrations.

        This should be called after the registry client is initialized to register
        any agents that were created before the A2A system was ready.
        """
        await self._process_pending_agent_registrations()

    async def _process_pending_agent_registrations(self) -> None:
        """
        Process pending external agent registrations.

        This method handles registration of agents with external A2A registries that
        were created before the A2A system was fully initialized. During overlord
        startup, agents may be created before the registry clients are available,
        so their registration is deferred until this method is called.

        The method processes all agents in the pending_external_registrations set
        and registers them concurrently with the external registry. Failed
        registrations are logged but don't prevent other registrations from proceeding.

        Side Effects:
            - Registers pending agents with external registries
            - Clears the pending_external_registrations set
            - Emits observability events for registration completion
        """
        try:
            # Skip if external registry not enabled or no pending registrations
            if not self.external_registry_enabled:
                return

            # Skip if no registry client or no pending registrations
            if not self.overlord.inbound_registry_client:
                return

            if not self.overlord.pending_external_registrations:
                return

            # Apply timeout to registration operations
            async def _register_with_timeout(agent_id: str):
                try:
                    await asyncio.wait_for(
                        self._register_agent_with_external_registry(agent_id),
                        timeout=self.registration_timeout,
                    )
                except asyncio.TimeoutError:
                    # Log timeout but don't fail the entire batch
                    _ = f"Registration timeout for agent {agent_id}"

            # Collect registration tasks for concurrent execution
            registration_tasks = []

            for agent_id in self.overlord.pending_external_registrations:
                # Only register agents that still exist in the registry
                if agent_id in self.overlord.agents:
                    # Create async registration task for this agent
                    task = _register_with_timeout(agent_id)
                    registration_tasks.append(task)

            # Execute all registrations concurrently to minimize latency
            if registration_tasks:
                await asyncio.gather(*registration_tasks, return_exceptions=True)

                # Clear the pending registrations set now that processing is complete
                self.overlord.pending_external_registrations.clear()

                observability.observe(
                    event_type=observability.SystemEvents.A2A_AGENT_REGISTRATIONS_COMPLETED,
                    level=observability.EventLevel.INFO,
                    data={"registration_count": len(registration_tasks)},
                    description=f"Completed bulk A2A agent registrations for {len(registration_tasks)} agents",
                )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.A2A_AGENT_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to register agents with external registry",
            )

    async def _register_agent_with_external_registry(self, agent_id: str) -> None:
        """
        Register a single agent with external registry.

        This method registers a local agent with an external A2A registry, making it
        discoverable and accessible to other formations. The registration includes
        the agent's metadata such as description, capabilities, and current status.

        The method handles registration failures gracefully, logging errors without
        stopping the registration process for other agents.

        Args:
            agent_id: ID of the agent to register. Must exist in self.overlord.agents.

        Side Effects:
            - Sends registration request to external registry
            - Emits observability events for registration success/failure
            - Makes the agent discoverable to external formations
        """
        try:
            # Skip if external registry not enabled
            if not self.external_registry_enabled:
                return

            # Skip if no registry client available or agent doesn't exist
            if not self.overlord.inbound_registry_client:
                return

            if agent_id not in self.overlord.agents:
                return

            # Get the agent instance for metadata extraction
            agent = self.overlord.agents[agent_id]

            # Get agent capabilities using same logic as internal discovery
            capabilities_list = []
            if hasattr(agent, "get_capabilities"):
                capabilities_list = agent.get_capabilities()
            elif hasattr(agent, "capabilities"):
                capabilities_list = agent.capabilities
            elif hasattr(agent, "specialties"):
                # Use specialties as capabilities
                capabilities_list = agent.specialties if agent.specialties else []

            # Create agent card for registration using MUXI format
            # For external A2A, capabilities must be in metadata since the SDK
            # will convert them appropriately
            agent_card = AgentCard(
                name=agent_id,
                description=self.overlord.agent_descriptions.get(agent_id, "No description"),
                version="1.0.0",
                url=self._get_agent_url(agent_id),
                muxi_agent_id=agent_id,
                muxi_formation=self.overlord.formation_id,
                # Don't set capabilities dict here - let SDK adapter handle it
                metadata={
                    "formation_id": self.overlord.formation_id,
                    "capabilities": capabilities_list,
                    "specialties": getattr(agent, "specialties", []),
                    "status": "active",
                },
            )

            # Send registration request to external registry
            await self.overlord.inbound_registry_client.register_agent(agent_card)

            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id},
                description=f"Registered A2A agent '{agent_id}' with external registry",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.A2A_AGENT_REGISTRATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to register agent '{agent_id}' with external registry",
            )

    async def deregister_agent_from_external_registry(self, agent_id: str) -> None:
        """
        Deregister an agent from external registry.

        Args:
            agent_id: ID of the agent to deregister
        """
        try:
            # Skip if external registry not enabled
            if not self.external_registry_enabled:
                return

            if not self.overlord.inbound_registry_client:
                return

            # Use helper method to get consistent agent URL
            agent_url = self._get_agent_url(agent_id)

            await self.overlord.inbound_registry_client.deregister_agent(agent_url)

            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_DEREGISTERED,
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id},
                description=f"Deregistered A2A agent '{agent_id}' from external registry",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DEREGISTRATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description=f"Failed to deregister agent '{agent_id}' from external registry",
            )

    def get_configuration(self) -> A2AServiceSchema:
        """
        Get the current A2A service configuration.

        Returns:
            The current A2AServiceSchema instance
        """
        return self.config

    def update_configuration(self, config: A2AServiceSchema) -> None:
        """
        Update the A2A service configuration.

        Args:
            config: New A2A service configuration

        Raises:
            ValueError: If configuration validation fails
        """
        # Validate new configuration
        config.validate()

        # Update configuration
        self.config = config

        # Apply new configuration
        self._apply_configuration()

    async def discover_external_agents(
        self, capability_filter: Optional[List[str]] = None, registry_url: Optional[str] = None
    ) -> Dict[str, List[AgentCard]]:
        """
        Discover agents from external registries using SDK.

        This method queries external registries to find agents with specific capabilities
        that can be used for cross-formation collaboration.

        Args:
            capability_filter: Optional list of required capabilities
            registry_url: Specific registry to query, or None for all registries

        Returns:
            Dictionary mapping registry URLs to lists of discovered AgentCards
        """
        try:
            # Skip if external registry not enabled
            if not self.external_registry_enabled:
                return {}

            # Skip if no registry client available
            if not self.overlord.inbound_registry_client:
                return {}

            # Use registry client to discover agents
            result = await self.overlord.inbound_registry_client.discover_agents(
                capability_filter=capability_filter, registry_url=registry_url
            )

            # Convert result to expected format
            if isinstance(result, list):
                # Single registry result
                return {registry_url or self.registry_url: result}
            else:
                # Multiple registry results
                return result

        except Exception as e:
            # Log error but don't fail
            _ = f"Failed to discover external agents: {e}"
            return {}

    async def get_all_available_agents(
        self,
        requesting_agent_id: str,
        capability_filter: Optional[List[str]] = None,
        include_external: bool = True,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all available agents (internal and external) in a unified format.

        This method provides a unified view of all agents that can be used for
        task delegation, including both internal formation agents and external
        agents discovered through registries.

        Args:
            requesting_agent_id: ID of the agent making the discovery request
            capability_filter: Optional list of required capabilities to filter by
            include_external: Whether to include external agents (default: True)

        Returns:
            Dict mapping agent_id to normalized agent information:
            - agent_id: Unique identifier for the agent
            - description: Agent's description
            - capabilities: List of agent capabilities
            - type: "internal" or "external"
            - url: Agent URL (agent:// for internal, http:// for external)
            - transport: Transport hint (agent, jsonrpc, rest, grpc, etc.)
            - formation: Formation name
            - preference_score: Lower = preferred (internal: 0.0, external: 1.0)
        """
        all_agents = {}

        # Step 1: Get internal agents
        internal_agents = self.get_available_agents_for_a2a(requesting_agent_id, capability_filter)

        # Normalize internal agents
        for agent_id, agent_info in internal_agents.items():
            all_agents[agent_id] = {
                "agent_id": agent_id,
                "description": agent_info.get("description", ""),
                "capabilities": agent_info.get("capabilities", []),
                "type": "internal",
                "url": agent_info.get(
                    "url"
                ),  # Already has agent:// URL from get_available_agents_for_a2a
                "transport": agent_info.get("transport", "agent"),  # Get transport hint from source
                "formation": self.overlord.formation_id,
                "preference_score": 0.0,  # Internal agents are always preferred
            }

        # Step 2: Get external agents if enabled
        if include_external and self.external_registry_enabled:
            try:
                # Don't pass capability filter to registry - filter locally instead
                # because registry might not check metadata for capabilities
                external_discovered = await self.discover_external_agents(
                    capability_filter=None  # Get all agents, filter locally
                )

                # Process external agents from all registries
                for registry_url, agent_cards in external_discovered.items():

                    from urllib.parse import urlparse

                    for agent_card in agent_cards:
                        # Extract hostname from the agent's URL, not the registry URL
                        # This gives us the actual formation's hostname
                        agent_url = getattr(agent_card, "url", "")
                        if agent_url:
                            parsed_agent_url = urlparse(agent_url)
                            # Include port if it's not the default port
                            if parsed_agent_url.port and parsed_agent_url.port not in [80, 443]:
                                hostname = f"{parsed_agent_url.hostname}:{parsed_agent_url.port}"
                            else:
                                hostname = parsed_agent_url.hostname or "unknown"
                        else:
                            # Fallback to registry hostname if agent URL not available
                            parsed_reg_url = urlparse(registry_url)
                            hostname = parsed_reg_url.hostname or "unknown"

                        # Create unique ID for external agent using hostname
                        # This prevents naming conflicts when using multiple A2A servers
                        external_id = f"{agent_card.name}@{hostname}"

                        # Skip if we already have this agent internally
                        if agent_card.name in all_agents:
                            continue

                        # Extract capabilities from agent card
                        capabilities = []

                        # Check metadata first (where we store capabilities during registration)
                        if hasattr(agent_card, "metadata") and agent_card.metadata:
                            metadata_caps = agent_card.metadata.get("capabilities", [])
                            if metadata_caps:
                                capabilities = metadata_caps

                        # If no capabilities in metadata, check the main capabilities field
                        if (
                            not capabilities
                            and hasattr(agent_card, "capabilities")
                            and agent_card.capabilities
                        ):
                            # SDK AgentCard has capabilities as dict
                            if isinstance(agent_card.capabilities, dict):
                                capabilities = list(agent_card.capabilities.keys())
                            else:
                                capabilities = agent_card.capabilities

                        # Apply capability filter if specified
                        if capability_filter:
                            if not any(cap in capabilities for cap in capability_filter):
                                continue

                        all_agents[external_id] = {
                            "agent_id": external_id,
                            "description": agent_card.description or "",
                            "capabilities": capabilities,
                            "type": "external",
                            "url": agent_card.url,
                            "transport": self._determine_transport_from_url(agent_card.url),
                            "formation": hostname,  # Use hostname for clarity
                            "preference_score": 1.0,  # External agents have higher score (lower preference)
                        }

            except Exception as e:
                # Log but don't fail if external discovery fails
                _ = f"Failed to include external agents: {e}"

        return all_agents

    async def get_relevant_agents_for_planning(
        self, requesting_agent_id: str, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get relevant agents for planning with optional smart filtering.

        Args:
            requesting_agent_id: ID of agent making the request
            task: Task description to plan for
            context: Optional task context

        Returns:
            Dictionary of relevant agents
        """

        # Try to initialize planning filter if not already done
        if self.planning_filter is None:
            self.initialize_planning_filter()

        # Get all available agents (internal + external)
        all_agents = await self.get_all_available_agents(requesting_agent_id)

        # Apply filtering if configured
        if self.planning_filter:
            # Add 'id' field to match what planning_filter expects
            agents_list = []
            for agent_id, agent_info in all_agents.items():
                agent_with_id = agent_info.copy()
                agent_with_id["id"] = agent_id  # Add 'id' field
                agents_list.append(agent_with_id)

            filtered_agents = await self.planning_filter.get_relevant_agents(
                task=task, all_agents=agents_list, context=context
            )

            # Convert back to dictionary format
            return {agent["agent_id"]: agent for agent in filtered_agents}

        # Return all agents if filtering not configured
        return all_agents

    async def route_to_agent(
        self,
        source_agent_id: str,
        target_agent_info: Dict[str, Any],
        message: Any,
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Unified routing method that handles both internal and external agents transparently.

        The agent doesn't need to know if the target is internal or external -
        this method uses the unified A2A messaging with appropriate transport.

        Args:
            source_agent_id: ID of the sending agent
            target_agent_info: Agent information dict with 'url' field
            message: Message to send
            message_type: Type of message (request/response)
            context: Optional message context

        Returns:
            Response from the target agent, or None if routing failed
        """

        # Use unified A2A messaging through overlord
        if hasattr(self.overlord, "send_a2a_message"):
            return await self.overlord.send_a2a_message(
                source_agent_id=source_agent_id,
                target_agent_info=target_agent_info,
                message=message,
                message_type=message_type,
                context=context,
            )
        else:
            # Fallback if unified messaging not available

            # Check if this is an external agent
            if target_agent_info.get("type") == "external":
                # Route to external agent
                return await self.route_to_external_agent(
                    source_agent_id=source_agent_id,
                    target_agent_url=target_agent_info.get("url"),
                    message=message,
                    message_type=message_type,
                    context=context,
                )
            else:
                # Route to internal agent
                target_agent_id = target_agent_info.get("agent_id")
                target_agent = self.overlord.agents.get(target_agent_id)

                if not target_agent:
                    return None

                # Use the agent's process_a2a_message method for internal routing
                if hasattr(target_agent, "process_a2a_message"):
                    from ...utils.id_generator import generate_nanoid

                    # Create A2A message format
                    a2a_message = {
                        "role": "user",
                        "messageId": f"msg_{generate_nanoid()}",
                        "parts": [
                            {
                                "type": "TextPart",
                                "text": message if isinstance(message, str) else str(message),
                            },
                            {"type": "DataPart", "data": context or {}},
                        ],
                    }

                    response = await target_agent.process_a2a_message(
                        source_agent_id=source_agent_id,
                        message=a2a_message,
                        message_type=message_type,
                    )

                    return response

                return None

    async def route_to_external_agent(
        self,
        source_agent_id: str,
        target_agent_url: str,
        message: Any,
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Route a message to an external agent via A2A protocol using SDK.

        This method sends messages to agents in other formations discovered
        through the external registry.

        Args:
            source_agent_id: ID of the sending agent
            target_agent_url: URL of the target external agent
            message: Message to send
            message_type: Type of message (request/response)
            context: Optional message context

        Returns:
            Response from the external agent, or None if routing failed
        """
        try:

            # Skip if external registry not enabled
            if not self.external_registry_enabled:
                return None

            import httpx
            from a2a.client import A2AClient
            from a2a.types import SendMessageRequest, MessageSendParams

            # Create httpx client and SDK client for target agent
            async with httpx.AsyncClient() as http_client:
                client = A2AClient(httpx_client=http_client, url=target_agent_url)

                # Convert message to SDK format
                sdk_message = ModelsAdapter.muxi_to_sdk_message(
                    message,
                    message_id=f"{source_agent_id}_{int(time.time() * 1000)}",
                    context=context,
                )

                # Create the params for the JSON-RPC request
                params = MessageSendParams(
                    message=sdk_message, metadata={"source_agent_id": source_agent_id}
                )

                # Create the JSON-RPC request
                request = SendMessageRequest(id=f"req_{int(time.time() * 1000)}", params=params)

                response = await client.send_message(request)

                # Handle the response - it's a RootModel that contains either success or error
                if response:
                    # The response.root contains the actual response
                    response_data = response.root if hasattr(response, "root") else response

                    # Check if it's a success response
                    if hasattr(response_data, "result"):
                        result_data = response_data.result

                        # Check if result is a Message
                        if hasattr(result_data, "message_id"):
                            # It's a Message
                            muxi_message = ModelsAdapter.sdk_to_muxi_message(result_data)
                            return muxi_message
                        else:
                            # It might be a Task or other type
                            # For now, return a simple response
                            return {"success": True, "type": "task", "data": str(result_data)}
                    elif hasattr(response_data, "error"):
                        # It's an error response
                        return None

                return None

        except Exception as e:
            # Log error properly using observability
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to route message to external agent: {str(e)}",
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_url": target_agent_url,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            return None
