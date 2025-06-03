"""
A2A (Agent-to-Agent) Communication Module

This module provides comprehensive A2A communication capabilities for MUXI agents,
including agent cards, server infrastructure, caching, and discovery services.
"""

from .models import AgentCard, A2ACapability, A2AEndpoint
from .cache_manager import A2ACacheManager
from .card_generator import AgentCardGenerator
from .server import A2AAgentServer, A2AServerManager, MUXIAgentExecutor
from .discovery import (
    LocalDiscoveryService,
    DiscoveryServiceManager,
    DiscoveryConfig,
    AgentRegistration
)

__all__ = [
    # Models
    "AgentCard",
    "A2ACapability",
    "A2AEndpoint",

    # Cache Management
    "A2ACacheManager",

    # Card Generation
    "AgentCardGenerator",

    # Server Infrastructure
    "A2AAgentServer",
    "A2AServerManager",
    "MUXIAgentExecutor",

    # Discovery Services
    "LocalDiscoveryService",
    "DiscoveryServiceManager",
    "DiscoveryConfig",
    "AgentRegistration"
]
