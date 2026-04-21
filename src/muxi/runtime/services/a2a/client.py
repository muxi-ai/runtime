"""
A2A SDK Client Wrapper (a2a-sdk 1.0)

Thin facade over a2a.client.create_client that MUXI agents use when they
need to send A2A messages without going through the overlord's
UnifiedA2AMessaging path. Most production traffic runs through
UnifiedA2AMessaging + the registered AgentTransport in ClientFactory; this
service survives for legacy call sites and for configuration-driven
external registries.

1.0 API shifts:
  * `A2AClient` is gone. We create a fresh `Client` per send via
    `create_client(url)` and close it immediately after.
  * `MessageSendParams` is gone. We pass `message`, `metadata` directly on
    `SendMessageRequest`.
  * `Client.send_message` yields `StreamResponse` values; we consume the
    first `message` payload for the sync-reply contract.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Dict, Optional, Union

from a2a.types import Message, SendMessageRequest

from .. import observability
from . import _sdk_helpers as sdk
from ...utils.id_generator import generate_nanoid

# Singleton instance and lock for thread safety.
_a2a_service_instance = None
_singleton_lock = threading.Lock()


class A2AService:
    """MUXI-facing wrapper around the a2a-sdk 1.0 client surface."""

    def __new__(cls):
        global _a2a_service_instance
        if _a2a_service_instance is None:
            with _singleton_lock:
                if _a2a_service_instance is None:
                    _a2a_service_instance = super(A2AService, cls).__new__(cls)
                    _a2a_service_instance._initialized = False
        return _a2a_service_instance

    def __init__(self):
        if self._initialized:
            return
        self._external_url: Optional[str] = None
        self._internal_handlers: Dict[str, Callable] = {}
        self._initialized = True

    async def initialize(self, config: Optional[Dict[str, Any]] = None):
        """Record the first configured external registry URL, if any."""
        if not config:
            self._external_url = None
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                data={"service": "a2a", "mode": "internal_only"},
                description="A2A service initialized for internal-only communication",
            )
            return

        if config.get("outbound", {}).get("enabled") or config.get("inbound", {}).get("enabled"):
            registries = config.get("outbound", {}).get("registries", [])
            self._external_url = registries[0] if registries else None
            if self._external_url:
                observability.observe(
                    event_type=observability.SystemEvents.A2A_REGISTRY_CLIENT_INITIALIZED,
                    level=observability.EventLevel.INFO,
                    data={"url": self._external_url},
                    description=f"A2A service registered registry URL: {self._external_url}",
                )
        else:
            self._external_url = None

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
        """Send an A2A message. Internal handlers dispatch in-memory; external
        sends go through create_client."""
        start_time = asyncio.get_event_loop().time()

        try:
            sdk_message = self._convert_to_sdk_message(message, source_agent_id, context)

            if self._is_internal(target_agent_id):
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                    level=observability.EventLevel.DEBUG,
                    data={"target_agent_id": target_agent_id, "routing": "internal"},
                    description=f"Routing internally to {target_agent_id}",
                )
                return await self._send_internal(
                    source_agent_id,
                    target_agent_id,
                    sdk_message,
                    message_type,
                    wait_for_response,
                    timeout,
                )

            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                level=observability.EventLevel.DEBUG,
                data={"target_agent_id": target_agent_id, "routing": "external"},
                description=f"External agent {target_agent_id} requested",
            )

            if not self._external_url:
                raise RuntimeError(
                    f"Cannot route to external agent '{target_agent_id}': "
                    "A2A external registry URL not configured"
                )

            result_message = await self._send_external(
                sdk_message,
                target_agent_id=target_agent_id,
                timeout=timeout,
            )

            duration = asyncio.get_event_loop().time() - start_time
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                level=observability.EventLevel.INFO,
                description=(
                    f"A2A message sent from {source_agent_id} to "
                    f"{target_agent_id} ({message_type})"
                ),
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": target_agent_id,
                    "message_type": message_type,
                    "duration": duration,
                    "success": True,
                },
            )

            if wait_for_response and result_message is not None:
                return self._convert_from_sdk_message(result_message)
            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e)},
                description=f"Error sending A2A message: {e}",
            )
            duration = asyncio.get_event_loop().time() - start_time
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                description=(
                    f"A2A message failed from {source_agent_id} to " f"{target_agent_id}: {str(e)}"
                ),
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": target_agent_id,
                    "message_type": message_type,
                    "duration": duration,
                    "error": str(e),
                },
            )
            raise

    async def _send_external(
        self,
        sdk_message: Message,
        *,
        target_agent_id: str,
        timeout: int,
    ) -> Optional[Message]:
        """Send a message to the configured external registry and return the first reply."""
        from a2a.client import create_client

        request = SendMessageRequest(
            message=sdk_message,
            metadata=sdk.dict_to_struct({"target_agent_id": target_agent_id}),
        )

        client = await create_client(
            self._external_url,
            resolver_http_kwargs={"timeout": float(timeout)},
        )
        try:
            async for stream_response in client.send_message(request):
                payload = stream_response.WhichOneof("payload")
                if payload == "message":
                    return stream_response.message
                if payload == "task" and stream_response.task.history:
                    return stream_response.task.history[-1]
        finally:
            try:
                await client.close()
            except Exception:
                pass
        return None

    async def handle_message(
        self,
        agent,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hand an incoming A2A message to the agent's generic handler."""
        try:
            return await agent._handle_generic_a2a_message(
                source_agent_id,
                message,
                message_type,
                context,
                message_id,
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "context": "message_handler"},
                description=f"Error handling A2A message: {e}",
            )
            return {
                "status": "error",
                "error": str(e),
                "message": "Failed to handle A2A message",
            }

    # ------------------------------------------------------------------
    # MUXI <-> SDK conversion
    # ------------------------------------------------------------------

    def _convert_to_sdk_message(
        self,
        message: Union[str, Dict[str, Any]],
        source_agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        parts = []
        if isinstance(message, str):
            parts.append(sdk.make_text_part(message))
        elif isinstance(message, dict):
            if "parts" in message:
                for part in message["parts"]:
                    part_type = (part.get("type") or "").lower()
                    if part_type in ("textpart", "text"):
                        parts.append(sdk.make_text_part(part.get("text", "")))
                    elif part_type in ("datapart", "data"):
                        parts.append(sdk.make_data_part(part.get("data") or {}))
            else:
                parts.append(sdk.make_data_part(message))
        if not parts:
            parts.append(sdk.make_text_part(""))

        return sdk.make_message(
            message_id=generate_nanoid(),
            role=sdk.ROLE_USER,
            parts=parts,
            metadata=context,
        )

    def _convert_from_sdk_message(self, sdk_message: Message) -> Dict[str, Any]:
        return {
            "parts": sdk.parts_to_muxi_list(sdk_message.parts),
            "message_id": sdk_message.message_id,
            "metadata": sdk.message_metadata(sdk_message),
        }

    # ------------------------------------------------------------------
    # Internal handler plumbing
    # ------------------------------------------------------------------

    def _is_internal(self, target_agent_id: str) -> bool:
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
        handler = self._internal_handlers.get(target_agent_id)
        if not handler:
            raise ValueError(f"No handler registered for agent {target_agent_id}")

        muxi_message = self._convert_from_sdk_message(sdk_message)
        response = await handler(
            source_agent_id,
            muxi_message,
            message_type,
            sdk.message_metadata(sdk_message),
            sdk_message.message_id,
        )
        return response if wait_for_response else None

    def register_internal_handler(self, agent_id: str, handler):
        self._internal_handlers[agent_id] = handler
        observability.observe(
            event_type=observability.SystemEvents.A2A_AGENT_REGISTERED,
            level=observability.EventLevel.DEBUG,
            data={"agent_id": agent_id, "type": "internal_handler"},
            description=f"Registered internal handler for agent {agent_id}",
        )

    async def cleanup(self):
        """No persistent resources; retained for API compatibility."""
        self._external_url = None
        observability.observe(
            event_type=observability.SystemEvents.OPERATION_COMPLETED,
            level=observability.EventLevel.DEBUG,
            data={"operation": "a2a_sdk_cleanup"},
            description="A2A service cleanup completed",
        )
