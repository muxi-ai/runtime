"""
A2A Local Discovery Service

This module provides local discovery capabilities for A2A agents within a MUXI formation.
It enables automatic registration, discovery, and health monitoring of agents.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import httpx


from .. import observability
from .models import AgentCard
from .card_generator import AgentCardGenerator
from .cache_manager import A2ACacheManager


@dataclass
class AgentRegistration:
    """Represents a registered agent in the discovery service"""

    agent_id: str
    agent_card: AgentCard
    endpoint: str
    registered_at: float
    last_seen: float
    status: str = "active"  # active, inactive, unreachable
    health_score: float = 1.0  # 0.0 to 1.0
    response_time_ms: Optional[float] = None


@dataclass
class DiscoveryConfig:
    """Configuration for the discovery service"""

    health_check_interval: int = 30  # seconds
    agent_timeout: int = 120  # seconds before marking agent as inactive
    registry_file: Optional[str] = None  # Path to persist registry
    discovery_port_range: tuple = (8100, 8200)  # Port range for discovery
    enable_persistence: bool = True
    enable_auto_cleanup: bool = True


class LocalDiscoveryService:
    """
    Local discovery service for A2A agents.

    Provides registration, discovery, and health monitoring capabilities
    for agents within a formation.
    """

    def __init__(self, config: Optional[DiscoveryConfig] = None):
        self.config = config or DiscoveryConfig()
        self.agents: Dict[str, AgentRegistration] = {}
        self.formation_name = "default"
        self.discovery_port = 8080
        self.is_running = False
        self.health_check_task: Optional[asyncio.Task] = None
        self.cache_manager = A2ACacheManager()
        self.card_generator = AgentCardGenerator(self.cache_manager)

        # HTTP client for health checks
        self.http_client = httpx.AsyncClient(timeout=5.0)

        # Initialize observability
        pass  # REMOVED: init-phase observe() call

        # Load persisted registry if enabled
        if self.config.enable_persistence and self.config.registry_file:
            self._load_registry()

    async def start(self, formation_name: str = "default", port: int = 8080) -> Dict[str, Any]:
        """
        Start the discovery service.

        Args:
            formation_name: Name of the formation this service manages
            port: Port to run the discovery service on

        Returns:
            Service startup information
        """
        try:
            self.formation_name = formation_name
            self.discovery_port = port
            self.is_running = True

            #  A2A_MESSAGE_SENT
            #     f"Starting A2A Discovery Service for formation '{formation_name}' on port {port}"
            # )

            # Track service start
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation_name": formation_name,
                    "port": port,
                    "agents_count": len(self.agents),
                },
                description="A2A Discovery Service started",
            )

            # Start health check task
            if self.config.health_check_interval > 0:
                self.health_check_task = asyncio.create_task(self._health_check_loop())

            # Auto-cleanup task
            if self.config.enable_auto_cleanup:
                asyncio.create_task(self._cleanup_loop())

            result = {
                "status": "started",
                "formation": formation_name,
                "port": port,
                "agents_count": len(self.agents),
                "health_check_enabled": self.health_check_task is not None,
            }

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                data=result,
                description="A2A Discovery Service startup completed",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"formation_name": formation_name, "port": port, "error": str(e)},
                description="Failed to start A2A Discovery Service",
            )
            raise

    async def stop(self):
        """Stop the discovery service."""
        try:
            #  A2A_MESSAGE_SENT

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STOPPED,
                level=observability.EventLevel.INFO,
                data={
                    "formation_name": self.formation_name,
                    "agents_count": len(self.agents),
                },
                description="A2A Discovery Service stopping",
            )

            self.is_running = False

            # Stop health check task
            if self.health_check_task:
                self.health_check_task.cancel()
                try:
                    await self.health_check_task
                except asyncio.CancelledError:
                    pass

            # Close HTTP client
            await self.http_client.aclose()

            # Persist registry if enabled
            if self.config.enable_persistence:
                self._save_registry()

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STOPPED,
                level=observability.EventLevel.INFO,
                data={"formation_name": self.formation_name},
                description="A2A Discovery Service stopped successfully",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "formation_name": self.formation_name,
                    "error": str(e),
                },
                description="Failed to stop A2A Discovery Service",
            )
            raise

    async def register_agent(
        self, agent_id: str, endpoint: str, agent_card: Optional[AgentCard] = None
    ) -> Dict[str, Any]:
        """
        Register an agent with the discovery service.

        Args:
            agent_id: Unique identifier for the agent
            endpoint: HTTP endpoint where the agent can be reached
            agent_card: Optional agent card (will fetch from endpoint if not provided)

        Returns:
            Registration result
        """
        try:

            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": agent_id,
                    "endpoint": endpoint,
                    "formation_name": self.formation_name,
                },
                description="A2A agent registered successfully",
            )

            # Fetch agent card if not provided
            if agent_card is None:
                try:
                    agent_card = await self._fetch_agent_card(endpoint)
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.NETWORK_ERROR,
                        level=observability.EventLevel.ERROR,
                        data={"agent_id": agent_id, "endpoint": endpoint, "error": str(e)},
                        description="Failed to fetch agent card during registration",
                    )
                    raise ValueError(f"Could not retrieve agent card: {e}")

            # Create registration
            registration = AgentRegistration(
                agent_id=agent_id,
                agent_card=agent_card,
                endpoint=endpoint,
                registered_at=time.time(),
                last_seen=time.time(),
                status="active",
            )

            self.agents[agent_id] = registration

            # Persist if enabled
            if self.config.enable_persistence:
                self._save_registry()

            result = {
                "agent_id": agent_id,
                "status": "registered",
                "endpoint": endpoint,
                "capabilities": len(agent_card.capabilities),
                "registered_at": registration.registered_at,
            }

            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRATION_COMPLETED,
                level=observability.EventLevel.INFO,
                data=result,
                description="A2A agent registration completed",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.NETWORK_ERROR,
                level=observability.EventLevel.ERROR,
                data={"agent_id": agent_id, "endpoint": endpoint, "error": str(e)},
                description="Failed to register A2A agent",
            )
            raise

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the discovery service.

        Args:
            agent_id: Agent to unregister

        Returns:
            True if agent was unregistered, False if not found
        """
        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DEREGISTRATION_STARTED,
                level=observability.EventLevel.INFO,
                data={"agent_id": agent_id, "formation_name": self.formation_name},
                description="A2A agent unregistration started",
            )

            if agent_id in self.agents:
                del self.agents[agent_id]

                # Persist if enabled
                if self.config.enable_persistence:
                    self._save_registry()

                observability.observe(
                    event_type=observability.SystemEvents.A2A_DEREGISTERED,
                    level=observability.EventLevel.INFO,
                    data={"agent_id": agent_id, "result": "success"},
                    description="A2A agent unregistration completed",
                )

                return True

            observability.observe(
                event_type=observability.SystemEvents.A2A_DEREGISTERED,
                level=observability.EventLevel.WARNING,
                data={"agent_id": agent_id, "result": "not_found"},
                description="A2A agent unregistration completed - agent not found",
            )

            return False

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.NETWORK_ERROR,
                level=observability.EventLevel.ERROR,
                data={"agent_id": agent_id, "error": str(e)},
                description="Failed to unregister A2A agent",
            )
            raise

    def discover_agents(
        self,
        capability_filter: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Discover available agents.

        Args:
            capability_filter: Filter by required capabilities
            status_filter: Filter by agent status (default: ["active"])

        Returns:
            List of discovered agent information
        """
        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "capability_filter": capability_filter,
                    "status_filter": status_filter,
                    "formation_name": self.formation_name,
                },
                description="A2A agent discovery query started",
            )

            status_filter = status_filter or ["active"]

            discovered = []

            for agent_id, registration in self.agents.items():
                # Status filter
                if registration.status not in status_filter:
                    continue

                # Capability filter
                if capability_filter:
                    agent_capabilities = set(registration.agent_card.capabilities.keys())
                    required_capabilities = set(capability_filter)
                    if not required_capabilities.issubset(agent_capabilities):
                        continue

                discovered.append(
                    {
                        "agent_id": agent_id,
                        "name": registration.agent_card.name,
                        "description": registration.agent_card.description,
                        "endpoint": registration.endpoint,
                        "capabilities": list(registration.agent_card.capabilities.keys()),
                        "status": registration.status,
                        "health_score": registration.health_score,
                        "response_time_ms": registration.response_time_ms,
                        "last_seen": registration.last_seen,
                    }
                )

            # Sort by health score (best first)
            discovered.sort(key=lambda x: x["health_score"], reverse=True)

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "agents_found": len(discovered),
                    "capability_filter": capability_filter,
                    "status_filter": status_filter,
                },
                description="A2A agent discovery query completed",
            )

            return discovered

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.NETWORK_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "capability_filter": capability_filter,
                    "status_filter": status_filter,
                    "error": str(e),
                },
                description="Failed to discover A2A agents",
            )
            raise

    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific agent.

        Args:
            agent_id: Agent to get info for

        Returns:
            Agent information or None if not found
        """
        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": agent_id,
                    "formation_name": self.formation_name,
                },
                description="A2A agent info query started",
            )

            if agent_id not in self.agents:
                observability.observe(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={"agent_id": agent_id, "found": False},
                    description="A2A agent info query completed - agent not found",
                )
                return None

            registration = self.agents[agent_id]

            result = {
                "agent_id": agent_id,
                "agent_card": registration.agent_card.to_dict(),
                "endpoint": registration.endpoint,
                "status": registration.status,
                "health_score": registration.health_score,
                "response_time_ms": registration.response_time_ms,
                "registered_at": registration.registered_at,
                "last_seen": registration.last_seen,
            }

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={"agent_id": agent_id, "found": True, "status": registration.status},
                description="A2A agent info query completed successfully",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.NETWORK_ERROR,
                level=observability.EventLevel.ERROR,
                data={"agent_id": agent_id, "error": str(e)},
                description="A2A agent info query failed",
            )
            return None

    def get_formation_status(self) -> Dict[str, Any]:
        """
        Get overall formation status.

        Returns:
            Formation status information
        """
        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.DEBUG,
                data={"formation_name": self.formation_name},
                description="A2A formation status query started",
            )

            total_agents = len(self.agents)
            active_agents = len([a for a in self.agents.values() if a.status == "active"])
            inactive_agents = len([a for a in self.agents.values() if a.status == "inactive"])
            unreachable_agents = len([a for a in self.agents.values() if a.status == "unreachable"])

            avg_health_score = 0.0
            if total_agents > 0:
                avg_health_score = sum(a.health_score for a in self.agents.values()) / total_agents

            capabilities = set()
            for agent in self.agents.values():
                capabilities.update(agent.agent_card.capabilities.keys())

            result = {
                "formation_name": self.formation_name,
                "discovery_port": self.discovery_port,
                "total_agents": total_agents,
                "active_agents": active_agents,
                "inactive_agents": inactive_agents,
                "unreachable_agents": unreachable_agents,
                "avg_health_score": round(avg_health_score, 2),
                "available_capabilities": sorted(list(capabilities)),
                "service_uptime": time.time() - getattr(self, "start_time", time.time()),
            }

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={
                    "formation_name": self.formation_name,
                    "total_agents": total_agents,
                    "active_agents": active_agents,
                    "avg_health_score": round(avg_health_score, 2),
                },
                description="A2A formation status query completed",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={"formation_name": self.formation_name, "error": str(e)},
                description="A2A formation status query failed",
            )
            return {}

    async def _fetch_agent_card(self, endpoint: str) -> AgentCard:
        """Fetch agent card from agent endpoint."""
        url = f"{endpoint}/.well-known/agent.json"

        response = await self.http_client.get(url)
        response.raise_for_status()

        card_data = response.json()
        return AgentCard.from_dict(card_data)

    async def _health_check_agent(self, agent_id: str, registration: AgentRegistration) -> bool:
        """Perform health check on a single agent."""
        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": agent_id,
                    "endpoint": registration.endpoint,
                    "formation_name": self.formation_name,
                },
                description="A2A agent health check started",
            )

            start_time = time.time()

            # Try to fetch agent card as health check
            health_url = f"{registration.endpoint}/.well-known/agent.json"
            response = await self.http_client.get(health_url)

            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                registration.status = "active"
                registration.last_seen = time.time()
                registration.response_time_ms = response_time_ms

                # Calculate health score based on response time
                if response_time_ms < 100:
                    registration.health_score = 1.0
                elif response_time_ms < 500:
                    registration.health_score = 0.8
                elif response_time_ms < 1000:
                    registration.health_score = 0.6
                elif response_time_ms < 2000:
                    registration.health_score = 0.4
                else:
                    registration.health_score = 0.2

                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "agent_id": agent_id,
                        "status": "active",
                        "response_time_ms": response_time_ms,
                        "health_score": registration.health_score,
                    },
                    description="A2A agent health check completed successfully",
                )

                return True
            else:
                registration.status = "inactive"
                registration.health_score = 0.1

                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": agent_id,
                        "status": "inactive",
                        "status_code": response.status_code,
                        "health_score": registration.health_score,
                    },
                    description="A2A agent health check completed with non-200 status",
                )

                return False

        except Exception as e:
            registration.status = "unreachable"
            registration.health_score = 0.0

            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "status": "unreachable",
                    "error": str(e),
                    "health_score": 0.0,
                },
                description="A2A agent health check failed",
            )

            return False

    async def _health_check_loop(self):
        """Background task for health checking agents."""
        while self.is_running:
            try:
                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                    level=observability.EventLevel.DEBUG,
                    data={"formation_name": self.formation_name, "agent_count": len(self.agents)},
                    description="A2A health check loop iteration started",
                )

                # Health check all agents
                tasks = []
                for agent_id, registration in self.agents.items():
                    task = self._health_check_agent(agent_id, registration)
                    tasks.append(task)

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={"formation_name": self.formation_name, "agents_checked": len(tasks)},
                    description="A2A health check loop iteration completed",
                )

                # Wait for next health check
                await asyncio.sleep(self.config.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={"formation_name": self.formation_name, "error": str(e)},
                    description="A2A health check loop error",
                )

                await asyncio.sleep(5)  # Short delay on error

    async def _cleanup_loop(self):
        """Background task for cleaning up inactive agents."""
        while self.is_running:
            try:
                observability.observe(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                    level=observability.EventLevel.DEBUG,
                    data={"formation_name": self.formation_name, "agent_count": len(self.agents)},
                    description="A2A cleanup loop iteration started",
                )

                current_time = time.time()
                cleaned_up_agents = 0

                for agent_id, registration in self.agents.items():
                    # Remove agents that haven't been seen for too long
                    if current_time - registration.last_seen > self.config.agent_timeout:
                        if registration.status != "unreachable":
                            registration.status = "unreachable"
                            registration.health_score = 0.0
                            cleaned_up_agents += 1

                            observability.observe(
                                event_type=observability.SystemEvents.A2A_DEREGISTERED,
                                level=observability.EventLevel.INFO,
                                data={
                                    "agent_id": agent_id,
                                    "formation_name": self.formation_name,
                                    "timeout_seconds": self.config.agent_timeout,
                                    "last_seen_ago": current_time - registration.last_seen,
                                },
                                description="A2A agent marked as unreachable due to timeout",
                            )

                observability.observe(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "formation_name": self.formation_name,
                        "cleaned_up_agents": cleaned_up_agents,
                    },
                    description="A2A cleanup loop iteration completed",
                )

                # Wait before next cleanup check
                await asyncio.sleep(60)  # Check every minute

            except asyncio.CancelledError:
                break
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={"formation_name": self.formation_name, "error": str(e)},
                    description="A2A cleanup loop error",
                )

                await asyncio.sleep(10)

    def _load_registry(self):
        """Load persisted registry from file."""
        if not self.config.registry_file:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={"formation_name": self.formation_name},
                description="A2A registry loading skipped - no registry file configured",
            )
            return

        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "formation_name": self.formation_name,
                    "registry_file": self.config.registry_file,
                },
                description="A2A registry loading started",
            )

            registry_path = Path(self.config.registry_file)
            if not registry_path.exists():
                observability.observe(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "formation_name": self.formation_name,
                        "registry_file": self.config.registry_file,
                    },
                    description="A2A registry file not found, starting with empty registry",
                )
                return

            with open(registry_path, "r") as f:
                data = json.load(f)

            # Restore agents (mark as inactive since we don't know current status)
            loaded_agents = 0
            failed_agents = 0
            for agent_data in data.get("agents", []):
                try:
                    agent_card = AgentCard.from_dict(agent_data["agent_card"])
                    registration = AgentRegistration(
                        agent_id=agent_data["agent_id"],
                        agent_card=agent_card,
                        endpoint=agent_data["endpoint"],
                        registered_at=agent_data["registered_at"],
                        last_seen=agent_data["last_seen"],
                        status="inactive",  # Will be updated by health check
                        health_score=0.0,
                    )
                    self.agents[agent_data["agent_id"]] = registration
                    loaded_agents += 1
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.WARNING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": agent_data.get("agent_id", "unknown"),
                            "error_type": type(e).__name__,
                            "error": str(e),
                        },
                        description=f"Failed to load agent from registry: {str(e)}",
                    )
                    failed_agents += 1

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "formation_name": self.formation_name,
                    "loaded_agents": loaded_agents,
                    "failed_agents": failed_agents,
                    "total_agents": len(self.agents),
                },
                description="A2A registry loaded successfully",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "formation_name": self.formation_name,
                    "registry_file": self.config.registry_file,
                    "error": str(e),
                },
                description="A2A registry loading failed",
            )

    def _save_registry(self):
        """Save current registry to file."""
        if not self.config.registry_file:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={"formation_name": self.formation_name},
                description="A2A registry saving skipped - no registry file configured",
            )
            return

        try:
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "formation_name": self.formation_name,
                    "registry_file": self.config.registry_file,
                    "agent_count": len(self.agents),
                },
                description="A2A registry saving started",
            )

            registry_path = Path(self.config.registry_file)
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            # Prepare data for serialization
            agents_data = []
            for agent_id, registration in self.agents.items():
                agents_data.append(
                    {
                        "agent_id": agent_id,
                        "agent_card": registration.agent_card.to_dict(),
                        "endpoint": registration.endpoint,
                        "registered_at": registration.registered_at,
                        "last_seen": registration.last_seen,
                        "status": registration.status,
                        "health_score": registration.health_score,
                    }
                )

            data = {
                "formation_name": self.formation_name,
                "agents": agents_data,
                "saved_at": time.time(),
            }

            with open(registry_path, "w") as f:
                json.dump(data, f, indent=2)

            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={"formation_name": self.formation_name, "saved_agents": len(self.agents)},
                description="A2A registry saved successfully",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "formation_name": self.formation_name,
                    "registry_file": self.config.registry_file,
                    "error": str(e),
                },
                description="A2A registry saving failed",
            )


