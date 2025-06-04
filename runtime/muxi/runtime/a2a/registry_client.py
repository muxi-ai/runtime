"""
A2A External Registry Client

This module provides client functionality for communicating with external
A2A registries. It handles agent registration, discovery, and health
monitoring across multiple external registries.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import httpx
import time

from .models import AgentCard

logger = logging.getLogger(__name__)


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

        logger.info(f"Initialized A2ARegistryClient with {len(self.registries)} registries")

    async def close(self):
        """Close the HTTP client"""
        await self.http_client.aclose()

    def add_registry(self, registry_url: str) -> None:
        """Add a new registry URL to the client"""
        if registry_url not in self.registries:
            self.registries.append(registry_url)
            self.registry_status[registry_url] = {"last_check": None, "healthy": None}
            self.registered_agents[registry_url] = []
            logger.info(f"Added registry: {registry_url}")

    def remove_registry(self, registry_url: str) -> None:
        """Remove a registry URL from the client"""
        if registry_url in self.registries:
            self.registries.remove(registry_url)
            self.registry_status.pop(registry_url, None)
            self.registered_agents.pop(registry_url, None)
            logger.info(f"Removed registry: {registry_url}")

    async def health_check(self, registry_url: str) -> bool:
        """
        Check if a registry is healthy and responding.

        Args:
            registry_url: URL of the registry to check

        Returns:
            True if registry is healthy, False otherwise
        """
        try:
            response = await self.http_client.get(f"{registry_url}/health")
            is_healthy = response.status_code == 200

            # Update status tracking
            self.registry_status[registry_url] = {
                "last_check": time.time(),
                "healthy": is_healthy,
                "status_code": response.status_code
            }

            if is_healthy:
                logger.debug(f"Registry {registry_url} is healthy")
            else:
                logger.warning(f"Registry {registry_url} unhealthy: {response.status_code}")

            return is_healthy

        except Exception as e:
            logger.error(f"Health check failed for {registry_url}: {e}")
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
        if not self.registries:
            return {}

        tasks = [self.health_check(registry) for registry in self.registries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            registry: (result if isinstance(result, bool) else False)
            for registry, result in zip(self.registries, results)
        }

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
        if registry_url:
            return await self._register_single(agent_card, registry_url)
        else:
            return await self._register_all(agent_card)

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

                logger.info(f"Registered agent {agent_card.name} with {registry_url}")

                return RegistryResponse(
                    success=True,
                    status_code=response.status_code,
                    data=response.json() if response.content else None,
                    registry_url=registry_url
                )
            else:
                error_msg = f"Registration failed: {response.status_code}"
                logger.error(f"Failed to register {agent_card.name} on {registry_url}: {error_msg}")

                return RegistryResponse(
                    success=False,
                    status_code=response.status_code,
                    error=error_msg,
                    registry_url=registry_url
                )

        except Exception as e:
            error_msg = f"Registration error: {e}"
            logger.error(f"Failed to register {agent_card.name} on {registry_url}: {error_msg}")

            return RegistryResponse(
                success=False,
                error=error_msg,
                registry_url=registry_url
            )

    async def _register_all(self, agent_card: AgentCard) -> Dict[str, RegistryResponse]:
        """Register agent with all configured registries"""
        if not self.registries:
            return {}

        tasks = [self._register_single(agent_card, registry) for registry in self.registries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        response_dict = {}
        for registry, result in zip(self.registries, results):
            if isinstance(result, Exception):
                response_dict[registry] = RegistryResponse(
                    success=False,
                    error=str(result),
                    registry_url=registry
                )
            else:
                response_dict[registry] = result

        return response_dict

    async def deregister_agent(self, agent_url: str) -> Dict[str, RegistryResponse]:
        """
        Deregister an agent from all configured registries.

        Args:
            agent_url: The URL of the agent to deregister

        Returns:
            Dict mapping registry URLs to RegistryResponse objects
        """
        responses = {}

        for registry_url in self.registries:
            try:
                # Use POST /deregister with JSON body instead of DELETE with URL encoding
                deregister_url = f"{registry_url}/deregister"

                payload = {"agent_url": agent_url}

                response = await self.http_client.post(
                    deregister_url,
                    json=payload,
                    timeout=self.config.timeout_seconds
                )

                if response.status_code == 200:
                    response_data = response.json()
                    responses[registry_url] = RegistryResponse(
                        success=True,
                        data=response_data,
                        error=None
                    )
                    logger.info(f"Successfully deregistered agent from {registry_url}")
                else:
                    error_detail = "Unknown error"
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("detail", str(response.status_code))
                    except Exception:
                        error_detail = f"HTTP {response.status_code}"

                    error_msg = f"Deregistration failed: {error_detail}"
                    responses[registry_url] = RegistryResponse(
                        success=False,
                        data=None,
                        error=error_msg
                    )
                    logger.warning(
                        f"Failed to deregister {agent_url} from {registry_url}: {error_msg}"
                    )

            except Exception as e:
                error_msg = f"Request failed: {str(e)}"
                responses[registry_url] = RegistryResponse(
                    success=False,
                    data=None,
                    error=error_msg
                )
                logger.error(f"Failed to deregister {agent_url} from {registry_url}: {error_msg}")

        return responses

    async def discover_agents(
        self,
        capability_filter: Optional[List[str]] = None,
        registry_url: Optional[str] = None
    ) -> Union[List[AgentCard], Dict[str, List[AgentCard]]]:
        """
        Discover agents from external registry(ies).

        Args:
            capability_filter: List of capabilities to filter by
            registry_url: Specific registry URL, or None to discover from all

        Returns:
            List of AgentCards for single registry, or dict mapping registry URLs to AgentCard lists
        """
        if registry_url:
            return await self._discover_single(registry_url, capability_filter)
        else:
            return await self._discover_all(capability_filter)

    async def _discover_single(
        self,
        registry_url: str,
        capability_filter: Optional[List[str]] = None
    ) -> List[AgentCard]:
        """Discover agents from a single registry"""
        try:
            # Build query parameters
            params = {}
            if capability_filter:
                params["capabilities"] = ",".join(capability_filter)

            response = await self.http_client.get(f"{registry_url}/discover", params=params)

            if response.status_code == 200:
                data = response.json()
                agents = data if isinstance(data, list) else data.get("agents", [])

                # Convert to AgentCard objects
                agent_cards = []
                for agent_data in agents:
                    try:
                        agent_card = AgentCard.from_dict(agent_data)
                        agent_cards.append(agent_card)
                    except Exception as e:
                        logger.warning(f"Failed to parse agent card from {registry_url}: {e}")

                logger.info(f"Discovered {len(agent_cards)} agents from {registry_url}")
                return agent_cards
            else:
                logger.error(f"Discovery failed for {registry_url}: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Discovery error for {registry_url}: {e}")
            return []

    async def _discover_all(
            self, capability_filter: Optional[List[str]] = None) -> Dict[str, List[AgentCard]]:
        """Discover agents from all configured registries"""
        if not self.registries:
            return {}

        tasks = [self._discover_single(registry, capability_filter) for registry in self.registries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        response_dict = {}
        for registry, result in zip(self.registries, results):
            if isinstance(result, Exception):
                logger.error(f"Discovery failed for {registry}: {result}")
                response_dict[registry] = []
            else:
                response_dict[registry] = result

        return response_dict

    def get_registry_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current status of all registries"""
        return self.registry_status.copy()

    def get_registered_agents(self) -> Dict[str, List[str]]:
        """Get list of agents registered with each registry"""
        return self.registered_agents.copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        healthy_registries = sum(
            1 for status in self.registry_status.values()
            if status.get("healthy", False)
        )

        total_registered = sum(len(agents) for agents in self.registered_agents.values())

        return {
            "total_registries": len(self.registries),
            "healthy_registries": healthy_registries,
            "total_registered_agents": total_registered,
            "registries": list(self.registries),
            "last_health_check": max(
                (status.get("last_check", 0) for status in self.registry_status.values()),
                default=None
            )
        }
