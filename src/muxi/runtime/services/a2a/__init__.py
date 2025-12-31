"""
A2A (Agent-to-Agent) Communication Module

This module provides comprehensive A2A communication capabilities for MUXI agents,
including agent cards, registry client, and the centralized formation server.
"""

from typing import Optional, Dict, Any, Union

from .models import AgentCard, A2ACapability, A2AEndpoint, A2AAuthentication, AuthType
from .cache_manager import A2ACacheManager
from .card_generator import AgentCardGenerator
from .discovery import (
    LocalDiscoveryService,
    DiscoveryServiceManager,
    DiscoveryConfig,
    AgentRegistration,
)
from .registry_client import A2ARegistryClient
from .server import A2AServer


# Public API for agents to use
async def send_message(
    source_agent_id: str,
    target_agent_id: str,
    message: Union[str, Dict[str, Any]],
    message_type: str = "request",
    context: Optional[Dict[str, Any]] = None,
    wait_for_response: bool = True,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    """Send an A2A message via the service layer.

    This is the primary interface for agents to send messages to other agents.
    All A2A protocol details are handled by the service layer.

    Args:
        source_agent_id: ID of the sending agent
        target_agent_id: ID of the target agent
        message: Message content (string or dict)
        message_type: Type of message (request, response, etc.)
        context: Optional context data
        wait_for_response: Whether to wait for a response
        timeout: Timeout in seconds

    Returns:
        Response from target agent if wait_for_response is True, None otherwise
    """
    # Implementation will be added in client.py
    from .client import A2AService
    service = A2AService()
    return await service.send_message(
        source_agent_id=source_agent_id,
        target_agent_id=target_agent_id,
        message=message,
        message_type=message_type,
        context=context,
        wait_for_response=wait_for_response,
        timeout=timeout,
    )


async def handle_message(
    agent,
    source_agent_id: str,
    message: Union[str, Dict[str, Any]],
    message_type: str = "request",
    context: Optional[Dict[str, Any]] = None,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle an incoming A2A message via the service layer.

    This is the primary interface for agents to handle messages from other agents.
    All A2A protocol details are handled by the service layer.

    Args:
        agent: The agent instance handling the message
        source_agent_id: ID of the sending agent
        message: Message content (string or dict)
        message_type: Type of message (request, response, etc.)
        context: Optional context data
        message_id: Optional message ID for tracking

    Returns:
        Response to send back to the source agent
    """
    # Implementation will be added in client.py
    from .client import A2AService
    service = A2AService()
    return await service.handle_message(
        agent=agent,
        source_agent_id=source_agent_id,
        message=message,
        message_type=message_type,
        context=context,
        message_id=message_id,
    )


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
    # Public API Functions
    "send_message",
    "handle_message",
]
