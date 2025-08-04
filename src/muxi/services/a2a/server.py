"""
A2A Formation Server Implementation

This module implements an SDK-compatible A2A server for the entire formation that handles
A2A communication for all agents using the official A2A SDK protocol.

Key features:
- Single server per formation (not per agent)
- Agent routing via /agents/{agent_id}/message
- SDK protocol compliance for cross-formation compatibility
- Backward compatibility with legacy format during migration
- Formation-level configuration (port, security, etc.)
- Integrates with Overlord for agent management
"""

import asyncio
import socket
from contextlib import closing
from typing import Dict, Any, Optional, List, Union
from ...utils.id_generator import generate_nanoid

from fastapi import FastAPI, Path, Request, Body, HTTPException
import uvicorn
from pydantic import BaseModel

# A2A SDK imports
from a2a.types import (
    Message as SDKMessage,
    SendMessageRequest as SDKSendMessageRequest,
    SendMessageResponse as SDKSendMessageResponse,
    Role as SDKRole
)

from .. import observability
from .models_sdk_adapter import ModelsAdapter


# Legacy request/response models for backward compatibility
class LegacyA2AMessageRequest(BaseModel):
    """Legacy A2A message request format"""
    message: str
    message_type: str = "request"
    context: Optional[Dict[str, Any]] = None
    message_id: Optional[str] = None


class LegacyA2AMessageResponse(BaseModel):
    """Legacy A2A message response format"""
    status: str
    response: Optional[str] = None
    message_id: Optional[str] = None
    agent_id: str
    error: Optional[str] = None


