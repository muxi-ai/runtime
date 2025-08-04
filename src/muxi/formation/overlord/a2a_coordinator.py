"""
A2A (Agent-to-Agent) coordination for the Overlord.

This module handles all A2A communication coordination, including agent discovery,
external registry management, and A2A server operations that were previously
embedded in the main Overlord class.
"""

import asyncio
from typing import Dict, List, Optional, Any

from ...datatypes.schema import A2AServiceSchema
from ...services.a2a.models import AgentCard


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
            Dict mapping agent_id to agent information including:
            - description: Agent's description
            - capabilities: Agent's available capabilities (if any)
            - status: 'active' (always active if in registry)

        Example:
            >>> # Agent A discovers other agents
            >>> available = overlord.get_available_agents_for_a2a('weather-agent')
            >>> print(available)
            {
                'calendar-agent': {
                    'description': 'Manages calendar events',
                    'capabilities': ['calendar_lookup', 'schedule_meeting'],
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

            # Apply capability filter if specified
            if capability_filter:
                if not capabilities or not any(cap in capabilities for cap in capability_filter):
                    continue

            # Add agent to available list
            available_agents[agent_id] = {
                "description": self.overlord.agent_descriptions.get(agent_id, ""),
                "capabilities": capabilities,
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

            if self.overlord.a2a_server:
                await self.overlord.a2a_server.start()

                #  Info - TODO: add observability
                # SystemEvents.A2A_SERVER_STARTED

        except Exception as e:
            #  Error - TODO: add observability
            # SystemEvents.A2A_SERVER_START_FAILED
            _ = e  # remove this after implementing observability

    def _get_agent_url(self, agent_id: str) -> str:
        """
        Helper method to construct the agent URL consistently.
        
        Args:
            agent_id: The ID of the agent
            
        Returns:
            The full URL for the agent
        """
        port = self.overlord.a2a_server.port if hasattr(self.overlord, 'a2a_server') and self.overlord.a2a_server else 8181
        return f"http://localhost:{port}/agents/{agent_id}"
    
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
            if (
                not self.overlord.inbound_registry_client
                or not self.overlord.pending_external_registrations
            ):
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

                #  Info - TODO: add observability
                # SystemEvents.A2A_AGENT_REGISTRATIONS_COMPLETED

        except Exception as e:
            #  Error - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTRATION_FAILED
            _ = e  # remove this after implementing observability

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
            if not self.overlord.inbound_registry_client or agent_id not in self.overlord.agents:
                return

            # Get the agent instance for metadata extraction
            agent = self.overlord.agents[agent_id]

            # Create agent card for registration
            agent_card = AgentCard(
                name=agent_id,
                description=self.overlord.agent_descriptions.get(agent_id, "No description"),
                version="1.0.0",
                url=self._get_agent_url(agent_id),
                muxi_agent_id=agent_id,
                muxi_formation=self.overlord.formation_id,
                metadata={
                    "formation_id": self.overlord.formation_id,
                    "capabilities": getattr(agent, "capabilities", []),
                    "status": "active",
                },
            )

            # Send registration request to external registry
            await self.overlord.inbound_registry_client.register_agent(agent_card)

            #  Info - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTERED

        except Exception as e:
            #  Warning - TODO: add observability
            # SystemEvents.A2A_AGENT_REGISTRATION_FAILED
            _ = e  # remove this after implementing observability

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

            #  Info - TODO: add observability
            # SystemEvents.A2A_AGENT_DEREGISTERED

        except Exception as e:
            #  Warning - TODO: add observability
            # SystemEvents.A2A_AGENT_DEREGISTRATION_FAILED
            _ = e  # remove this after implementing observability

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