class DiscoveryServiceManager:
    """
    Manager for multiple discovery services (useful for multi-formation deployments).
    """

    def __init__(self):
        self.services: Dict[str, LocalDiscoveryService] = {}

    async def create_service(
        self, formation_name: str, config: Optional[DiscoveryConfig] = None
    ) -> LocalDiscoveryService:
        """Create and start a discovery service for a formation."""
        if formation_name in self.services:
            raise ValueError(f"Discovery service for formation '{formation_name}' already exists")

        service = LocalDiscoveryService(config)
        await service.start(formation_name)
        self.services[formation_name] = service

        return service

    def get_service(self, formation_name: str) -> Optional[LocalDiscoveryService]:
        """Get discovery service for a formation."""
        return self.services.get(formation_name)

    async def stop_service(self, formation_name: str) -> bool:
        """Stop discovery service for a formation."""
        if formation_name not in self.services:
            return False

        await self.services[formation_name].stop()
        del self.services[formation_name]
        return True

    async def stop_all_services(self):
        """Stop all discovery services."""
        for service in self.services.values():
            await service.stop()
        self.services.clear()

    def list_formations(self) -> List[str]:
        """List all formations with active discovery services."""
        return list(self.services.keys())

    def get_global_status(self) -> Dict[str, Any]:
        """Get status of all discovery services."""
        formations = {}
        total_agents = 0

        for formation_name, service in self.services.items():
            status = service.get_formation_status()
            formations[formation_name] = status
            total_agents += status["total_agents"]

        return {
            "total_formations": len(self.services),
            "total_agents": total_agents,
            "formations": formations,
        }
