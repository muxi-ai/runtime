"""
Agent Transport for A2A Protocol (a2a-sdk 1.0)

Direct in-memory transport for agent-to-agent communication within a formation.
This transport bypasses HTTP and calls agent methods directly while
maintaining A2A protocol compliance on the wire format.

1.0 API shifts baked into this implementation:
  * `MessageSendParams` is gone — transports receive `SendMessageRequest`.
  * The base `ClientTransport.send_message` returns a single
    `SendMessageResponse` (not an async iterator); streaming lives on
    `send_message_streaming`.
  * `Message.metadata` is a protobuf Struct, read via the helpers module.
"""

from __future__ import annotations

from typing import Optional

from a2a.client import ClientCallContext
from a2a.client.transports.base import ClientTransport
from a2a.types import SendMessageRequest, SendMessageResponse

from . import _sdk_helpers as sdk
from .models_adapter import ModelsAdapter


class AgentNotFoundError(Exception):
    """Raised when target agent is not found in formation"""

    pass


class AgentTransport(ClientTransport):
    """In-memory transport that dispatches to formation-local agents."""

    def __init__(self, overlord):
        self.overlord = overlord

    async def send_message(
        self,
        request: SendMessageRequest,
        *,
        context: Optional[ClientCallContext] = None,
    ) -> SendMessageResponse:
        """Route an A2A message directly to an agent inside the formation."""
        if context is None:
            raise ValueError("Context is required for agent transport")

        url = None
        if hasattr(context, "url"):
            url = context.url
        elif hasattr(context, "state") and isinstance(context.state, dict):
            url = context.state.get("url")
        if not url:
            raise ValueError("Context with URL is required for agent transport")

        target_agent_id = self._extract_agent_id(url)
        target_agent = self.overlord.agents.get(target_agent_id)
        if not target_agent:
            raise AgentNotFoundError(f"Agent {target_agent_id} not found in formation")
        if not hasattr(target_agent, "handle_a2a_message"):
            raise AttributeError(f"Agent {target_agent_id} does not support A2A messaging")

        # Extract source agent id + message type out of the request metadata
        # (protobuf Struct). The external HTTP path (server.py) routes these
        # via a plain dict; the internal in-memory path routes them via Struct,
        # so we normalize to a dict here.
        request_metadata = (
            sdk.struct_to_dict(request.metadata) if request.HasField("metadata") else {}
        )
        source_agent_id = request_metadata.get("source_agent_id", "unknown")
        message_type = request_metadata.get("message_type", "request")

        # Convert the protobuf Message into the MUXI dict shape the agent's
        # handle_a2a_message expects (same shape server.py passes on the
        # external path). Merge any additional metadata from the SDK Message
        # into the handler context, excluding fields already consumed above.
        muxi_message = ModelsAdapter.sdk_to_muxi_message(request.message)
        message_content = muxi_message.get("content", muxi_message)

        handler_context: dict = {}
        if muxi_message.get("metadata"):
            handler_context.update(muxi_message["metadata"])
        for key in ("source_agent_id", "message_type"):
            handler_context.pop(key, None)

        message_id = (
            getattr(request.message, "message_id", None)
            or request_metadata.get("message_id")
            or None
        )

        response = await target_agent.handle_a2a_message(
            source_agent_id=source_agent_id,
            message=message_content,
            message_type=message_type,
            context=handler_context or None,
            message_id=message_id,
        )

        # Build a reply Message from whatever the agent returned.
        reply_id = f"resp_{target_agent_id}_{message_id or 'unknown'}"

        if response is None:
            reply = sdk.make_message(
                message_id=reply_id,
                role=sdk.ROLE_AGENT,
                parts=[sdk.make_text_part("")],
            )
        elif isinstance(response, dict):
            reply = sdk.make_message(
                message_id=reply_id,
                role=sdk.ROLE_AGENT,
                parts=[sdk.make_data_part(response)],
                metadata=response,
            )
        else:
            reply = sdk.make_message(
                message_id=reply_id,
                role=sdk.ROLE_AGENT,
                parts=[sdk.make_text_part(str(response))],
            )

        return SendMessageResponse(message=reply)

    def _extract_agent_id(self, url: str) -> str:
        return url.replace("agent://", "")

    async def close(self) -> None:
        return None

    # -- Optional ClientTransport surface: the internal transport only --
    #    services send_message; the rest are intentional no-ops.

    async def get_card(self, *args, **kwargs):
        return None

    async def get_task(self, *args, **kwargs):
        return None

    async def cancel_task(self, *args, **kwargs):
        return None

    async def send_message_streaming(self, *args, **kwargs):
        raise NotImplementedError("Streaming not supported for internal agent communication")

    async def subscribe(self, *args, **kwargs):
        raise NotImplementedError("Subscribe not supported for internal agent communication")

    async def resubscribe(self, *args, **kwargs):
        return None

    async def get_extended_agent_card(self, *args, **kwargs):
        return None

    async def list_tasks(self, *args, **kwargs):
        return None

    async def create_task_push_notification_config(self, *args, **kwargs):
        return None

    async def delete_task_push_notification_config(self, *args, **kwargs):
        return None

    async def get_task_push_notification_config(self, *args, **kwargs):
        return None

    async def list_task_push_notification_configs(self, *args, **kwargs):
        return None

    def set_task_callback(self, *args, **kwargs):
        pass

    def get_task_callback(self, *args, **kwargs):
        return None
