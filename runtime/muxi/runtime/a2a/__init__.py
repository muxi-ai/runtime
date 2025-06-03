"""
MUXI A2A (Agent-to-Agent) Integration Module

This module provides A2A protocol support for MUXI agents, including:
- Agent card generation and caching
- A2A server and client implementations
- Discovery and registry services
- Integration with Google's A2A SDK
"""

__version__ = "1.0.0"

from .card_generator import AgentCardGenerator, AgentCard
from .cache_manager import A2ACacheManager
from .server import A2AAgentServer, A2AServerManager, MUXIAgentExecutor

__all__ = [
    "AgentCardGenerator",
    "AgentCard",
    "A2ACacheManager",
    "A2AAgentServer",
    "A2AServerManager",
    "MUXIAgentExecutor",
]
