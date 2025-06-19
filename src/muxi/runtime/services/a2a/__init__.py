"""
A2A (Agent-to-Agent) Communication Module

This module provides comprehensive A2A communication capabilities for MUXI agents,
including agent cards, registry client, and the centralized formation server.
"""

from .models import AgentCard, A2ACapability, A2AEndpoint, A2AAuthentication, AuthType
from .cache_manager import A2ACacheManager
from .card_generator import AgentCardGenerator
from .discovery import (
    LocalDiscoveryService,
    DiscoveryServiceManager,
    DiscoveryConfig,
    AgentRegistration
)
from .registry_client import A2ARegistryClient
from .server import A2AServer

__all__ = [
    # Models
    "AgentCard",
    "A2ACapability",
    "A2AEndpoint",
    "A2AAuthentication",
    "AuthType",

    # Cache Management
    "A2ACacheManager",

    # Card Generation
    "AgentCardGenerator",

    # Discovery Services
    "LocalDiscoveryService",
    "DiscoveryServiceManager",
    "DiscoveryConfig",
    "AgentRegistration",

    # Registry Client
    "A2ARegistryClient",

    # Formation Server
    "A2AServer",
]
