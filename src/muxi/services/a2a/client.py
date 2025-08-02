"""
A2A SDK Client Wrapper

This module provides the SDK client wrapper that handles all A2A protocol details
using the official A2A SDK v0.3.0.
"""

import asyncio
from typing import Optional, Dict, Any, Union
from nanoid import generate as generate_nanoid

from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    SendMessageResponse,
    Message,
    TextPart,
    DataPart,
    Role,
)

import logging

from .. import observability


logger = logging.getLogger(__name__)


# Singleton instance
_a2a_service_instance = None


class A2AService:
    """A2A Service Layer using SDK.

    This service provides the abstraction between agents and the A2A SDK,
    handling all protocol details and format conversions.
    """

    def __new__(cls):
        """Ensure singleton instance."""
        global _a2a_service_instance
        if _a2a_service_instance is None:
            _a2a_service_instance = super(A2AService, cls).__new__(cls)
            _a2a_service_instance._initialized = False
        return _a2a_service_instance

    def __init__(self):
        """Initialize the A2A service with SDK client."""
        if self._initialized:
            return

        self.sdk_client = None
        self._internal_handlers = {}
        self._initialized = True

    async def initialize(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the SDK client with configuration.

        Args:
            config: Optional configuration for SDK client
        """
        try:
            # Initialize SDK client
            client_config = config or {}
            self.sdk_client = A2AClient(**client_config)
            logger.info("A2A SDK client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize A2A SDK client: {e}")
            raise

    async def send_message(
        self,
        source_agent_id: str,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """Send an A2A message using the SDK.

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
        start_time = asyncio.get_event_loop().time()

        try:
            # Convert MUXI format to SDK format
            sdk_message = self._convert_to_sdk_message(
                message, source_agent_id, context
            )

            # Check if internal or external routing
            if self._is_internal(target_agent_id):
                logger.debug(f"Routing internally to {target_agent_id}")
                return await self._send_internal(
                    source_agent_id,
                    target_agent_id,
                    sdk_message,
                    message_type,
                    wait_for_response,
                    timeout,
                )

            # For external agents, check if SDK is initialized
            logger.debug(f"External agent {target_agent_id} requested")

            if not self.sdk_client:
                # Fall back to direct internal routing if agent can be found
                handler = await self._try_find_handler(target_agent_id)
                if handler:
                    logger.debug(f"Found internal handler for {target_agent_id}")
                    return await self._send_internal(
                        source_agent_id,
                        target_agent_id,
                        sdk_message,
                        message_type,
                        wait_for_response,
                        timeout,
                    )
                raise RuntimeError("A2A SDK client not initialized for external routing")

            from a2a.types import MessageSendParams

            params = MessageSendParams(
                message=sdk_message,
                metadata={"target_agent_id": target_agent_id},
            )

            request = SendMessageRequest(
                id=generate_nanoid(),
                params=params,
            )

            response: SendMessageResponse = await self.sdk_client.send_message(request)

            # Track metrics
            duration = asyncio.get_event_loop().time() - start_time
            observability.observe(
                event_type="a2a_message_sent",
                level=observability.EventLevel.INFO,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": target_agent_id,
                    "message_type": message_type,
                    "duration": duration,
                    "success": True,
                },
            )

            if wait_for_response and hasattr(response.root, 'result'):
                # Convert SDK response back to MUXI format
                return self._convert_from_sdk_message(response.root.result)

            return None

        except Exception as e:
            logger.error(f"Error sending A2A message: {e}")

            # Track error metrics
            duration = asyncio.get_event_loop().time() - start_time
            observability.observe(
                event_type="a2a_message_error",
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": target_agent_id,
                    "message_type": message_type,
                    "duration": duration,
                    "error": str(e),
                },
            )

            raise

    async def handle_message(
        self,
        agent,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle an incoming A2A message.

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
        try:
            # Delegate to agent's existing handler
            return await agent._handle_generic_a2a_message(
                source_agent_id,
                message,
                message_type,
                context,
                message_id,
            )
        except Exception as e:
            logger.error(f"Error handling A2A message: {e}")
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to handle A2A message",
            }

    def _convert_to_sdk_message(
        self,
        message: Union[str, Dict[str, Any]],
        source_agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Convert MUXI message format to SDK Message format.

        Args:
            message: MUXI format message
            source_agent_id: ID of the sending agent
            context: Optional context data

        Returns:
            SDK Message object
        """
        parts = []

        # Handle different message formats
        if isinstance(message, str):
            # Simple text message
            parts.append(TextPart(text=message, kind="text"))
        elif isinstance(message, dict):
            # Check if it's already in parts format
            if "parts" in message:
                for part in message["parts"]:
                    if part["type"] == "TextPart":
                        parts.append(TextPart(text=part["text"], kind="text"))
                    elif part["type"] == "DataPart":
                        parts.append(DataPart(data=part["data"], kind="data"))
            else:
                # Convert dict to data part
                parts.append(DataPart(data=message, kind="data"))

        # Create SDK Message
        return Message(
            message_id=generate_nanoid(),
            role=Role.user,
            parts=parts,
            metadata=context or {},
            kind="message",
        )

    def _convert_from_sdk_message(self, sdk_message: Message) -> Dict[str, Any]:
        """Convert SDK Message to MUXI format.

        Args:
            sdk_message: SDK Message object

        Returns:
            MUXI format message dict
        """
        parts = []

        for part in sdk_message.parts:
            # SDK parts need to be dumped to access their fields
            part_data = part.model_dump()
            if part_data.get("kind") == "text":
                parts.append({"type": "TextPart", "text": part_data.get("text")})
            elif part_data.get("kind") == "data":
                parts.append({"type": "DataPart", "data": part_data.get("data")})

        return {
            "parts": parts,
            "message_id": sdk_message.message_id,
            "metadata": sdk_message.metadata,
        }

    def _is_internal(self, target_agent_id: str) -> bool:
        """Check if target agent is internal (same formation).

        Args:
            target_agent_id: ID of the target agent

        Returns:
            True if agent is internal, False otherwise
        """
        # Check if we have a handler registered for this agent
        return target_agent_id in self._internal_handlers

    async def _send_internal(
        self,
        source_agent_id: str,
        target_agent_id: str,
        sdk_message: Message,
        message_type: str,
        wait_for_response: bool,
        timeout: int,
    ) -> Optional[Dict[str, Any]]:
        """Send message to internal agent.

        Args:
            source_agent_id: ID of the sending agent
            target_agent_id: ID of the target agent
            sdk_message: SDK Message object
            message_type: Type of message
            wait_for_response: Whether to wait for response
            timeout: Timeout in seconds

        Returns:
            Response if wait_for_response is True, None otherwise
        """
        handler = self._internal_handlers.get(target_agent_id)
        if not handler:
            raise ValueError(f"No handler registered for agent {target_agent_id}")

        # Convert SDK message back to MUXI format for internal handling
        muxi_message = self._convert_from_sdk_message(sdk_message)

        # Call the handler
        response = await handler(
            source_agent_id,
            muxi_message,
            message_type,
            sdk_message.metadata,
            sdk_message.message_id,
        )

        return response if wait_for_response else None

    def register_internal_handler(self, agent_id: str, handler):
        """Register an internal message handler for an agent.

        Args:
            agent_id: ID of the agent
            handler: Async function to handle messages
        """
        self._internal_handlers[agent_id] = handler
        logger.debug(f"Registered internal handler for agent {agent_id}")

    async def _try_find_handler(self, agent_id: str):
        """Try to find a handler for an agent (used for fallback routing).

        Args:
            agent_id: ID of the agent

        Returns:
            Handler function if found, None otherwise
        """
        # First check if already registered
        if agent_id in self._internal_handlers:
            return self._internal_handlers[agent_id]

        # Could add more discovery logic here if needed
        return None
