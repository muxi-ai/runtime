"""
Agent Transport for A2A Protocol

Direct in-memory transport for agent-to-agent communication within a formation.
This transport bypasses HTTP and directly calls agent methods while
maintaining full A2A protocol compliance for message format.
"""

from typing import Optional, Union
from a2a.client.transports.base import ClientTransport
from a2a.client.middleware import ClientCallContext
from a2a.types import MessageSendParams, Task, Message


class AgentNotFoundError(Exception):
    """Raised when target agent is not found in formation"""
    pass


class AgentTransport(ClientTransport):
    """
    Direct in-memory transport for agent-to-agent communication within a formation.

    This transport bypasses HTTP and directly calls agent methods while
    maintaining full A2A protocol compliance for message format.
    """

    def __init__(self, overlord):
        """
        Initialize the agent transport with reference to overlord.

        Args:
            overlord: The overlord instance containing all agents
        """
        self.overlord = overlord

    async def send_message(
        self,
        request: MessageSendParams,
        *,
        context: Optional[ClientCallContext] = None
    ) -> Union[Task, Message]:
        """
        Send A2A message directly to an agent in the formation.

        Args:
            request: The A2A SDK MessageSendParams
            context: Client call context containing URL and other info

        Returns:
            Message or Task response from the target agent

        Raises:
            AgentNotFoundError: If target agent is not found
        """
        # Extract URL from context
        if not context:
            raise ValueError("Context is required for agent transport")

        # Try to get URL from context state or attributes
        url = None
        if hasattr(context, 'url'):
            url = context.url
        elif hasattr(context, 'state') and isinstance(context.state, dict):
            url = context.state.get('url')

        if not url:
            raise ValueError("Context with URL is required for agent transport")

        # Extract target agent from the URL (e.g., "agent://researcher")
        target_agent_id = self._extract_agent_id(url)
        target_agent = self.overlord.agents.get(target_agent_id)

        if not target_agent:
            raise AgentNotFoundError(f"Agent {target_agent_id} not found in formation")

        # Check if agent has handle_a2a_message method
        if not hasattr(target_agent, "handle_a2a_message"):
            raise AttributeError(f"Agent {target_agent_id} does not support A2A messaging")

        # Extract source agent ID from metadata
        source_agent_id = request.metadata.get("source_agent_id", "unknown") if request.metadata else "unknown"

        # Message is already in A2A protocol format
        # Call the agent directly (in-memory)
        response = await target_agent.handle_a2a_message(
            source_agent_id=source_agent_id,
            message=request.message,
            message_type="request"
        )

        # Convert response to Message if it's a dict
        if isinstance(response, dict):
            # Extract message_id suffix for better readability
            message_suffix = 'unknown'
            if context and hasattr(context, 'state'):
                message_suffix = context.state.get('message_id', 'unknown')

            # Create a Message from the response
            from a2a.types import TextPart, Role
            return Message(
                message_id=f"resp_{target_agent_id}_{message_suffix}",
                role=Role.agent,
                parts=[TextPart(text=str(response), kind="text")],
                metadata=response if isinstance(response, dict) else {},
                kind="message"
            )

        # Return as-is if already a Message or Task
        return response

    def _extract_agent_id(self, url: str) -> str:
        """
        Extract agent ID from agent:// URL.

        Args:
            url: URL in format agent://researcher

        Returns:
            The agent ID (e.g., "researcher")
        """
        # agent://researcher -> researcher
        return url.replace("agent://", "")

    async def close(self) -> None:
        """Close the transport (no-op for in-memory transport)."""
        pass

    # Other required methods from ClientTransport
    async def get_card(self, *args, **kwargs):
        """Get agent card - not applicable for internal agents."""
        # Internal agents don't have agent cards in the A2A sense
        # Their capabilities are managed by the formation
        return None

    async def get_task(self, *args, **kwargs):
        """Get task status - not applicable for synchronous internal calls."""
        # Internal agent calls are synchronous, no task tracking needed
        return None

    async def cancel_task(self, *args, **kwargs):
        """Cancel task - not applicable for synchronous internal calls."""
        # Internal agent calls are synchronous, no cancellation needed
        return None

    async def send_message_streaming(self, *args, **kwargs):
        """Streaming not supported for internal agent calls."""
        # Internal agents communicate via direct method calls
        # Streaming would add unnecessary complexity
        raise NotImplementedError("Streaming not supported for internal agent communication")

    def set_task_callback(self, *args, **kwargs):
        """Task callbacks not applicable for synchronous internal calls."""
        # Internal agent calls are synchronous, no callbacks needed
        pass

    def get_task_callback(self, *args, **kwargs):
        """Task callbacks not applicable for synchronous internal calls."""
        # Internal agent calls are synchronous, no callbacks needed
        return None

    async def resubscribe(self, *args, **kwargs):
        """Resubscription not applicable for internal agents."""
        # Internal agents are always available within the formation
        # No subscription mechanism needed
        return None
