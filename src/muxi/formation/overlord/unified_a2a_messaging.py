"""
Unified A2A Messaging using ClientFactory

This module provides unified A2A messaging that uses the same protocol
for both internal and external agents, only differing in transport.
"""

from typing import Optional, Dict, Any, Union
from a2a.types import Message, TextPart, DataPart, Role, MessageSendParams
from a2a.client.middleware import ClientCallContext
from ...utils.id_generator import generate_nanoid


class UnifiedA2AMessaging:
    """Unified A2A messaging using ClientFactory."""

    def __init__(self, overlord):
        """Initialize with overlord instance that has ClientFactory."""
        self.overlord = overlord

    async def send_a2a_message(
        self,
        source_agent_id: str,
        target_agent_url: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Send A2A message using unified protocol with appropriate transport.

        Args:
            source_agent_id: ID of the sending agent
            target_agent_url: URL of target agent (agent:// for internal, http:// for external)
            message: Message content (string or dict)
            message_type: Type of message (request, response, etc.)
            context: Optional context data
            wait_for_response: Whether to wait for a response
            timeout: Timeout in seconds

        Returns:
            Response from target agent if wait_for_response is True
        """
        if not self.overlord.client_factory:
            raise RuntimeError("A2A ClientFactory not initialized")

        # Convert message to A2A protocol format
        a2a_message = self._convert_to_a2a_message(
            message, source_agent_id, context
        )

        # Create message send params
        params = MessageSendParams(
            message=a2a_message,
            metadata={
                "source_agent_id": source_agent_id,
                "message_type": message_type,
                **(context or {})
            }
        )

        # Determine transport based on URL scheme
        if target_agent_url.startswith("agent://"):
            # Internal agent - use AgentTransport directly
            if hasattr(self.overlord.client_factory, '_registry'):
                agent_transport = self.overlord.client_factory._registry.get('agent')
                if agent_transport:
                    # Create context for the call
                    call_context = ClientCallContext()
                    call_context.state["url"] = target_agent_url
                    call_context.state["message_id"] = a2a_message.message_id

                    # Send message directly through transport
                    result = await agent_transport.send_message(params, context=call_context)
                else:
                    raise RuntimeError("AgentTransport not registered in ClientFactory")
            else:
                raise RuntimeError("ClientFactory registry not available")
        else:
            # External agent - create client using AgentCard
            # For now, we'll need the full agent card info
            # This will be handled in Phase 4 planning integration
            from a2a.types import AgentCard

            # Create minimal agent card for external agent
            agent_card = AgentCard(
                agent_id=target_agent_url.split('/')[-1],  # Extract ID from URL
                name=target_agent_url.split('/')[-1],
                description="External agent",
                version="1.0.0",
                protocol_version="1.0",
                capabilities={},
                endpoints=[{"url": target_agent_url}],
                preferred_transport="jsonrpc"
            )

            # Create client using agent card
            client = self.overlord.client_factory.create(agent_card)

            # Send message through client
            result = await client.send_message(params)

        if wait_for_response and isinstance(result, Message):
            # Convert A2A message back to dict format
            return self._convert_from_a2a_message(result)

        return None

    def _convert_to_a2a_message(
        self,
        message: Union[str, Dict[str, Any]],
        source_agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Convert to A2A Message format."""
        parts = []

        if isinstance(message, str):
            parts.append(TextPart(text=message, kind="text"))
        elif isinstance(message, dict):
            if "parts" in message:
                # Already in parts format
                for part in message["parts"]:
                    if part.get("type") == "TextPart":
                        parts.append(TextPart(text=part["text"], kind="text"))
                    elif part.get("type") == "DataPart":
                        parts.append(DataPart(data=part["data"], kind="data"))
            else:
                # Convert dict to data part
                parts.append(DataPart(data=message, kind="data"))

        return Message(
            message_id=generate_nanoid(),
            role=Role.user,
            parts=parts,
            metadata=context or {},
            kind="message"
        )

    def _convert_from_a2a_message(self, message: Message) -> Dict[str, Any]:
        """Convert from A2A Message to dict format."""
        parts = []

        for part in message.parts:
            part_data = part.model_dump()
            if part_data.get("kind") == "text":
                parts.append({"type": "TextPart", "text": part_data.get("text")})
            elif part_data.get("kind") == "data":
                parts.append({"type": "DataPart", "data": part_data.get("data")})

        return {
            "parts": parts,
            "message_id": message.message_id,
            "metadata": message.metadata,
        }
