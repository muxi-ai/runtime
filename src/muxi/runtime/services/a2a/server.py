"""
A2A Formation Server Implementation

This module implements a single HTTP server for the entire formation that handles
A2A communication for all agents. Unlike individual agent servers, this provides
centralized A2A serving with agent routing.

Key features:
- Single server per formation (not per agent)
- Agent routing via /agents/{agent_id}/message
- Formation-level configuration (port, security, etc.)
- Integrates with Overlord for agent management
- Follows A2A protocol specification
"""

import asyncio
import socket
from contextlib import closing
from typing import Dict, Any, Optional, List
from ...utils.id_generator import generate_nanoid

from fastapi import FastAPI, Path, Request
import uvicorn
from pydantic import BaseModel

from .. import observability


class A2AMessageRequest(BaseModel):
    """A2A message request format"""

    message: str
    message_type: str = "request"
    context: Optional[Dict[str, Any]] = None
    message_id: Optional[str] = None


class A2AMessageResponse(BaseModel):
    """A2A message response format"""

    status: str
    response: Optional[str] = None
    message_id: Optional[str] = None
    agent_id: str
    error: Optional[str] = None


class A2AServer:
    """
    Single A2A HTTP server for an entire formation.

    This server handles A2A communication for all agents in the formation
    through a unified endpoint structure, replacing individual agent servers.
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
        Initialize the A2A Formation Server.

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
                    "auth_mode": self.auth_mode if self.auth else "none",
                },
                description=f"Initialized A2A Formation Server for '{formation_name}' on port {port}",  # noqa: E501
            )

        except Exception as e:
            # Emit error event for initialization failure
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_FAILED,
                level=observability.EventLevel.ERROR,
                data={"formation_name": formation_name, "port": port, "error": str(e)},
                description=f"Failed to initialize A2A Formation Server: {str(e)}",
            )
            raise

    def _create_app(self) -> None:
        """Create the FastAPI application with A2A endpoints"""
        try:
            self.app = FastAPI(
                title=f"A2A Formation Server - {self.formation_name}",
                description="Single A2A server for entire formation with agent routing",
                version="1.0.0",
                docs_url=(
                    "/docs" if self.auth_mode == "none" else None
                ),  # Disable docs if authenticated
            )

            # Health check endpoint
            @self.app.get("/health")
            async def health_check():
                """Health check endpoint for the A2A server"""
                try:
                    # Emit health check event
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_HEALTH_CHECK_STARTED,
                        level=observability.EventLevel.DEBUG,
                        data={
                            "formation": self.formation_name,
                            "agents_count": (len(self.overlord.agents) if self.overlord else 0),
                        },
                        description="A2A Formation Server health check requested",
                    )

                    return {
                        "status": "healthy",
                        "formation": self.formation_name,
                        "agents": (list(self.overlord.agents.keys()) if self.overlord else []),
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                        level=observability.EventLevel.ERROR,
                        data={"formation": self.formation_name, "error": str(e)},
                        description=f"A2A health check failed: {str(e)}",
                    )
                    raise

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

                    # Emit formation info request event
                    observability.observe(
                        event_type=observability.ConversationEvents.A2A_DISCOVERY_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={
                            "formation": self.formation_name,
                            "agents_count": len(agents_info),
                            "auth_mode": self.auth_mode,
                        },
                        description="A2A Formation info requested",
                    )

                    return {
                        "formation": self.formation_name,
                        "server_mode": self.auth_mode,
                        "agents": agents_info,
                        "total_agents": len(agents_info),
                    }
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                        level=observability.EventLevel.ERROR,
                        data={"formation": self.formation_name, "error": str(e)},
                        description=f"A2A formation info request failed: {str(e)}",
                    )
                    raise

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

                    # Emit agent discovery event
                    observability.observe(
                        event_type=observability.ConversationEvents.A2A_DISCOVERY_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={
                            "formation": self.formation_name,
                            "agents_discovered": len(agent_cards),
                            "agent_ids": [card["agent_id"] for card in agent_cards],
                        },
                        description="A2A agent discovery completed",
                    )

                    return {"agents": agent_cards, "formation": self.formation_name}
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                        level=observability.EventLevel.ERROR,
                        data={"formation": self.formation_name, "error": str(e)},
                        description=f"A2A agent discovery failed: {str(e)}",
                    )
                    raise

            # Main A2A message endpoint for specific agents
            @self.app.post("/agents/{agent_id}/message")
            async def handle_agent_message(
                http_request: Request,
                agent_id: str = Path(..., description="ID of the target agent"),
                request: A2AMessageRequest = ...,
            ) -> A2AMessageResponse:
                """
                Handle A2A message for a specific agent.

                This is the main endpoint that external agents use to communicate
                with agents in this formation.
                """
                return await self._handle_a2a_message(agent_id, request, http_request)

            # Emit app creation event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "endpoints_created": 5,
                    "auth_mode": self.auth_mode,
                },
                description="A2A Formation Server FastAPI app created",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to create A2A Formation Server app: {str(e)}",
            )
            raise

    async def _handle_a2a_message(
        self, agent_id: str, request: A2AMessageRequest, http_request: Optional[Request] = None
    ) -> Dict[str, Any]:
        """
        Handle incoming A2A message by routing directly to the target agent.

        This method routes messages directly to agents without going through
        the overlord's routing mechanism for better performance and cleaner
        separation of concerns.
        """
        # Generate unique message ID
        message_id = f"msg_{generate_nanoid()}"

        try:
            # Emit message received event
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_RECEIVED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": agent_id,
                    "message_id": message_id,
                    "message_type": request.message_type,
                    "formation": self.formation_name,
                    "has_context": request.context is not None,
                },
                description=f"A2A message received for agent {agent_id}",
            )

            # Authenticate the request if authentication is enabled
            if http_request and self.auth_mode != "none":
                authenticated, client_id, auth_error = (
                    await self.authenticator.authenticate_request(http_request)
                )

                if not authenticated:
                    # Emit authentication failure event
                    observability.observe(
                        event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": agent_id,
                            "message_id": message_id,
                            "auth_error": auth_error,
                            "formation": self.formation_name,
                        },
                        description=f"A2A authentication failed for agent {agent_id}",
                    )

                    return {
                        "status": "error",
                        "error": f"Authentication failed: {auth_error}",
                        "message_id": message_id,
                    }

                # Emit successful authentication event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATED,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "client_id": client_id,
                        "formation": self.formation_name,
                    },
                    description=f"A2A authentication successful for agent {agent_id}",
                )

                #  Authentication success event already emitted above

            # Get client host for security validation
            # Note: In a real implementation, this would come from the request headers
            client_host = "127.0.0.1"  # Default for development

            # Validate trusted endpoints if configured
            if self.trusted_endpoints and client_host not in self.trusted_endpoints:
                # Emit untrusted client event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_AUTH_VALIDATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "client_host": client_host,
                        "trusted_endpoints": self.trusted_endpoints,
                        "formation": self.formation_name,
                    },
                    description="Untrusted client attempted A2A communication",
                )

                #  Untrusted client event already emitted above
                return {"status": "error", "error": "Untrusted client", "message_id": message_id}

            # Check if agent exists in the formation
            if not self.overlord or agent_id not in self.overlord.agents:
                # Emit agent not found event
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "available_agents": (
                            list(self.overlord.agents.keys()) if self.overlord else []
                        ),
                        "formation": self.formation_name,
                    },
                    description=f"A2A message failed: Agent {agent_id} not found",
                )

                #  Agent not found event already emitted above
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not found",
                    "message_id": message_id,
                }

            # Get the target agent directly
            agent = self.overlord.agents[agent_id]

            # Check if agent accepts external A2A messages
            if not getattr(agent, "a2a_external", True):
                # Emit agent not configured for external A2A event
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "formation": self.formation_name,
                    },
                    description=(
                        f"A2A message failed: Agent {agent_id} " "not configured for external A2A"
                    ),
                )

                #  Agent A2A config event already emitted above
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not configured for external A2A",
                    "message_id": message_id,
                }

            # Emit message routing event
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": agent_id,
                    "message_id": message_id,
                    "message_type": request.message_type,
                    "formation": self.formation_name,
                },
                description=f"A2A message sent to agent {agent_id}",
            )

            # Route message directly to the agent
            response = await agent.handle_a2a_message(
                source_agent_id="external",
                message=request.message,
                message_type=request.message_type,
                context=request.context,
                message_id=message_id,
            )

            # Return successful response
            if response:
                # Extract the actual response content from the agent's response
                response_content = (
                    response.get("response") if isinstance(response, dict) else str(response)
                )

                # Emit successful message processing event
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "response_length": (len(response_content) if response_content else 0),
                        "formation": self.formation_name,
                    },
                    description=(f"A2A message successfully processed " f"by agent {agent_id}"),
                )

                return {
                    "status": "success",
                    "response": response_content,  # Extract the actual content string
                    "agent_id": agent_id,
                    "message_id": message_id,
                }
            else:
                # Handle case where agent doesn't return a response (e.g., notifications)
                observability.observe(
                    event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
                    level=observability.EventLevel.INFO,
                    data={
                        "agent_id": agent_id,
                        "message_id": message_id,
                        "formation": self.formation_name,
                    },
                    description=(
                        f"A2A message delivered successfully " f"to agent {agent_id} (no response)"
                    ),
                )

                return {
                    "status": "success",
                    "message": "Message delivered successfully",
                    "agent_id": agent_id,
                    "message_id": message_id,
                }

        except Exception as e:
            # Emit error event for message handling failure
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "formation": self.formation_name,
                },
                description=f"A2A message handling failed for agent {agent_id}",
            )

            #  Message handling error event already emitted above
            return {
                "status": "error",
                "error": f"Message handling failed: {str(e)}",
                "agent_id": agent_id,
                "message_id": message_id,
            }

    def _create_agent_card(self, agent_id: str, agent) -> Dict[str, Any]:
        """Create an A2A agent card for discovery"""
        try:
            agent_description = self.overlord.agent_descriptions.get(agent_id, f"Agent {agent_id}")

            card = {
                "name": agent_id,
                "description": agent_description,
                "version": "1.0.0",
                "url": f"http://{self.host}:{self.port}/agents/{agent_id}/message",
                "capabilities": {
                    "messaging": {
                        "enabled": True,
                        "description": "Agent can receive and process A2A messages",
                    },
                    "tools": {
                        "enabled": hasattr(agent, "get_capabilities"),
                        "description": "Agent has tool capabilities",
                    },
                },
                "authentication": {"type": self.auth_mode, "required": self.auth_mode != "none"},
                "formation": self.formation_name,
                "agent_id": agent_id,
            }

            # Emit agent card creation event
            observability.observe(
                event_type=observability.ConversationEvents.A2A_DISCOVERY_COMPLETED,
                level=observability.EventLevel.DEBUG,
                data={
                    "agent_id": agent_id,
                    "formation": self.formation_name,
                    "has_tools": hasattr(agent, "get_capabilities"),
                },
                description=f"A2A agent card created for {agent_id}",
            )

            return card

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": agent_id,
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to create agent card for {agent_id}: {str(e)}",
            )
            raise

    def _find_free_port(self) -> int:
        """Find a free port for the server (fallback if configured port unavailable)"""
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.bind(("", 0))
                s.listen(1)
                port = s.getsockname()[1]

            # Emit port discovery event
            observability.observe(
                event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                level=observability.EventLevel.INFO,
                data={"formation": self.formation_name, "port": port, "original_port": self.port},
                description=f"Free port found for A2A Formation Server: {port}",
            )

            return port

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to find free port for A2A Formation Server: {str(e)}",
            )
            raise

    async def start(self) -> Dict[str, Any]:
        """
        Start the A2A Formation Server.

        Returns:
            Server startup information
        """
        try:
            if self.is_running:
                # Emit already running event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "formation": self.formation_name,
                        "port": self.port,
                        "status": "already_running",
                    },
                    description="A2A Formation Server already running",
                )

                #  Server already running event - add observability
                return await self.get_status()

            # Emit server starting event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "port": self.port,
                    "host": self.host,
                    "auth_mode": self.auth_mode,
                },
                description=f"Starting A2A Formation Server for {self.formation_name}",
            )

            # Initialize authentication credentials from SecretsManager
            await self.authenticator.initialize_credentials()

            # Check if port is available
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                try:
                    s.bind((self.host, self.port))
                except OSError:
                    # Emit port unavailable event
                    observability.observe(
                        event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                        level=observability.EventLevel.WARNING,
                        data={"formation": self.formation_name, "original_port": self.port},
                        description=f"Port {self.port} unavailable, finding alternative",
                    )

                    #  Port unavailable event - add observability
                    self.port = self._find_free_port()

            # Create uvicorn config
            config = uvicorn.Config(
                app=self.app, host=self.host, port=self.port, log_level="info", access_log=True
            )

            # Start server
            server = uvicorn.Server(config)
            self.server_task = asyncio.create_task(server.serve())
            self.is_running = True

            # Emit successful server start event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "host": self.host,
                    "port": self.port,
                    "endpoint": f"http://{self.host}:{self.port}",
                    "agents_count": len(self.overlord.agents) if self.overlord else 0,
                    "auth_mode": self.auth_mode,
                },
                description="A2A Formation Server started successfully",
            )
            return {
                "status": "started",
                "formation": self.formation_name,
                "host": self.host,
                "port": self.port,
                "endpoint": f"http://{self.host}:{self.port}",
                "agents": list(self.overlord.agents.keys()) if self.overlord else [],
                "auth_mode": self.auth_mode,
            }

        except Exception as e:
            # Emit server start failure event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STOPPED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "port": self.port,
                    "error": str(e),
                },
                description=f"Failed to start A2A Formation Server: {str(e)}",
            )

            #  Server start failure event - add observability
            self.is_running = False
            raise

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the A2A Formation Server.

        Returns:
            Server shutdown information
        """
        try:
            if not self.is_running:
                # Emit not running event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_SERVER_STOPPED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "formation": self.formation_name,
                        "status": "not_running",
                    },
                    description="A2A Formation Server not running",
                )

                #  Server not running event - add observability
                return {"status": "not_running"}

            # Emit server stopping event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STOPPED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "port": self.port,
                },
                description=f"Stopping A2A Formation Server for {self.formation_name}",
            )

            if self.server_task and not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass

            self.is_running = False

            # Emit successful server stop event
            observability.observe(
                event_type=observability.SystemEvents.A2A_SERVER_STOPPED,
                level=observability.EventLevel.INFO,
                data={
                    "formation": self.formation_name,
                    "port": self.port,
                },
                description="A2A Formation Server stopped successfully",
            )

            #  Server stopped event - add observability

            return {"status": "stopped", "formation": self.formation_name, "port": self.port}

        except Exception as e:
            # Emit server stop failure event
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "port": self.port,
                    "error": str(e),
                },
                description=f"Error stopping A2A Formation Server: {str(e)}",
            )

            #  Server stop error event - add observability
            raise

    async def get_status(self) -> Dict[str, Any]:
        """Get current server status"""
        try:
            status = {
                "running": self.is_running,
                "formation": self.formation_name,
                "host": self.host,
                "port": self.port,
                "endpoint": f"http://{self.host}:{self.port}" if self.is_running else None,
                "agents": list(self.overlord.agents.keys()) if self.overlord else [],
                "auth_mode": self.auth_mode,
                "trusted_endpoints": self.trusted_endpoints,
            }

            # Emit status check event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.DEBUG,
                data={
                    "formation": self.formation_name,
                    "running": self.is_running,
                    "agents_count": len(status["agents"]),
                },
                description="A2A Formation Server status checked",
            )

            return status

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"Failed to get A2A Formation Server status: {str(e)}",
            )
            raise

    async def health_check(self) -> bool:
        """Check if the server is healthy and responding"""
        try:
            if not self.is_running:
                # Emit health check failure event
                observability.observe(
                    event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                    level=observability.EventLevel.WARNING,
                    data={
                        "formation": self.formation_name,
                        "running": False,
                    },
                    description="A2A Formation Server health check failed: server not running",
                )
                return False

            # Try to connect to the server port
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(1)
                result = s.connect_ex((self.host, self.port))
                is_healthy = result == 0

            # Emit health check result event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=(
                    observability.EventLevel.INFO
                    if is_healthy
                    else observability.EventLevel.WARNING
                ),
                data={
                    "formation": self.formation_name,
                    "healthy": is_healthy,
                    "port": self.port,
                    "connection_result": result,
                },
                description=(
                    f"A2A Formation Server health check " f"{'passed' if is_healthy else 'failed'}"
                ),
            )

            return is_healthy

        except Exception as e:
            # Emit health check error event
            observability.observe(
                event_type=observability.SystemEvents.A2A_HEALTH_CHECK,
                level=observability.EventLevel.ERROR,
                data={
                    "formation": self.formation_name,
                    "error": str(e),
                },
                description=f"A2A Formation Server health check error: {str(e)}",
            )

            #  Health check failure event - add observability
            return False
