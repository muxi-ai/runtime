"""
A2A External Registry Client using A2A SDK

This module provides SDK-based client functionality for communicating with external
A2A registries. It handles agent registration, discovery, and health
monitoring across multiple external registries using the official A2A SDK.
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import time
import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard as SDKAgentCard,
    Message,
    TextPart,
    Role,
    SendMessageRequest,
)

from .. import observability
from .models import AgentCard
from .models_adapter import ModelsAdapter


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
    SDK-based client for communicating with external A2A registries.

    This implementation uses the official A2A SDK for all registry operations,
    ensuring protocol compliance and future compatibility.
    """

    def __init__(
        self,
        registries: Optional[List[str]] = None,
        config: Optional[RegistryConfig] = None
    ):
        """
        Initialize the SDK-based external registry client.

        Args:
            registries: List of registry URLs from formation config
            config: Client configuration options
        """
        try:
            self.registries = registries or []
            self.config = config or RegistryConfig()

            # Initialize A2A SDK clients for each registry
            self.sdk_clients: Dict[str, A2AClient] = {}
            self.httpx_clients: Dict[str, httpx.AsyncClient] = {}

            for registry_url in self.registries:
                # Create httpx client for this registry with base_url for consistent routing
                self.httpx_clients[registry_url] = httpx.AsyncClient(
                    base_url=registry_url,
                    timeout=self.config.timeout_seconds,
                    headers={"User-Agent": self.config.user_agent}
                )

                # Create SDK client with httpx client
                self.sdk_clients[registry_url] = A2AClient(
                    httpx_client=self.httpx_clients[registry_url],
                    url=registry_url
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
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                level=observability.EventLevel.INFO,
                description=f"A2A Registry Client (SDK) initialized with {len(self.registries)} registries",
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "timeout_seconds": self.config.timeout_seconds,
                    "max_retries": self.config.max_retries,
                    "sdk_enabled": True
                }
            )

        except Exception as e:
            # Emit error event for initialization failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to initialize A2A Registry Client (SDK): {str(e)}",
                data={
                    "registries_count": len(registries) if registries else 0,
                    "error": str(e)
                }
            )
            raise

    async def close(self):
        """Close all SDK and httpx clients"""
        try:
            # Close all httpx clients
            for client in self.httpx_clients.values():
                await client.aclose()

            # Close all SDK clients if they have close method
            for client in self.sdk_clients.values():
                if hasattr(client, 'close'):
                    await client.close()

            # Emit client close event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                level=observability.EventLevel.INFO,
                description="A2A Registry Client (SDK) closed",
                data={
                    "registries_count": len(self.registries),
                    "total_registered_agents": sum(
                        len(agents) for agents in self.registered_agents.values()
                    ),
                }
            )

        except Exception as e:
            # Emit error event for close failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to close A2A Registry Client (SDK): {str(e)}",
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

                # Create httpx client for new registry
                self.httpx_clients[registry_url] = httpx.AsyncClient(
                    base_url=registry_url,
                    timeout=self.config.timeout_seconds,
                    headers={"User-Agent": self.config.user_agent}
                )

                # Create SDK client with httpx client (consistent with __init__)
                self.sdk_clients[registry_url] = A2AClient(
                    httpx_client=self.httpx_clients[registry_url],
                    url=registry_url
                )

                # Emit registry addition event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                    level=observability.EventLevel.INFO,
                    description=f"Added registry (SDK): {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries),
                        "sdk_enabled": True
                    }
                )
            else:
                # Emit warning for duplicate registry
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                    level=observability.EventLevel.WARNING,
                    description=f"Registry already exists (SDK): {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries)
                    }
                )

        except Exception as e:
            # Emit error event for registry addition failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to add registry (SDK) {registry_url}: {str(e)}",
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

                # Close and remove SDK client
                if registry_url in self.sdk_clients:
                    client = self.sdk_clients.pop(registry_url)
                    if hasattr(client, 'close'):
                        asyncio.create_task(client.close())

                # Emit registry removal event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                    level=observability.EventLevel.INFO,
                    description=f"Removed registry (SDK): {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "agents_removed": agents_count,
                        "remaining_registries": len(self.registries)
                    }
                )
            else:
                # Emit warning for non-existent registry
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                    level=observability.EventLevel.WARNING,
                    description=f"Registry not found for removal (SDK): {registry_url}",
                    data={
                        "registry_url": registry_url,
                        "total_registries": len(self.registries)
                    }
                )

        except Exception as e:
            # Emit error event for registry removal failure
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to remove registry (SDK) {registry_url}: {str(e)}",
                data={
                    "registry_url": registry_url,
                    "error": str(e)
                }
            )
            raise

    def _convert_to_sdk_agent_card(self, agent_card: AgentCard) -> SDKAgentCard:
        """Convert MUXI AgentCard to SDK AgentCard using ModelsAdapter"""
        return ModelsAdapter.muxi_to_sdk_agent_card(agent_card)

    def _convert_from_sdk_agent_card(self, sdk_card: SDKAgentCard) -> AgentCard:
        """Convert SDK AgentCard to MUXI AgentCard using ModelsAdapter"""
        return ModelsAdapter.sdk_to_muxi_agent_card(sdk_card)

    async def health_check(self, registry_url: str) -> bool:
        """
        Check if a registry is healthy and responding using SDK.

        Args:
            registry_url: URL of the registry to check

        Returns:
            True if registry is healthy, False otherwise
        """
        try:
            # Emit health check start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                level=observability.EventLevel.DEBUG,
                description=f"Starting health check for registry (SDK): {registry_url}",
                data={"registry_url": registry_url, "sdk_enabled": True}
            )

            client = self.sdk_clients.get(registry_url)
            if not client:
                return False

            # Use SDK to send health check message
            health_message = Message(
                message_id="health_check",
                role=Role.agent,
                parts=[TextPart(text="health", kind="text")],
                metadata={"type": "health_check"},
                kind="message"
            )

            # Send health check via SDK
            request = SendMessageRequest(
                agent_id="registry",
                message=health_message,
                timeout=5
            )

            # Try to send the health check message
            # If registry is healthy, it should respond or at least accept the message
            try:
                await client.send_message(request)
                is_healthy = True
            except Exception as e:
                # Only consider healthy if it's a method not allowed error (health endpoint exists but rejects messages)
                # Connectivity issues or other errors should mark as unhealthy
                error_msg = str(e).lower()
                if "method not allowed" in error_msg or "405" in error_msg:
                    is_healthy = True  # Health endpoint exists but doesn't accept messages
                else:
                    is_healthy = False  # Real connectivity or server issue

            # Update status tracking
            self.registry_status[registry_url] = {
                "last_check": time.time(),
                "healthy": is_healthy,
                "sdk_check": True
            }

            # Emit health check result event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                level=observability.EventLevel.INFO if is_healthy else observability.EventLevel.WARNING,
                description=f"Registry health check {'passed' if is_healthy else 'failed'} (SDK): {registry_url}",
                data={
                    "registry_url": registry_url,
                    "healthy": is_healthy,
                    "sdk_enabled": True
                }
            )

            return is_healthy

        except Exception as e:
            # Emit health check error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Health check failed for registry (SDK): {registry_url}",
                data={
                    "registry_url": registry_url,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )

            self.registry_status[registry_url] = {
                "last_check": time.time(),
                "healthy": False,
                "error": str(e)
            }
            return False

    async def check_registries_with_policy(
        self,
        startup_policy: str = "lenient",
        retry_timeout_seconds: int = 30,
        registry_configs: Optional[List[Dict[str, Any]]] = None
    ) -> tuple[bool, Dict[str, bool]]:
        """
        Check registry health according to startup policy.

        Args:
            startup_policy: "lenient", "strict", or "retry"
            retry_timeout_seconds: How long to retry for "retry" policy
            registry_configs: List of registry configurations with required flags

        Returns:
            Tuple of (should_continue, health_status)
            - should_continue: Whether formation should start based on policy
            - health_status: Dict mapping registry URLs to health status
        """
        try:
            # Parse registry configs to find required ones
            required_registries = set()
            if registry_configs:
                for config in registry_configs:
                    if isinstance(config, dict) and config.get("required", False):
                        required_registries.add(config.get("url"))

            # Emit startup policy check event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                level=observability.EventLevel.INFO,
                description=f"Checking registries with {startup_policy} policy",
                data={
                    "startup_policy": startup_policy,
                    "retry_timeout_seconds": retry_timeout_seconds,
                    "total_registries": len(self.registries),
                    "required_registries": len(required_registries),
                    "required_urls": list(required_registries)
                }
            )

            if startup_policy == "lenient":
                # Just check once and continue regardless
                health_status = await self.health_check_all()

                # Log warnings for unhealthy registries
                for registry_url, is_healthy in health_status.items():
                    if not is_healthy:
                        observability.observe(
                            event_type=observability.SystemEvents.A2A_REGISTRY_DISCONNECTED,
                            level=observability.EventLevel.WARNING,
                            description=f"Registry {registry_url} is unreachable (lenient mode - continuing)",
                            data={"registry_url": registry_url, "policy": "lenient"}
                        )

                return (True, health_status)  # Always continue in lenient mode

            elif startup_policy == "strict":
                # Check once and fail if any required registry is down
                health_status = await self.health_check_all()

                # In strict mode, treat ALL registries as required unless explicitly marked optional
                # If no explicit required registries specified, all are required
                registries_to_check = required_registries if required_registries else set(self.registries)

                # Check if any required registry is down
                for registry_url in registries_to_check:
                    if registry_url in health_status and not health_status[registry_url]:
                        observability.observe(
                            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                            level=observability.EventLevel.ERROR,
                            description=f"Registry {registry_url} is unreachable (strict mode)",
                            data={
                                "registry_url": registry_url,
                                "policy": "strict",
                                "required": True,
                                "explicit_required": registry_url in required_registries
                            }
                        )
                        return (False, health_status)  # Fail fast

                # All registries are up
                return (True, health_status)

            elif startup_policy == "retry":
                # Retry for specified duration, then apply required flags
                start_time = time.time()
                best_health_status = {}

                # In retry mode with no explicit requirements, treat all as required
                registries_to_check = required_registries if required_registries else set(self.registries)

                while time.time() - start_time < retry_timeout_seconds:
                    health_status = await self.health_check_all()

                    # Track best results
                    for url, status in health_status.items():
                        if status:
                            best_health_status[url] = True

                    # Check if all required registries are up
                    all_required_up = True
                    for registry_url in registries_to_check:
                        if registry_url in health_status and not health_status[registry_url]:
                            all_required_up = False
                            break

                    if all_required_up:
                        observability.observe(
                            event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                            level=observability.EventLevel.INFO,
                            description="All required registries are healthy",
                            data={
                                "policy": "retry",
                                "retry_time": time.time() - start_time,
                                "health_status": health_status
                            }
                        )
                        return (True, health_status)

                    # Wait before retrying
                    await asyncio.sleep(min(5, retry_timeout_seconds / 6))

                # Timeout reached - check required registries
                final_health = {**health_status, **best_health_status}
                for registry_url in registries_to_check:
                    if registry_url in final_health and not final_health[registry_url]:
                        observability.observe(
                            event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                            level=observability.EventLevel.ERROR,
                            description=f"Registry {registry_url} still unreachable after {retry_timeout_seconds}s",
                            data={
                                "registry_url": registry_url,
                                "policy": "retry",
                                "retry_timeout": retry_timeout_seconds,
                                "required": True,
                                "explicit_required": registry_url in required_registries
                            }
                        )
                        return (False, final_health)

                return (True, final_health)

            else:
                # Unknown policy - default to lenient
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CONNECTED,
                    level=observability.EventLevel.WARNING,
                    description=f"Unknown startup policy '{startup_policy}', defaulting to lenient",
                    data={"policy": startup_policy}
                )
                health_status = await self.health_check_all()
                return (True, health_status)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to check registries with policy: {str(e)}",
                data={"error": str(e), "policy": startup_policy}
            )
            # On error, fail if strict, continue if lenient/retry
            return (startup_policy != "strict", {})

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all configured registries using SDK.

        Returns:
            Dictionary mapping registry URLs to health status
        """
        try:
            if not self.registries:
                # Emit no registries event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                    level=observability.EventLevel.WARNING,
                    description="No registries configured for health check (SDK)",
                    data={"registries_count": 0, "sdk_enabled": True}
                )
                return {}

            # Emit health check all start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Starting health check for all {len(self.registries)} registries (SDK)",
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "sdk_enabled": True
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
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_COMPLETED,
                level=observability.EventLevel.INFO,
                description="Health check completed for all registries (SDK)",
                data={
                    "registries_count": len(self.registries),
                    "healthy_count": healthy_count,
                    "unhealthy_count": len(self.registries) - healthy_count,
                    "health_status": health_status,
                    "sdk_enabled": True
                }
            )

            return health_status

        except Exception as e:
            # Emit health check all error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"Failed to perform health check on all registries (SDK): {str(e)}",
                data={
                    "registries_count": len(self.registries),
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            raise

    async def register_agent(
        self,
        agent_card: AgentCard,
        registry_url: Optional[str] = None
    ) -> Union[RegistryResponse, Dict[str, RegistryResponse]]:
        """
        Register an agent with external registry(ies) using SDK.

        Args:
            agent_card: Agent card to register
            registry_url: Specific registry URL, or None to register with all

        Returns:
            RegistryResponse for single registry, or dict of responses for all registries
        """
        try:
            # Emit agent registration start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Starting agent registration for {agent_card.name} (SDK)",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "target_registry": registry_url,
                    "register_all": registry_url is None,
                    "sdk_enabled": True
                }
            )

            if registry_url:
                return await self._register_single(agent_card, registry_url)
            else:
                return await self._register_all(agent_card)

        except Exception as e:
            # Emit agent registration error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent registration failed for {agent_card.name} (SDK): {str(e)}",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "target_registry": registry_url,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            raise

    async def _register_single(self, agent_card: AgentCard, registry_url: str) -> RegistryResponse:
        """Register agent with a single registry using HTTP (registries are not A2A agents)"""
        try:
            # Get the httpx client for this registry
            http_client = self.httpx_clients.get(registry_url)
            if not http_client:
                return RegistryResponse(
                    success=False,
                    error=f"No HTTP client for registry: {registry_url}",
                    registry_url=registry_url
                )

            # Send the MUXI AgentCard directly - the registry expects MUXI format, not SDK format!
            # The registry is a MUXI service, not an A2A SDK service
            agent_data = {
                "name": agent_card.name,
                "description": agent_card.description,
                "version": agent_card.version,
                "url": agent_card.url,
                "a2aVersion": getattr(agent_card, 'a2a_version', "1.0"),
                "capabilities": agent_card.capabilities or {},
                "authentication": getattr(agent_card, 'authentication', None),
                "endpoints": getattr(agent_card, 'endpoints', {}),
                "metadata": agent_card.metadata or {}
            }

            # Send HTTP POST to registry's /register endpoint
            response = await http_client.post(
                f"{registry_url}/register",
                json=agent_data
            )

            # Check if registration was successful
            if response.status_code == 201:  # Registry returns 201 for successful registration
                # Track successful registration
                if registry_url not in self.registered_agents:
                    self.registered_agents[registry_url] = []
                if agent_card.url not in self.registered_agents[registry_url]:
                    self.registered_agents[registry_url].append(agent_card.url)

                # Emit successful registration event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTERED,
                    level=observability.EventLevel.INFO,
                    description=f"Agent {agent_card.name} registered successfully with {registry_url} (SDK)",
                    data={
                        "agent_name": agent_card.name,
                        "agent_url": agent_card.url,
                        "registry_url": registry_url,
                        "total_registered": len(self.registered_agents[registry_url]),
                        "sdk_enabled": True
                    }
                )

                return RegistryResponse(
                    success=True,
                    status_code=response.status_code,
                    data=response.json() if response.text else None,
                    registry_url=registry_url
                )
            else:
                # Registration failed
                error_msg = f"Registration failed with status {response.status_code}"
                if response.text:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("detail", error_msg)
                    except Exception:
                        error_msg = response.text

                return RegistryResponse(
                    success=False,
                    status_code=response.status_code,
                    error=error_msg,
                    registry_url=registry_url
                )

        except Exception as e:
            error_msg = f"Registration error (SDK): {str(e)}"

            # Emit registration error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent registration error for {agent_card.name} on {registry_url} (SDK)",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registry_url": registry_url,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )

            return RegistryResponse(
                success=False,
                error=error_msg,
                registry_url=registry_url
            )

    async def _register_all(self, agent_card: AgentCard) -> Dict[str, RegistryResponse]:
        """Register agent with all configured registries using SDK"""
        try:
            if not self.registries:
                # Emit no registries event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"No registries configured for agent {agent_card.name} (SDK)",
                    data={
                        "agent_name": agent_card.name,
                        "agent_url": agent_card.url,
                        "registries_count": 0,
                        "sdk_enabled": True
                    }
                )
                return {}

            # Emit register all start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Registering agent {agent_card.name} with all {len(self.registries)} registries (SDK)",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "sdk_enabled": True
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
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Agent registration completed for {agent_card.name} (SDK)",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "successful_registrations": successful_registrations,
                    "failed_registrations": len(self.registries) - successful_registrations,
                    "sdk_enabled": True
                }
            )

            return responses

        except Exception as e:
            # Emit register all error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"Failed to register agent {agent_card.name} with all registries (SDK): {str(e)}",
                data={
                    "agent_name": agent_card.name,
                    "agent_url": agent_card.url,
                    "registries_count": len(self.registries),
                    "error": str(e),
                    "sdk_enabled": True
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
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description=f"No registrations found for agent (SDK): {agent_url}",
                    data={
                        "agent_url": agent_url,
                        "total_registries": len(self.registries),
                        "sdk_enabled": True
                    }
                )
                return {}

            # Emit deregistration start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Starting deregistration for agent (SDK): {agent_url}",
                data={
                    "agent_url": agent_url,
                    "target_registries": target_registries,
                    "registrations_count": len(target_registries),
                    "sdk_enabled": True
                }
            )

            responses = {}
            successful_deregistrations = 0

            for registry_url in target_registries:
                try:
                    # Get the httpx client for this registry (NOT the SDK client)
                    http_client = self.httpx_clients.get(registry_url)
                    if not http_client:
                        continue

                    # Send HTTP POST to registry's /deregister endpoint with MUXI format
                    # The registry expects {"agent_url": "..."} not SDK messages
                    response = await http_client.post(
                        f"{registry_url}/deregister",
                        json={"agent_url": agent_url}
                    )

                    # Check if deregistration was successful
                    if response.status_code == 200:
                        # Remove from tracking
                        if agent_url in self.registered_agents[registry_url]:
                            self.registered_agents[registry_url].remove(agent_url)

                        # Emit successful deregistration event
                        observability.observe(
                            event_type=observability.SystemEvents.A2A_REGISTERED,
                            level=observability.EventLevel.INFO,
                            description=f"Agent deregistered successfully from {registry_url} (SDK)",
                            data={
                                "agent_url": agent_url,
                                "registry_url": registry_url,
                                "sdk_enabled": True
                            }
                        )

                        responses[registry_url] = RegistryResponse(
                            success=True,
                            status_code=response.status_code,
                            data=response.json() if response.text else None,
                            registry_url=registry_url
                        )
                        successful_deregistrations += 1
                    else:
                        # Deregistration failed
                        error_msg = f"Deregistration failed with status {response.status_code}"
                        if response.text:
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("detail", error_msg)
                            except Exception:
                                error_msg = response.text

                        responses[registry_url] = RegistryResponse(
                            success=False,
                            status_code=response.status_code,
                            error=error_msg,
                            registry_url=registry_url
                        )

                except Exception as e:
                    error_msg = f"Deregistration error (SDK): {str(e)}"

                    # Emit deregistration error event
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_REGISTRATION_FAILED,
                        level=observability.EventLevel.ERROR,
                        description=f"Agent deregistration error from {registry_url} (SDK)",
                        data={
                            "agent_url": agent_url,
                            "registry_url": registry_url,
                            "error": str(e),
                            "sdk_enabled": True
                        }
                    )

                    responses[registry_url] = RegistryResponse(
                        success=False,
                        error=error_msg,
                        registry_url=registry_url
                    )

            # Emit deregistration summary event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTERED,
                level=observability.EventLevel.INFO,
                description=f"Agent deregistration completed for {agent_url} (SDK)",
                data={
                    "agent_url": agent_url,
                    "target_registries_count": len(target_registries),
                    "successful_deregistrations": successful_deregistrations,
                    "failed_deregistrations": len(target_registries) - successful_deregistrations,
                    "sdk_enabled": True
                }
            )

            return responses

        except Exception as e:
            # Emit deregistration error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"Failed to deregister agent {agent_url} (SDK): {str(e)}",
                data={
                    "agent_url": agent_url,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            raise

    async def discover_agents(
        self,
        capability_filter: Optional[List[str]] = None,
        registry_url: Optional[str] = None
    ) -> Union[List[AgentCard], Dict[str, List[AgentCard]]]:
        """
        Discover agents from external registry(ies) using SDK.

        Args:
            capability_filter: Optional list of required capabilities
            registry_url: Specific registry URL, or None to discover from all

        Returns:
            List of AgentCards for single registry, or dict for all registries
        """
        try:
            # Emit discovery start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                description="Starting agent discovery (SDK)",
                data={
                    "capability_filter": capability_filter,
                    "target_registry": registry_url,
                    "discover_all": registry_url is None,
                    "sdk_enabled": True
                }
            )

            if registry_url:
                return await self._discover_single(registry_url, capability_filter)
            else:
                return await self._discover_all(capability_filter)

        except Exception as e:
            # Emit discovery error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent discovery failed (SDK): {str(e)}",
                data={
                    "capability_filter": capability_filter,
                    "target_registry": registry_url,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            raise

    async def _discover_single(
        self,
        registry_url: str,
        capability_filter: Optional[List[str]] = None
    ) -> List[AgentCard]:
        """Discover agents from a single registry using HTTP (registries are not A2A agents)"""
        try:
            # Get the httpx client for this registry (NOT the SDK client)
            http_client = self.httpx_clients.get(registry_url)
            if not http_client:
                return []

            # Build query parameters
            params = {}
            if capability_filter:
                params["capabilities"] = ",".join(capability_filter)

            # Send HTTP GET to registry's /discover endpoint
            response = await http_client.get(
                f"{registry_url}/discover",
                params=params
            )

            # Extract agents from response
            agent_cards = []
            if response.status_code == 200:
                data = response.json()
                if "agents" in data:
                    for agent_data in data["agents"]:
                        try:
                            # Registry returns MUXI format AgentCards
                            # Create AgentCard from the data
                            agent_card = AgentCard(
                                name=agent_data.get("name"),
                                description=agent_data.get("description"),
                                version=agent_data.get("version"),
                                url=agent_data.get("url"),
                                capabilities=agent_data.get("capabilities", {}),
                                metadata=agent_data.get("metadata", {})
                            )
                            agent_cards.append(agent_card)
                        except Exception as e:
                            # Log conversion error but continue
                            observability.observe(
                                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                                level=observability.EventLevel.WARNING,
                                description="Failed to parse agent card JSON from registry",
                                data={
                                    "registry_url": registry_url,
                                    "agent_name": agent_data.get("name", "unknown"),
                                    "error": str(e),
                                    "agent_data": agent_data
                                }
                            )

            # Emit successful discovery event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                description=f"Agent discovery completed from {registry_url} (SDK)",
                data={
                    "registry_url": registry_url,
                    "agents_discovered": len(agent_cards),
                    "capability_filter": capability_filter,
                    "sdk_enabled": True
                }
            )

            return agent_cards

        except Exception as e:
            # Emit discovery error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Agent discovery error from {registry_url} (SDK)",
                data={
                    "registry_url": registry_url,
                    "capability_filter": capability_filter,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            return []

    async def _discover_all(
        self, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, List[AgentCard]]:
        """Discover agents from all configured registries using SDK"""
        try:
            if not self.registries:
                # Emit no registries event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_DISCOVERY_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="No registries configured for discovery (SDK)",
                    data={
                        "registries_count": 0,
                        "capability_filter": capability_filter,
                        "sdk_enabled": True
                    }
                )
                return {}

            # Emit discover all start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_STARTED,
                level=observability.EventLevel.INFO,
                description=f"Discovering agents from all {len(self.registries)} registries (SDK)",
                data={
                    "registries_count": len(self.registries),
                    "registries": self.registries,
                    "capability_filter": capability_filter,
                    "sdk_enabled": True
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

            # Emit discover all result event
            observability.observe(
                event_type=observability.SystemEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.INFO,
                description="Agent discovery completed from all registries (SDK)",
                data={
                    "registries_count": len(self.registries),
                    "total_agents_discovered": total_agents,
                    "capability_filter": capability_filter,
                    "discoveries_per_registry": {
                        registry: len(agents) for registry, agents in discoveries.items()
                    },
                    "sdk_enabled": True
                }
            )

            return discoveries

        except Exception as e:
            # Emit discover all error event
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.ERROR,
                description=f"Failed to discover agents from all registries (SDK): {str(e)}",
                data={
                    "registries_count": len(self.registries),
                    "capability_filter": capability_filter,
                    "error": str(e),
                    "sdk_enabled": True
                }
            )
            raise

    def get_registry_status(self) -> Dict[str, Dict[str, Any]]:
        """Get the current status of all registries"""
        try:
            # Emit status request event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                level=observability.EventLevel.DEBUG,
                description="Registry status requested (SDK)",
                data={
                    "registries_count": len(self.registry_status),
                    "registries": list(self.registry_status.keys()),
                    "sdk_enabled": True
                }
            )

            return self.registry_status.copy()

        except Exception as e:
            # Emit status request error event
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registry status (SDK): {str(e)}",
                data={"error": str(e), "sdk_enabled": True}
            )
            raise

    def get_registered_agents(self) -> Dict[str, List[str]]:
        """Get the list of registered agents per registry"""
        try:
            # Emit registered agents request event
            observability.observe(
                event_type=observability.SystemEvents.A2A_REGISTERED,
                level=observability.EventLevel.DEBUG,
                description="Registered agents list requested (SDK)",
                data={
                    "registries_count": len(self.registered_agents),
                    "total_agents": sum(len(agents) for agents in self.registered_agents.values()),
                    "sdk_enabled": True
                }
            )

            return self.registered_agents.copy()

        except Exception as e:
            # Emit registered agents request error event
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registered agents (SDK): {str(e)}",
                data={"error": str(e), "sdk_enabled": True}
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
                },
                "sdk_enabled": True
            }

            # Emit stats request event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                level=observability.EventLevel.DEBUG,
                description="Registry client stats requested (SDK)",
                data=stats
            )

            return stats

        except Exception as e:
            # Emit stats request error event
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description=f"Failed to get registry client stats (SDK): {str(e)}",
                data={"error": str(e), "sdk_enabled": True}
            )
            raise
