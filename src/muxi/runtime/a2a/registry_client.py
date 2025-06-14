"""
A2A External Registry Client

This module provides client functionality for communicating with external
A2A registries. It handles agent registration, discovery, and health
monitoring across multiple external registries.
"""

import asyncio

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import httpx
import time

from .. import observability
from .models import AgentCard


@dataclass
class RegistryResponse:
    """Response from an external registry operation"""
    success: bool
    status_code: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    registry_url: Optional[str] = None


@dataclass
class RegistryConfig:
    """Configuration for external registry client"""
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    health_check_interval: int = 60  # seconds
    user_agent: str = "MUXI-Framework/1.0"


class A2ARegistryClient:
    """
    Client for communicating with external A2A registries.

    Handles registration, discovery, and health monitoring of agents
    across multiple external registries as configured in formation YAML.
    """

    def __init__(
        self,
        registries: Optional[List[str]] = None,
        config: Optional[RegistryConfig] = None
    ):
        """
        Initialize the external registry client.

        Args:
            registries: List of registry URLs from formation config
            config: Client configuration options
        """
        try:
            self.registries = registries or []
            self.config = config or RegistryConfig()

            # HTTP client with timeout configuration
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                headers={"User-Agent": self.config.user_agent}
            )

            # Track registry health
            self.registry_status: Dict[str, Dict[str, Any]] = {}

            # Track registered agents per registry
            self.registered_agents: Dict[str, List[str]] = {}

            # Initialize registry status tracking
            for registry_url in self.registries:
                self.registry_status[registry_url] = {"last_check": None, "healthy": None}
                self.registered_agents[registry_url] = []

            # Emit initialization event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                level=observability.EventLevel.INFO,
                description=f"A2A Registry Client initialized with {len(self.registries)} registries",  # noqa: E501
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "timeout_seconds": self.config.timeout_seconds,
                    "max_retries": self.config.max_retries
                }
            )

            # Initialization event already emitted above

        except Exception as e:
            # Emit error event for initialization failure
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to initialize A2A Registry Client: {str(e)}",
                data={
                    "registries_count": len(registries) if registries else 0,
                    "error": str(e)
                }
            )
            raise

    async def close(self):
        """Close the HTTP client"""
        try:
            await self.http_client.aclose()

            # Emit client close event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                level=observability.EventLevel.INFO,
                description="A2A Registry Client closed",
                data={
                    "registries_count": len(self.registries),
                    "total_registered_agents": sum(
                        len(agents) for agents in self.registered_agents.values()
                    ),
                }
            )

        except Exception as e:
            # Emit error event for close failure
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to close A2A Registry Client: {str(e)}",
                data={"error": str(e)}
            )
            raise

    def add_registry(self, registry_url: str) -> None:
        """Add a new registry URL to the client"""
        try:
            if registry_url not in self.registries:
                self.registries.append(registry_url)
                self.registry_status[registry_url] = {"last_check": None, "healthy": None}
                self.registered_agents[registry_url] = []

                # Emit registry addition event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                    level=observability.EventLevel.INFO,
                    description=f"Added registry: {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries)
                    }
                )

                # Registry addition event already emitted above
            else:
                # Emit warning for duplicate registry
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                    level=observability.EventLevel.WARNING,
                    description=f"Registry already exists: {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries)
                    }
                )

        except Exception as e:
            # Emit error event for registry addition failure
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to add registry {registry_url}: {str(e)}",
                data={
                    "registry_url": registry_url,
                    "error": str(e)
                }
            )
            raise

    def remove_registry(self, registry_url: str) -> None:
        """Remove a registry URL from the client"""
        try:
            if registry_url in self.registries:
                agents_count = len(self.registered_agents.get(registry_url, []))

                self.registries.remove(registry_url)
                self.registry_status.pop(registry_url, None)
                self.registered_agents.pop(registry_url, None)

                # Emit registry removal event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                    level=observability.EventLevel.INFO,
                    description=f"Removed registry: {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "agents_removed": agents_count,
                        "remaining_registries": len(self.registries)
                    }
                )

                #  Registry removal event already emitted above
            else:
                # Emit warning for non-existent registry
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                    level=observability.EventLevel.WARNING,
                    description=f"Registry not found for removal: {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries)
                    }
                )

        except Exception as e:
            # Emit error event for registry removal failure
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to remove registry {registry_url}: {str(e)}",
                data={
                    "registry_url": registry_url,
                    "error": str(e)
                }
            )
            raise

    async def health_check(self, registry_url: str) -> bool:
        """
        Check if a registry is healthy and responding.

        Args:
            registry_url: URL of the registry to check

        Returns:
            True if registry is healthy, False otherwise
        """
        try:
            # Emit health check start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.DEBUG,
                description=f"Starting health check for registry: {registry_url}",
                data={"registry_url": registry_url}
            )

            response = await self.http_client.get(f"{registry_url}/health")
            is_healthy = response.status_code == 200

            # Update status tracking
            self.registry_status[registry_url] = {
                "last_check": time.time(),
                "healthy": is_healthy,
                "status_code": response.status_code
            }

            # Emit health check result event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=(
                    observability.EventLevel.INFO
                    if is_healthy
                    else observability.EventLevel.WARNING
                ),
                description=f"Registry health check {'passed' if is_healthy else 'failed'}: {registry_url}",  # noqa: E501
                data={
                    "registry_url": registry_url,
                    "healthy": is_healthy,
                    "status_code": response.status_code,
                    "response_time_ms": getattr(response, 'elapsed', None)
                }
            )

            return is_healthy

        except Exception as e:
            # Emit health check error event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.ERROR,
                description=f"Health check failed for registry: {registry_url}",
                data={
                    "registry_url": registry_url,
                    "error": str(e)
                }
            )

            #  Health check error event already emitted above
            self.registry_status[registry_url] = {
                "last_check": time.time(),
                "healthy": False,
                "error": str(e)
            }
            return False

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all configured registries.

        Returns:
            Dictionary mapping registry URLs to health status
        """
        try:
            if not self.registries:
                # Emit no registries event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                    level=observability.EventLevel.WARNING,
                    description="No registries configured for health check",
                    data={"registries_count": 0}
                )
                return {}

            # Emit health check all start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.INFO,
                description=f"Starting health check for all {len(self.registries)} registries",
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries
                }
            )

            tasks = [self.health_check(registry) for registry in self.registries]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            health_status = {
                registry: (result if isinstance(result, bool) else False)
                for registry, result in zip(self.registries, results)
            }

            healthy_count = sum(1 for status in health_status.values() if status)

            # Emit health check all result event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.INFO,
                description="Health check completed for all registries",
                data={
                    "registries_count": len(self.registries),
                    "healthy_count": healthy_count,
                    "unhealthy_count": len(self.registries) - healthy_count,
                    "health_status": health_status
                }
            )

            return health_status

        except Exception as e:
            # Emit health check all error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to perform health check on all registries: {str(e)}",
                data={
                    "registries_count": len(self.registries),
                    "error": str(e)
                }
            )
            raise

    async def register_agent(
        self,
        agent_card: AgentCard,
        registry_url: Optional[str] = None
    ) -> Union[RegistryResponse, Dict[str, RegistryResponse]]:
        """
        Register an agent with external registry(ies).

        Args:
            agent_card: Agent card to register
            registry_url: Specific registry URL, or None to register with all

        Returns:
            RegistryResponse for single registry, or dict of responses for all registries
        """
        try:
            # Emit agent registration start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Starting agent registration for {agent_card.name}",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "target_registry": registry_url,
                    "register_all": registry_url is None
                }
            )

            if registry_url:
                return await self._register_single(agent_card, registry_url)
            else:
                return await self._register_all(agent_card)

        except Exception as e:
            # Emit agent registration error event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent registration failed for {agent_card.name}: {str(e)}",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "target_registry": registry_url,
                    "error": str(e)
                }
            )
            raise

    async def _register_single(self, agent_card: AgentCard, registry_url: str) -> RegistryResponse:
        """Register agent with a single registry"""
        try:
            response = await self.http_client.post(
                f"{registry_url}/register",
                json=agent_card.to_dict(),
                headers={"Content-Type": "application/json"}
            )

            if response.status_code in [200, 201]:  # Accept both OK and Created
                # Track successful registration
                if registry_url not in self.registered_agents:
                    self.registered_agents[registry_url] = []
                if agent_card.url not in self.registered_agents[registry_url]:
                    self.registered_agents[registry_url].append(agent_card.url)

                # Emit successful registration event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                    level=observability.EventLevel.INFO,
                    description=f"Agent {agent_card.name} registered successfully with {registry_url}",  # noqa: E501
                    data={
                        "agent_name": agent_card.name,
                        "agent_url": agent_card.url,
                        "registry_url": registry_url,
                        "status_code": response.status_code,
                        "total_registered": len(self.registered_agents[registry_url])
                    }
                )

                #  Registration success event already emitted above

                return RegistryResponse(
                    success=True,
                    status_code=response.status_code,
                    data=response.json() if response.content else None,
                    registry_url=registry_url
                )
            else:
                error_msg = f"Registration failed: {response.status_code}"

                # Emit registration failure event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description=f"Agent registration failed for {agent_card.name} on {registry_url}",  # noqa: E501
                    data={
                        "agent_name": agent_card.name,
                        "agent_url": agent_card.url,
                        "registry_url": registry_url,
                        "status_code": response.status_code,
                        "error": error_msg
                    }
                )

                #  Registration failure event already emitted above

                return RegistryResponse(
                    success=False,
                    status_code=response.status_code,
                    error=error_msg,
                    registry_url=registry_url
                )

        except Exception as e:
            error_msg = f"Registration error: {str(e)}"

            # Emit registration error event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent registration error for {agent_card.name} on {registry_url}",  # noqa: E501
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registry_url": registry_url,
                    "error": str(e)
                }
            )

            #  Registration error event already emitted above

            return RegistryResponse(
                success=False,
                error=error_msg,
                registry_url=registry_url
            )

    async def _register_all(self, agent_card: AgentCard) -> Dict[str, RegistryResponse]:
        """Register agent with all configured registries"""
        try:
            if not self.registries:
                # Emit no registries event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"No registries configured for agent {agent_card.name}",
                    data={
                        "agent_name": agent_card.name,
                        "agent_url": agent_card.url,
                        "registries_count": 0
                    }
                )
                return {}

            # Emit register all start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Registering agent {agent_card.name} with all {len(self.registries)} registries",  # noqa: E501
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "registries": self.registries
                }
            )

            tasks = [
                self._register_single(agent_card, registry)
                for registry in self.registries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            responses = {}
            successful_registrations = 0

            for registry, result in zip(self.registries, results):
                if isinstance(result, RegistryResponse):
                    responses[registry] = result
                    if result.success:
                        successful_registrations += 1
                else:
                    # Handle exceptions
                    responses[registry] = RegistryResponse(
                        success=False,
                        error=f"Exception: {str(result)}",
                        registry_url=registry
                    )

            # Emit register all result event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"Agent registration completed for {agent_card.name}",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "successful_registrations": successful_registrations,
                    "failed_registrations": len(self.registries) - successful_registrations
                }
            )

            return responses

        except Exception as e:
            # Emit register all error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to register agent {agent_card.name} with all registries: {str(e)}",  # noqa: E501
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "error": str(e)
                }
            )
            raise

    async def deregister_agent(self, agent_url: str) -> Dict[str, RegistryResponse]:
        """
        Deregister an agent from all registries where it's registered.

        Args:
            agent_url: URL of the agent to deregister

        Returns:
            Dictionary mapping registry URLs to deregistration responses
        """
        try:
            # Find registries where this agent is registered
            target_registries = [
                registry for registry, agents in self.registered_agents.items()
                if agent_url in agents
            ]

            if not target_registries:
                # Emit no registrations found event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"No registrations found for agent: {agent_url}",
                    data={
                        "agent_url": agent_url,
                        "total_registries": len(self.registries)
                    }
                )
                return {}

            # Emit deregistration start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Starting deregistration for agent: {agent_url}",
                data={
                    "agent_url": agent_url,
                    "target_registries": target_registries,
                    "registrations_count": len(target_registries)
                }
            )

            responses = {}
            successful_deregistrations = 0

            for registry_url in target_registries:
                try:
                    response = await self.http_client.delete(
                        f"{registry_url}/deregister",
                        params={"agent_url": agent_url}
                    )

                    if response.status_code in [200, 204, 404]:  # OK, No Content, or Not Found
                        # Remove from tracking
                        if agent_url in self.registered_agents[registry_url]:
                            self.registered_agents[registry_url].remove(agent_url)

                        # Emit successful deregistration event
                        observability.emit_event(
                            event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                            level=observability.EventLevel.INFO,
                            description=f"Agent deregistered successfully from {registry_url}",
                            data={
                                "agent_url": agent_url,
                                "registry_url": registry_url,
                                "status_code": response.status_code
                            }
                        )

                        responses[registry_url] = RegistryResponse(
                            success=True,
                            status_code=response.status_code,
                            registry_url=registry_url
                        )
                        successful_deregistrations += 1

                        #  Deregistration success event already emitted above
                    else:
                        error_msg = f"Deregistration failed: {response.status_code}"

                        # Emit deregistration failure event
                        observability.emit_event(
                            event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                            level=observability.EventLevel.ERROR,
                            description=f"Agent deregistration failed from {registry_url}",
                            data={
                                "agent_url": agent_url,
                                "registry_url": registry_url,
                                "status_code": response.status_code,
                                "error": error_msg
                            }
                        )

                        responses[registry_url] = RegistryResponse(
                            success=False,
                            status_code=response.status_code,
                            error=error_msg,
                            registry_url=registry_url
                        )

                        #  Deregistration failure event already emitted above

                except Exception as e:
                    error_msg = f"Deregistration error: {str(e)}"

                    # Emit deregistration error event
                    observability.emit_event(
                        event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                        level=observability.EventLevel.ERROR,
                        description=f"Agent deregistration error from {registry_url}",
                        data={
                            "agent_url": agent_url,
                            "registry_url": registry_url,
                            "error": str(e)
                        }
                    )

                    responses[registry_url] = RegistryResponse(
                        success=False,
                        error=error_msg,
                        registry_url=registry_url
                    )

                    #  Deregistration error event already emitted above

            # Emit deregistration summary event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"Agent deregistration completed for {agent_url}",
                data={
                    "agent_url": agent_url,
                    "target_registries_count": len(target_registries),
                    "successful_deregistrations": successful_deregistrations,
                    "failed_deregistrations": len(target_registries) - successful_deregistrations
                }
            )

            return responses

        except Exception as e:
            # Emit deregistration error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to deregister agent {agent_url}: {str(e)}",
                data={
                    "agent_url": agent_url,
                    "error": str(e)
                }
            )
            raise

    async def discover_agents(
        self,
        capability_filter: Optional[List[str]] = None,
        registry_url: Optional[str] = None
    ) -> Union[List[AgentCard], Dict[str, List[AgentCard]]]:
        """
        Discover agents from external registry(ies).

        Args:
            capability_filter: Optional list of required capabilities
            registry_url: Specific registry URL, or None to discover from all

        Returns:
            List of AgentCards for single registry, or dict for all registries
        """
        try:
            # Emit discovery start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                description="Starting agent discovery",
                data={
                    "capability_filter": capability_filter,
                    "target_registry": registry_url,
                    "discover_all": registry_url is None
                }
            )

            if registry_url:
                return await self._discover_single(registry_url, capability_filter)
            else:
                return await self._discover_all(capability_filter)

        except Exception as e:
            # Emit discovery error event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent discovery failed: {str(e)}",
                data={
                    "capability_filter": capability_filter,
                    "target_registry": registry_url,
                    "error": str(e)
                }
            )
            raise

    async def _discover_single(
        self,
        registry_url: str,
        capability_filter: Optional[List[str]] = None
    ) -> List[AgentCard]:
        """Discover agents from a single registry"""
        try:
            params = {}
            if capability_filter:
                params["capabilities"] = ",".join(capability_filter)

            response = await self.http_client.get(
                f"{registry_url}/discover",
                params=params
            )

            if response.status_code == 200:
                data = response.json()
                agents = data.get("agents", [])

                # Convert to AgentCard objects
                agent_cards = []
                for agent_data in agents:
                    try:
                        agent_card = AgentCard.from_dict(agent_data)
                        agent_cards.append(agent_card)

                        # Emit successful discovery event
                        observability.emit_event(
                            event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                            level=observability.EventLevel.INFO,
                            description=f"Agent discovery completed from {registry_url}",
                            data={
                                "registry_url": registry_url,
                                "agents_discovered": len(agent_cards),
                                "capability_filter": capability_filter,
                                "status_code": response.status_code
                            }
                        )
                    except Exception as e:
                        #  Agent card parsing error - add observability event
                        _ = e  # remove this after implementing observability

                #  Discovery success event already emitted above
                return agent_cards
            else:
                error_msg = f"Discovery failed: {response.status_code}"

                # Emit discovery failure event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                    level=observability.EventLevel.ERROR,
                    description=f"Agent discovery failed from {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "status_code": response.status_code,
                        "capability_filter": capability_filter,
                        "error": error_msg
                    }
                )

                #  Discovery failure event already emitted above
                return []

        except Exception as e:
            # Emit discovery error event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent discovery error from {registry_url}",
                data={
                    "registry_url": registry_url,
                    "capability_filter": capability_filter,
                    "error": str(e)
                }
            )

            #  Discovery error event already emitted above
            return []

    async def _discover_all(
        self, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, List[AgentCard]]:
        """Discover agents from all configured registries"""
        try:
            if not self.registries:
                # Emit no registries event
                observability.emit_event(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="No registries configured for discovery",
                    data={
                        "registries_count": 0,
                        "capability_filter": capability_filter
                    }
                )
                return {}

            # Emit discover all start event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Discovering agents from all {len(self.registries)} registries",
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "capability_filter": capability_filter
                }
            )

            tasks = [
                self._discover_single(registry, capability_filter)
                for registry in self.registries
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            discoveries = {}
            total_agents = 0

            for registry, result in zip(self.registries, results):
                if isinstance(result, list):
                    discoveries[registry] = result
                    total_agents += len(result)
                else:
                    # Handle exceptions
                    discoveries[registry] = []
                    #  Discovery exception event already emitted above

            # Emit discover all result event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                description="Agent discovery completed from all registries",
                data={
                    "registries_count": len(self.registries),
                    "total_agents_discovered": total_agents,
                    "capability_filter": capability_filter,
                    "discoveries_per_registry": {
                        registry: len(agents) for registry, agents in discoveries.items()
                    }
                }
            )

            return discoveries

        except Exception as e:
            # Emit discover all error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to discover agents from all registries: {str(e)}",
                data={
                    "registries_count": len(self.registries),
                    "capability_filter": capability_filter,
                    "error": str(e)
                }
            )
            raise

    def get_registry_status(self) -> Dict[str, Dict[str, Any]]:
        """Get the current status of all registries"""
        try:
            # Emit status request event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.DEBUG,
                description="Registry status requested",
                data={
                    "registries_count": len(self.registry_status),
                    "registries": list(self.registry_status.keys())
                }
            )

            return self.registry_status.copy()

        except Exception as e:
            # Emit status request error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registry status: {str(e)}",
                data={"error": str(e)}
            )
            raise

    def get_registered_agents(self) -> Dict[str, List[str]]:
        """Get the list of registered agents per registry"""
        try:
            # Emit registered agents request event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="Registered agents list requested",
                data={
                    "registries_count": len(self.registered_agents),
                    "total_agents": sum(len(agents) for agents in self.registered_agents.values())
                }
            )

            return self.registered_agents.copy()

        except Exception as e:
            # Emit registered agents request error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registered agents: {str(e)}",
                data={"error": str(e)}
            )
            raise

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about the registry client"""
        try:
            healthy_registries = sum(
                1 for status in self.registry_status.values()
                if status.get("healthy", False)
            )

            stats = {
                "total_registries": len(self.registries),
                "healthy_registries": healthy_registries,
                "unhealthy_registries": len(self.registries) - healthy_registries,
                "total_registered_agents": sum(
                    len(agents) for agents in self.registered_agents.values()),
                "registrations_per_registry": {
                    registry: len(agents) for registry, agents in self.registered_agents.items()
                },
                "registry_health": {
                    registry: status.get("healthy", False)
                    for registry, status in self.registry_status.items()
                }
            }

            # Emit stats request event
            observability.emit_event(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.DEBUG,
                description="Registry client stats requested",
                data=stats
            )

            return stats

        except Exception as e:
            # Emit stats request error event
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registry client stats: {str(e)}",
                data={"error": str(e)}
            )
            raise
