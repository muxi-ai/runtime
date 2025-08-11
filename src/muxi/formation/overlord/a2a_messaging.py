"""
Unified A2A Messaging using ClientFactory

This module provides unified A2A messaging that uses the same protocol
for both internal and external agents, only differing in transport.
"""

import asyncio
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
        timeout: Optional[int] = None,
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
            timeout: Timeout in seconds (uses A2A config default if not specified)

        Returns:
            Response from target agent if wait_for_response is True
        """
        if not self.overlord.client_factory:
            raise RuntimeError("A2A ClientFactory not initialized")

        # Get timeout from A2A configuration if not specified
        if timeout is None:
            if hasattr(self.overlord, "a2a_coordinator") and self.overlord.a2a_coordinator:
                a2a_config = self.overlord.a2a_coordinator.config
                timeout = a2a_config.default_timeout_seconds if a2a_config else 30
            else:
                timeout = 30

        # Convert message to A2A protocol format
        a2a_message = self._convert_to_a2a_message(message, source_agent_id, context)

        # Create message send params
        params = MessageSendParams(
            message=a2a_message,
            metadata={
                "source_agent_id": source_agent_id,
                "message_type": message_type,
                **(context or {}),
            },
        )

        # Determine transport based on URL scheme
        if target_agent_url.startswith("agent://"):
            # Internal agent - use AgentTransport directly
            self._last_was_external = False
            if hasattr(self.overlord.client_factory, "_registry"):
                agent_transport = self.overlord.client_factory._registry.get("agent")
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
            # External agent - create client using URL directly
            self._last_was_external = True
            # The ClientFactory should handle HTTP URLs directly
            import httpx
            from a2a.client import A2AClient

            # Get retry configuration from A2A config
            retry_attempts = 3  # default
            if hasattr(self.overlord, "a2a_coordinator") and self.overlord.a2a_coordinator:
                a2a_config = self.overlord.a2a_coordinator.config
                retry_attempts = a2a_config.default_retry_attempts if a2a_config else 3

            # Create HTTP client for external agent with appropriate timeout
            # Use the timeout parameter passed to this method
            timeout_value = float(timeout) if timeout else 60.0

            # Get authentication headers for outbound requests
            auth_headers = {}
            if hasattr(self.overlord, "secrets_manager") and self.overlord.secrets_manager:
                # Get or create auth manager for this overlord
                if not hasattr(self.overlord, "_a2a_auth_manager"):
                    from ...services.a2a.auth.outbound import get_auth_manager

                    self.overlord._a2a_auth_manager = get_auth_manager(
                        self.overlord.secrets_manager
                    )
                    # Load credentials from formation config
                    if hasattr(self.overlord, "formation_config"):
                        await self.overlord._a2a_auth_manager.load_credentials_from_formation_config(
                            self.overlord.formation_config
                        )

                auth_manager = self.overlord._a2a_auth_manager

                # Look for matching outbound service configuration
                outbound_services = (
                    self.overlord.formation_config.get("a2a", {})
                    .get("outbound", {})
                    .get("services", [])
                )

                # Parse target URL to extract components for matching
                from urllib.parse import urlparse

                parsed_url = urlparse(target_agent_url)
                target_host = parsed_url.hostname
                target_port = parsed_url.port

                # Extract agent ID from path if present
                # URL format: http://hostname:port/agents/{agent-id}/message
                target_agent_id = None
                if parsed_url.path:
                    path_parts = parsed_url.path.strip("/").split("/")
                    if (
                        len(path_parts) >= 3
                        and path_parts[0] == "agents"
                        and path_parts[2] == "message"
                    ):
                        target_agent_id = path_parts[1]

                # Try to find matching service configuration with precedence
                target_service_id = None

                # Collect all matches with their precedence
                matches = []

                for service in outbound_services:
                    service_id = service.get("service_id", "")
                    if not service_id:
                        continue

                    # Priority 1: agent-id@hostname:port (most specific)
                    if target_agent_id and target_host and target_port:
                        if service_id == f"{target_agent_id}@{target_host}:{target_port}":
                            matches.append((1, service_id))
                            continue

                    # Priority 2: hostname:port
                    if target_host and target_port:
                        if service_id == f"{target_host}:{target_port}":
                            matches.append((2, service_id))
                            continue

                    # Priority 3: hostname
                    if target_host:
                        if service_id == target_host:
                            matches.append((3, service_id))
                            continue

                    # Priority 4: port (also check localhost:port for localhost targets)
                    if target_port:
                        if service_id == str(target_port):
                            matches.append((4, service_id))
                            continue
                        # Special case for localhost
                        if (
                            target_host in ["localhost", "127.0.0.1", "0.0.0.0"]
                            and service_id == f"localhost:{target_port}"
                        ):
                            matches.append((2, service_id))  # Same priority as hostname:port
                            continue

                # Select the match with highest priority (lowest number)
                if matches:
                    matches.sort(key=lambda x: x[0])
                    target_service_id = matches[0][1]

                # If no matching service_id found, don't use any (no default)
                # This ensures we only apply auth when explicitly configured

                # Apply SDK authentication if we have a service_id
                if target_service_id:
                    # Try SDK authentication first
                    success, updated_headers = await auth_manager.apply_sdk_authentication(
                        target_service_id, auth_headers, required=False
                    )
                    if success:
                        auth_headers = updated_headers

            # Retry logic for external requests
            for attempt in range(retry_attempts):
                try:
                    # Create HTTP client with authentication headers
                    client_headers = auth_headers.copy() if auth_headers else {}

                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(timeout_value), headers=client_headers
                    ) as http_client:
                        client = A2AClient(httpx_client=http_client, url=target_agent_url)

                        # Create request with params
                        from a2a.types import SendMessageRequest
                        import time

                        # The A2A SDK expects params to be a dict with 'message' key
                        # Convert MessageSendParams to dict format
                        params_dict = {"message": params.message.model_dump()}

                        request = SendMessageRequest(
                            id=f"req_{int(time.time() * 1000)}", params=params_dict
                        )

                        if attempt == 0:
                            pass  # First attempt, no retry message
                        else:
                            # Log retry attempt (could add logging here if needed)
                            pass

                        # Send message through client
                        result = await client.send_message(request)

                        # Extract the Message from SendMessageResponse

                        # Try to extract the message from the response
                        if hasattr(result, "result"):
                            # This is a SendMessageResponse, extract the actual message
                            result = result.result
                        elif hasattr(result, "model_dump"):
                            # If it's a pydantic model, get the dict and extract result
                            result_dict = result.model_dump()
                            if "result" in result_dict:
                                # Import Message type to reconstruct it
                                result = Message(**result_dict["result"])

                        # Success - break out of retry loop
                        break

                except Exception:
                    if attempt < retry_attempts - 1:
                        # Wait before retry with exponential backoff
                        wait_time = (2**attempt) * 0.5  # 0.5s, 1s, 2s
                        await asyncio.sleep(wait_time)
                    else:
                        # Last attempt failed, re-raise the error
                        raise

        if wait_for_response:
            if isinstance(result, Message):
                # Convert A2A message back to dict format
                converted = self._convert_from_a2a_message(result)
                return converted
            else:
                return result

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
            kind="message",
        )

    def _convert_from_a2a_message(self, message: Message) -> Dict[str, Any]:
        """Convert from A2A Message to dict format."""
        # Check if this is an external response that needs special handling
        # External responses should be converted to the format expected by agents
        is_external_response = hasattr(self, "_last_was_external") and self._last_was_external

        if is_external_response:
            # Convert to agent-expected format with status and response fields
            response_text = ""
            response_data = None

            for part in message.parts:
                part_data = part.model_dump()
                if part_data.get("kind") == "text":
                    response_text += part_data.get("text", "")
                elif part_data.get("kind") == "data":
                    response_data = part_data.get("data")

            # If we have data, check if it already has the expected format
            if response_data and isinstance(response_data, dict):
                if "status" in response_data and "response" in response_data:
                    # Already in the expected format
                    return response_data
                else:
                    # Wrap in expected format
                    return {
                        "status": "success",
                        "response": response_data,
                        "execution_completed": True,  # External agents complete execution
                    }
            elif response_text:
                # Text response - wrap in expected format
                return {
                    "status": "success",
                    "response": response_text,
                    "execution_completed": True,  # External agents complete execution
                }
            else:
                # Empty response
                return {"status": "error", "response": "Empty response received"}

        # For internal messages, use the standard format
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
