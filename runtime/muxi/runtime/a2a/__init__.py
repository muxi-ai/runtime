"""
A2A (Agent-to-Agent) Communication Module

This module provides comprehensive A2A communication capabilities for MUXI agents,
including agent cards, registry client, and the centralized formation server.

Note: Individual agent servers (A2AAgentServer, A2AServerManager) have been
deprecated in favor of the centralized A2AFormationServer architecture.
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
from .formation_server import A2AFormationServer

# Deprecated imports - will be removed in next major version
# Use A2AFormationServer instead of individual agent servers
try:
    from .server import A2AAgentServer, A2AServerManager, MUXIAgentExecutor
    import warnings
    warnings.warn(
        "A2AAgentServer and A2AServerManager are deprecated. "
        "Use A2AFormationServer for centralized A2A communication.",
        DeprecationWarning,
        stacklevel=2
    )
except ImportError:
    # If server.py is removed, gracefully handle the import
    A2AAgentServer = None
    A2AServerManager = None
    MUXIAgentExecutor = None

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

    # Formation Server (RECOMMENDED)
    "A2AFormationServer",

    # Deprecated - use A2AFormationServer instead
    "A2AAgentServer",  # DEPRECATED
    "A2AServerManager",  # DEPRECATED
    "MUXIAgentExecutor",  # DEPRECATED
]