class A2AServer:
    """
    SDK-compatible A2A HTTP server for an entire formation.

    This server handles both SDK protocol messages and legacy format
    for backward compatibility during migration.
    """

    def __init__(
        self,
        overlord,
        port: int = 8181,
        host: str = "0.0.0.0",
        trusted_endpoints: Optional[List[str]] = None,
        auth_mode: str = "none",
        formation_name: str = "default",
    ):
        """
        Initialize the SDK-compatible A2A Formation Server.

        Args:
            overlord: Reference to the Overlord managing agents
            port: Port to bind the server to
            host: Host address to bind to
            trusted_endpoints: List of trusted endpoint addresses for security
            auth_mode: Authentication mode ("none", "api_key", "bearer", etc.)
            formation_name: Name of the formation this server serves
        """
        try:
            self.overlord = overlord
            self.port = port
            self.host = host
            self.trusted_endpoints = trusted_endpoints or []
            self.auth_mode = auth_mode
            self.formation_name = formation_name

            # Server state
            self.app: Optional[FastAPI] = None
            self.server_task: Optional[asyncio.Task] = None
            self.is_running = False

            # Initialize authentication
            from .inbound_auth import A2AInboundAuthenticator

            # Pass SecretsManager from overlord if available
            secrets_manager = getattr(overlord, "secrets_manager", None)
            self.authenticator = A2AInboundAuthenticator(auth_mode, secrets_manager)

            # Initialize FastAPI app
            self._create_app()

            # Emit A2A formation server initialization event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation_name": formation_name,
                    "port": port,
                    "host": self.host,
                    "auth_mode": self.auth_mode,
                    "sdk_enabled": True
                },
                description=f"Initialized SDK-compatible A2A Formation Server for '{formation_name}' on port {port}",
            )

        except Exception as e:
            # Emit error event for initialization failure
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_FAILED,
                level=observability.EventLevel.ERROR,
                data={"formation_name": formation_name, "port": port, "error": str(e)},
                description=f"Failed to initialize SDK A2A Formation Server: {str(e)}",
            )
            raise

    def _create_app(self) -> None:
        """Create the FastAPI application with SDK-compatible A2A endpoints"""
        try:
            self.app = FastAPI(
                title=f"A2A Formation Server (SDK) - {self.formation_name}",
                description="SDK-compatible A2A server with agent routing",
                version="2.0.0",
                docs_url=(
                    "/docs" if self.auth_mode == "none" else None
                ),  # Disable docs if authenticated
            )

            # Health check endpoint
            @self.app.get("/health")
            async def health_check():
                """Health check endpoint for the A2A server"""
                try:
                    return {
                        "status": "healthy",
                        "formation": self.formation_name,
                        "agents": (list(self.overlord.agents.keys()) if self.overlord else []),
                        "sdk_version": "0.3.0",
                        "protocol": "a2a-sdk"
                    }
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))

            # Formation info endpoint
            @self.app.get("/info")
            async def formation_info():
                """Get information about the formation and available agents"""
                try:
                    agents_info = {}
                    if self.overlord:
                        for agent_id, agent in self.overlord.agents.items():
                            # Only include agents with external A2A enabled
                            if getattr(agent, "a2a_external", True):
                                agents_info[agent_id] = {
                                    "description": self.overlord.agent_descriptions.get(
                                        agent_id, ""
                                    ),
                                    "capabilities": getattr(agent, "capabilities", []),
                                    "endpoint": f"/agents/{agent_id}/message",
                                }

                    return {
                        "formation": self.formation_name,
                        "server_mode": self.auth_mode,
                        "agents": agents_info,
                        "total_agents": len(agents_info),
                        "sdk_enabled": True,
                        "protocol_version": "a2a-sdk-0.3.0"
                    }
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))

            # Agent discovery endpoint (A2A standard)
            @self.app.get("/agents")
            async def list_agents():
                """List all agents available for A2A communication"""
                try:
                    agent_cards = []
                    if self.overlord:
                        for agent_id, agent in self.overlord.agents.items():
                            # Only include agents with external A2A enabled
                            if getattr(agent, "a2a_external", True):
                                agent_cards.append(self._create_agent_card(agent_id, agent))

                    return {"agents": agent_cards, "formation": self.formation_name}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))

            # Main SDK A2A message endpoint for specific agents
            @self.app.post("/agents/{agent_id}/message")
            async def handle_agent_message(
                http_request: Request,
                agent_id: str = Path(..., description="ID of the target agent"),
                body: Dict = Body(...)  # Accept any JSON body
            ):
                """
                Handle A2A message for a specific agent.

                Accepts both SDK SendMessageRequest format and legacy format.
                """
                # Try to detect the message format
                if "message" in body and isinstance(body.get("message"), dict):
                    # Looks like SDK format with nested message object
                    if "role" in body["message"] and "parts" in body["message"]:
                        # SDK format confirmed
                        return await self._handle_sdk_message(agent_id, body, http_request)

                # Otherwise treat as legacy format
                try:
                    legacy_request = LegacyA2AMessageRequest(**body)
                    return await self._handle_legacy_message(agent_id, legacy_request, http_request)
                except Exception:
                    # If legacy parsing fails, try SDK format
                    return await self._handle_sdk_message(agent_id, body, http_request)

            # SDK-specific endpoint (explicit SDK format)
            @self.app.post("/agents/{agent_id}/sdk/message")
            async def handle_sdk_agent_message(
                http_request: Request,
                agent_id: str = Path(..., description="ID of the target agent"),
                request: Dict = Body(...)
            ):
                """
                Handle SDK-formatted A2A message for a specific agent.
                """
                return await self._handle_sdk_message(agent_id, request, http_request)

            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "endpoints_created": 6,
                    "auth_mode": self.auth_mode,
                    "sdk_enabled": True
                },
                description="SDK A2A Formation Server FastAPI app created",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to create SDK A2A Formation Server app: {str(e)}",
            )
            raise

    async def _handle_sdk_message(
        self, agent_id: str, request_data: Dict, http_request: Optional[Request] = None
    ) -> Dict[str, Any]:
        """
        Handle incoming SDK-formatted A2A message.
        """
        # Generate unique message ID
        message_id = f"msg_{generate_nanoid()}"

        try:
            # Parse SDK message from request
            sdk_message = None
            if "message" in request_data and isinstance(request_data["message"], dict):
                # Extract the SDK message
                sdk_message_data = request_data["message"]

                # The SDK message should have role and parts
                if "role" in sdk_message_data and "parts" in sdk_message_data:
                    # Convert to MUXI format for agent processing
                    muxi_message = ModelsAdapter.sdk_to_muxi_message(sdk_message_data)

                    # Extract the actual message content
                    message_content = ""
                    context = {}

                    if "parts" in muxi_message:
                        for part in muxi_message["parts"]:
                            if part.get("type") == "TextPart":
                                message_content += part.get("text", "")
                            elif part.get("type") == "DataPart":
                                context.update(part.get("data", {}))

                    # Add metadata as context
                    if "metadata" in muxi_message:
                        context.update(muxi_message["metadata"])
                else:
                    # Not a valid SDK message structure
                    raise ValueError("Invalid SDK message structure")
            else:
                # Try to extract message directly
                message_content = request_data.get("message", "")
                context = request_data.get("context", {})

            # Authenticate if needed
            if http_request and self.auth_mode != "none":
                authenticated, client_id, auth_error = (
                    await self.authenticator.authenticate_request(http_request)
                )
                if not authenticated:
                    return {
                        "status": "error",
                        "error": f"Authentication failed: {auth_error}",
                        "message_id": message_id,
                    }

            # Check if agent exists
            if not self.overlord or agent_id not in self.overlord.agents:
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not found",
                    "message_id": message_id,
                }

            # Get the target agent
            agent = self.overlord.agents[agent_id]

            # Check if agent accepts external A2A messages
            if not getattr(agent, "a2a_external", True):
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not configured for external A2A",
                    "message_id": message_id,
                }

            # Route message to the agent
            response = await agent.handle_a2a_message(
                source_agent_id="external",
                message=message_content,
                message_type="request",
                context=context,
                message_id=message_id,
            )

            # Convert response to SDK format
            if response:
                response_content = (
                    response.get("response") if isinstance(response, dict) else str(response)
                )

                # Create SDK response message
                response_message = ModelsAdapter.muxi_to_sdk_message(
                    response_content,
                    message_id=f"resp_{message_id}",
                    role=SDKRole.agent,
                    context={"agent_id": agent_id}
                )

                # Return SDK-formatted response
                return {
                    "status": "success",
                    "message": response_message.model_dump() if hasattr(response_message, 'model_dump') else response_message,
                    "agent_id": agent_id,
                    "message_id": message_id,
                }
            else:
                return {
                    "status": "success",
                    "message": "Message delivered successfully",
                    "agent_id": agent_id,
                    "message_id": message_id,
                }

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "sdk_format": True
                },
                description=f"SDK A2A message handling failed: {str(e)}",
            )
            return {
                "status": "error",
                "error": f"Message handling failed: {str(e)}",
                "message_id": message_id,
            }

    async def _handle_legacy_message(
        self, agent_id: str, request: LegacyA2AMessageRequest, http_request: Optional[Request] = None
    ) -> LegacyA2AMessageResponse:
        """
        Handle incoming legacy-formatted A2A message for backward compatibility.
        """
        # Generate unique message ID
        message_id = request.message_id or f"msg_{generate_nanoid()}"

        try:
            # Authenticate if needed
            if http_request and self.auth_mode != "none":
                authenticated, client_id, auth_error = (
                    await self.authenticator.authenticate_request(http_request)
                )
                if not authenticated:
                    return LegacyA2AMessageResponse(
                        status="error",
                        error=f"Authentication failed: {auth_error}",
                        message_id=message_id,
                        agent_id=agent_id
                    )

            # Check if agent exists
            if not self.overlord or agent_id not in self.overlord.agents:
                return LegacyA2AMessageResponse(
                    status="error",
                    error=f"Agent {agent_id} not found",
                    message_id=message_id,
                    agent_id=agent_id
                )

            # Get the target agent
            agent = self.overlord.agents[agent_id]

            # Check if agent accepts external A2A messages
            if not getattr(agent, "a2a_external", True):
                return LegacyA2AMessageResponse(
                    status="error",
                    error=f"Agent {agent_id} not configured for external A2A",
                    message_id=message_id,
                    agent_id=agent_id
                )

            # Route message to the agent
            response = await agent.handle_a2a_message(
                source_agent_id="external",
                message=request.message,
                message_type=request.message_type,
                context=request.context,
                message_id=message_id,
            )

            # Return legacy response
            if response:
                response_content = (
                    response.get("response") if isinstance(response, dict) else str(response)
                )
                return LegacyA2AMessageResponse(
                    status="success",
                    response=response_content,
                    agent_id=agent_id,
                    message_id=message_id
                )
            else:
                return LegacyA2AMessageResponse(
                    status="success",
                    response="Message delivered successfully",
                    agent_id=agent_id,
                    message_id=message_id
                )

        except Exception as e:
            return LegacyA2AMessageResponse(
                status="error",
                error=f"Message handling failed: {str(e)}",
                message_id=message_id,
                agent_id=agent_id
            )

    def _create_agent_card(self, agent_id: str, agent: Any) -> Dict[str, Any]:
        """Create an agent card for discovery responses"""
        return {
            "agent_id": agent_id,
            "name": getattr(agent, "name", agent_id),
            "description": self.overlord.agent_descriptions.get(agent_id, ""),
            "capabilities": getattr(agent, "capabilities", []),
            "endpoint": f"/agents/{agent_id}/message",
            "protocol": "a2a-sdk",
            "accepts": ["sdk", "legacy"]
        }

    async def start(self) -> None:
        """Start the A2A Formation Server"""
        try:
            if self.is_running:
                return

            # Check if port is available
            if not self._is_port_available(self.port):
                raise RuntimeError(f"Port {self.port} is already in use")

            # Create server configuration
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=False,  # Disable access logs for cleaner output
            )

            # Create server
            server = uvicorn.Server(config)

            # Start server in background task
            self.server_task = asyncio.create_task(server.serve())
            self.is_running = True

            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "host": self.host,
                    "port": self.port,
                    "auth_mode": self.auth_mode,
                    "sdk_enabled": True
                },
                description=f"SDK A2A Formation Server started on {self.host}:{self.port}",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to start SDK A2A Formation Server: {str(e)}",
            )
            raise

    async def stop(self) -> None:
        """Stop the A2A Formation Server"""
        try:
            if not self.is_running:
                return

            # Cancel server task
            if self.server_task:
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass

            self.is_running = False

            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STOPPED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "sdk_enabled": True
                },
                description="SDK A2A Formation Server stopped",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Error stopping SDK A2A Formation Server: {str(e)}",
            )

    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available for binding"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            try:
                sock.bind((self.host, port))
                return True
            except OSError:
                return False
