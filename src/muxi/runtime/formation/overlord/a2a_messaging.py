"""
Unified A2A Messaging using a2a-sdk 1.0 ClientFactory.

Both internal (agent://) and external (http://) transports terminate at
a single `send_a2a_message` entry point. Internal traffic is dispatched
directly through the registered `AgentTransport`; external traffic goes
through `a2a.client.create_client` which handles card resolution,
interceptor wiring, and HTTP transport for us.

Key 1.0 API shifts:
  * `a2a.client.A2AClient` is gone. External calls go through
    `create_client(url)` which returns an async `Client`.
  * `Client.send_message` now yields `StreamResponse` entries; we await
    the first one for non-streaming callers.
  * `MessageSendParams` is gone. Callers build `SendMessageRequest`
    directly with `message`, `metadata`, `configuration`, `tenant`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from a2a.client import ClientCallContext
from a2a.types import Message, SendMessageRequest

from ...services.a2a import _sdk_helpers as sdk
from ...services.a2a.identifiers import get_service_identifier
from ...utils.id_generator import generate_nanoid


class UnifiedA2AMessaging:
    """Unified A2A messaging using ClientFactory."""

    def __init__(self, overlord):
        """Initialize with overlord instance that has ClientFactory."""
        self.overlord = overlord
        self._last_was_external: bool = False

    @staticmethod
    def _match_outbound_service(
        service: Dict[str, Any],
        target_agent_url: str,
    ) -> Optional[tuple[int, int, str]]:
        credential_id = get_service_identifier(service)
        if credential_id is None:
            return None

        target = urlparse(target_agent_url)
        target_host = target.hostname
        try:
            target_port = target.port or (443 if target.scheme == "https" else 80)
        except ValueError:
            return None
        path_parts = target.path.strip("/").split("/")
        target_agent_id = (
            path_parts[1]
            if len(path_parts) >= 3 and path_parts[0] == "agents" and path_parts[2] == "message"
            else None
        )

        selector = service.get("service_id")
        if not isinstance(selector, str) or not selector.strip():
            selector = credential_id if "url" not in service else None
        if selector:
            selector = selector.strip()
            if (
                target_agent_id
                and target_host
                and selector == f"{target_agent_id}@{target_host}:{target_port}"
            ):
                return 0, 0, credential_id
            if target_host and selector == f"{target_host}:{target_port}":
                return 2, 0, credential_id
            if (
                target_host in ("localhost", "127.0.0.1", "0.0.0.0")
                and selector == f"localhost:{target_port}"
            ):
                return 2, 0, credential_id
            if target_host and selector == target_host:
                return 3, 0, credential_id
            if selector == str(target_port):
                return 4, 0, credential_id

        configured_url = service.get("url")
        if not isinstance(configured_url, str) or not configured_url.strip():
            return None
        configured = urlparse(configured_url)
        try:
            configured_port = configured.port or (443 if configured.scheme == "https" else 80)
        except ValueError:
            return None
        if (
            configured.scheme != target.scheme
            or configured.hostname != target_host
            or configured_port != target_port
        ):
            return None

        configured_path = configured.path.rstrip("/")
        if configured_path and not (
            target.path == configured_path or target.path.startswith(f"{configured_path}/")
        ):
            return None
        return 1, -len(configured_path), credential_id

    async def send_a2a_message(
        self,
        source_agent_id: str,
        target_agent_url: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send an A2A message to a peer (internal or external)."""
        if not self.overlord.client_factory:
            raise RuntimeError("A2A ClientFactory not initialized")

        # Resolve timeout from coordinator config if not explicit.
        if timeout is None:
            if hasattr(self.overlord, "a2a_coordinator") and self.overlord.a2a_coordinator:
                a2a_config = self.overlord.a2a_coordinator.config
                timeout = a2a_config.default_timeout_seconds if a2a_config else 30
            else:
                timeout = 30

        # Build the protobuf Message body.
        a2a_message = self._convert_to_a2a_message(message, source_agent_id, context)

        # Wrap metadata (context + framing) in a Struct for the request.
        request_metadata = {
            "source_agent_id": source_agent_id,
            "message_type": message_type,
            **(context or {}),
        }
        request = SendMessageRequest(
            message=a2a_message,
            metadata=sdk.dict_to_struct(request_metadata),
        )

        result_message: Optional[Message] = None

        if target_agent_url.startswith("agent://"):
            # -----------------------------------------------------------
            # Internal transport: hand the request straight to AgentTransport.
            # -----------------------------------------------------------
            self._last_was_external = False
            agent_transport = self._get_agent_transport()
            if agent_transport is None:
                raise RuntimeError("AgentTransport not registered in ClientFactory")

            call_context = ClientCallContext()
            call_context.state["url"] = target_agent_url
            call_context.state["message_id"] = a2a_message.message_id

            response = await agent_transport.send_message(request, context=call_context)
            result_message = getattr(response, "message", None) if response else None
        else:
            # -----------------------------------------------------------
            # External transport: use create_client + stream-aware send.
            # -----------------------------------------------------------
            self._last_was_external = True
            result_message = await self._send_external_message(
                target_agent_url, request, timeout=timeout
            )

        if wait_for_response and result_message is not None:
            return self._convert_from_a2a_message(result_message)
        return None

    # ------------------------------------------------------------------
    # External transport helpers
    # ------------------------------------------------------------------

    def _get_agent_transport(self):
        # The overlord keeps a direct reference to the singleton AgentTransport;
        # fall back to ClientFactory's producer registry if that's missing.
        direct = getattr(self.overlord, "agent_transport", None)
        if direct is not None:
            return direct
        registry = getattr(self.overlord.client_factory, "_registry", None)
        if not registry:
            return None
        producer = registry.get("agent")
        if producer is None:
            return None
        # In 1.0 the registry holds producers (callables); invoke with dummy
        # args to materialize the transport. The agent producer ignores them.
        try:
            return producer(None, "agent://", None)
        except Exception:
            return None

    async def _send_external_message(
        self, target_agent_url: str, request: SendMessageRequest, timeout: int
    ) -> Optional[Message]:
        """Send an HTTP A2A message via the 1.0 create_client API with retries."""
        from a2a.client import create_client

        retry_attempts = 3
        if hasattr(self.overlord, "a2a_coordinator") and self.overlord.a2a_coordinator:
            a2a_config = self.overlord.a2a_coordinator.config
            retry_attempts = a2a_config.default_retry_attempts if a2a_config else 3

        # Resolve any per-service auth headers configured on the overlord.
        auth_headers = await self._resolve_outbound_auth_headers(target_agent_url)

        last_error: Optional[BaseException] = None
        for attempt in range(retry_attempts):
            client = None
            try:
                resolver_kwargs: Dict[str, Any] = {"timeout": float(timeout or 60)}
                if auth_headers:
                    resolver_kwargs["headers"] = auth_headers
                client = await create_client(
                    target_agent_url,
                    resolver_http_kwargs=resolver_kwargs,
                )
                async for stream_response in client.send_message(request):
                    # First payload wins for non-streaming callers.
                    payload = stream_response.WhichOneof("payload")
                    if payload == "message":
                        return stream_response.message
                    if payload == "task" and stream_response.task.history:
                        # Some implementations surface the reply inside the task history.
                        return stream_response.task.history[-1]
                return None
            except Exception as e:  # noqa: BLE001 — retried explicitly
                last_error = e
                if attempt < retry_attempts - 1:
                    await asyncio.sleep((2**attempt) * 0.5)
                else:
                    raise
            finally:
                if client is not None:
                    try:
                        await client.close()
                    except Exception:
                        pass

        if last_error is not None:
            raise last_error
        return None

    async def _resolve_outbound_auth_headers(self, target_agent_url: str) -> Dict[str, str]:
        """Look up per-service auth headers for an external target URL."""
        if not (
            hasattr(self.overlord, "secrets_manager")
            and self.overlord.secrets_manager
            and hasattr(self.overlord, "formation_config")
        ):
            return {}

        # Lazily build the outbound auth manager.
        if not hasattr(self.overlord, "_a2a_auth_manager"):
            from ...services.a2a.auth.outbound import get_auth_manager

            self.overlord._a2a_auth_manager = get_auth_manager(self.overlord.secrets_manager)
            await self.overlord._a2a_auth_manager.load_credentials_from_formation_config(
                self.overlord.formation_config
            )

        auth_manager = self.overlord._a2a_auth_manager
        outbound_services = (
            (self.overlord.formation_config or {})
            .get("a2a", {})
            .get("outbound", {})
            .get("services", [])
        )

        matches = []
        for service in outbound_services:
            match = self._match_outbound_service(service, target_agent_url)
            if match is not None:
                matches.append(match)

        if not matches:
            return {}
        matches.sort()
        success, headers = await auth_manager.apply_sdk_authentication(
            matches[0][2], {}, required=False
        )
        return headers if success else {}

    # ------------------------------------------------------------------
    # MUXI <-> SDK conversion
    # ------------------------------------------------------------------

    def _convert_to_a2a_message(
        self,
        message: Union[str, Dict[str, Any]],
        source_agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Convert a MUXI-level message (string or parts dict) to an SDK Message."""
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

    def _convert_from_a2a_message(self, message: Message) -> Dict[str, Any]:
        """Convert an SDK Message back to MUXI dict format."""
        is_external_response = getattr(self, "_last_was_external", False)

        if is_external_response:
            response_text = ""
            response_data = None

            for part in message.parts:
                kind = sdk.part_kind(part)
                if kind == "text":
                    response_text += sdk.part_text(part) or ""
                elif kind == "data":
                    response_data = sdk.part_data(part)

            if response_data and isinstance(response_data, dict):
                if "status" in response_data and "response" in response_data:
                    return response_data
                return {
                    "status": "success",
                    "response": response_data,
                    "execution_completed": True,
                }
            if response_text:
                return {
                    "status": "success",
                    "response": response_text,
                    "execution_completed": True,
                }
            return {"status": "error", "response": "Empty response received"}

        return {
            "parts": sdk.parts_to_muxi_list(message.parts),
            "message_id": message.message_id,
            "metadata": sdk.message_metadata(message),
        }
