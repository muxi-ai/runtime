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
import uuid

from fastapi import FastAPI, Path
import uvicorn
from pydantic import BaseModel

from loguru import logger


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


class A2AFormationServer:
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
        formation_name: str = "default"
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

        # Initialize FastAPI app
        self._create_app()

        logger.info(f"Initialized A2A Formation Server for '{formation_name}' on port {port}")

    def _create_app(self) -> None:
        """Create the FastAPI application with A2A endpoints"""
        self.app = FastAPI(
            title=f"A2A Formation Server - {self.formation_name}",
            description="Single A2A server for entire formation with agent routing",
            version="1.0.0",
            docs_url="/docs" if self.auth_mode == "none" else None,  # Disable docs if authenticated
        )

        # Health check endpoint
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint for the A2A server"""
            return {
                "status": "healthy",
                "formation": self.formation_name,
                "agents": list(self.overlord.agents.keys()) if self.overlord else [],
                "timestamp": asyncio.get_event_loop().time()
            }

        # Formation info endpoint
        @self.app.get("/info")
        async def formation_info():
            """Get information about the formation and available agents"""
            agents_info = {}
            if self.overlord:
                for agent_id, agent in self.overlord.agents.items():
                    # Only include agents with external A2A enabled
                    if getattr(agent, 'a2a_external', True):
                        agents_info[agent_id] = {
                            "description": self.overlord.agent_descriptions.get(agent_id, ""),
                            "capabilities": getattr(agent, 'capabilities', []),
                            "endpoint": f"/agents/{agent_id}/message"
                        }

            return {
                "formation": self.formation_name,
                "server_mode": self.auth_mode,
                "agents": agents_info,
                "total_agents": len(agents_info)
            }

        # Agent discovery endpoint (A2A standard)
        @self.app.get("/agents")
        async def list_agents():
            """List all agents available for A2A communication"""
            agent_cards = []
            if self.overlord:
                for agent_id, agent in self.overlord.agents.items():
                    # Only include agents with external A2A enabled
                    if getattr(agent, 'a2a_external', True):
                        agent_cards.append(self._create_agent_card(agent_id, agent))

            return {
                "agents": agent_cards,
                "formation": self.formation_name
            }

        # Main A2A message endpoint for specific agents
        @self.app.post("/agents/{agent_id}/message")
        async def handle_agent_message(
            agent_id: str = Path(..., description="ID of the target agent"),
            request: A2AMessageRequest = ...
        ) -> A2AMessageResponse:
            """
            Handle A2A message for a specific agent.

            This is the main endpoint that external agents use to communicate
            with agents in this formation.
            """
            return await self._handle_a2a_message(agent_id, request)

        # Legacy endpoint support (if needed)
        @self.app.post("/{agent_id}")
        async def handle_legacy_message(
            agent_id: str = Path(..., description="ID of the target agent"),
            request: A2AMessageRequest = ...
        ) -> A2AMessageResponse:
            """Legacy endpoint for backward compatibility"""
            return await self._handle_a2a_message(agent_id, request)

    async def _handle_a2a_message(
        self, agent_id: str, request: A2AMessageRequest
    ) -> Dict[str, Any]:
        """
        Handle incoming A2A message by routing directly to the target agent.

        This method routes messages directly to agents without going through
        the overlord's routing mechanism for better performance and cleaner
        separation of concerns.
        """
        # Generate unique message ID
        message_id = str(uuid.uuid4())

        try:
            # Get client host for security validation
            # Note: In a real implementation, this would come from the request headers
            client_host = "127.0.0.1"  # Default for development

            # Validate trusted endpoints if configured
            if self.trusted_endpoints and client_host not in self.trusted_endpoints:
                logger.warning(
                    f"Untrusted client {client_host} attempted A2A communication"
                )
                return {
                    "status": "error",
                    "error": "Untrusted client",
                    "message_id": message_id
                }

            # Check if agent exists in the formation
            if not self.overlord or agent_id not in self.overlord.agents:
                logger.warning(f"Agent {agent_id} not found in formation")
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not found",
                    "message_id": message_id
                }

            # Get the target agent directly
            agent = self.overlord.agents[agent_id]

            # Check if agent accepts external A2A messages
            if not getattr(agent, 'a2a_external', True):
                logger.warning(f"Agent {agent_id} not configured for external A2A")
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not configured for external A2A",
                    "message_id": message_id
                }

            # Log the incoming A2A message
            logger.info(
                f"A2A Message: external -> {agent_id} ({request.message_type}, id: {message_id})"
            )

            # Route message directly to the agent
            response = await agent.handle_a2a_message(
                source_agent_id="external",
                message=request.message,
                message_type=request.message_type,
                context=request.context,
                message_id=message_id
            )

            # Return successful response
            if response:
                return {
                    "status": "success",
                    "response": response,
                    "agent_id": agent_id,
                    "message_id": message_id
                }
            else:
                # Handle case where agent doesn't return a response (e.g., notifications)
                return {
                    "status": "success",
                    "message": "Message delivered successfully",
                    "agent_id": agent_id,
                    "message_id": message_id
                }

        except Exception as e:
            logger.error(f"Error handling A2A message for agent {agent_id}: {e}")
            return {
                "status": "error",
                "error": f"Message handling failed: {str(e)}",
                "agent_id": agent_id,
                "message_id": message_id
            }

    def _create_agent_card(self, agent_id: str, agent) -> Dict[str, Any]:
        """Create an A2A agent card for discovery"""
        agent_description = self.overlord.agent_descriptions.get(agent_id, f"Agent {agent_id}")

        return {
            "name": agent_id,
            "description": agent_description,
            "version": "1.0.0",
            "url": f"http://{self.host}:{self.port}/agents/{agent_id}/message",
            "capabilities": {
                "messaging": {
                    "enabled": True,
                    "description": "Agent can receive and process A2A messages"
                },
                "tools": {
                    "enabled": hasattr(agent, 'get_capabilities'),
                    "description": "Agent has tool capabilities"
                }
            },
            "authentication": {
                "type": self.auth_mode,
                "required": self.auth_mode != "none"
            },
            "formation": self.formation_name,
            "agent_id": agent_id
        }

    def _find_free_port(self) -> int:
        """Find a free port for the server (fallback if configured port unavailable)"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    async def start(self) -> Dict[str, Any]:
        """
        Start the A2A Formation Server.

        Returns:
            Server startup information
        """
        if self.is_running:
            logger.warning("A2A Formation Server already running")
            return await self.get_status()

        try:
            # Check if port is available
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                try:
                    s.bind((self.host, self.port))
                except OSError:
                    logger.warning(f"Port {self.port} unavailable, finding alternative")
                    self.port = self._find_free_port()

            # Create uvicorn config
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=True
            )

            # Start server
            server = uvicorn.Server(config)
            self.server_task = asyncio.create_task(server.serve())
            self.is_running = True

            logger.info(f"A2A Formation Server started on http://{self.host}:{self.port}")
            logger.info(f"Formation: {self.formation_name}")
            logger.info(
                f"Available agents: {list(self.overlord.agents.keys()) if self.overlord else []}"
            )

            return {
                "status": "started",
                "formation": self.formation_name,
                "host": self.host,
                "port": self.port,
                "endpoint": f"http://{self.host}:{self.port}",
                "agents": list(self.overlord.agents.keys()) if self.overlord else [],
                "auth_mode": self.auth_mode
            }

        except Exception as e:
            logger.error(f"Failed to start A2A Formation Server: {e}")
            self.is_running = False
            raise

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the A2A Formation Server.

        Returns:
            Server shutdown information
        """
        if not self.is_running:
            logger.warning("A2A Formation Server not running")
            return {"status": "not_running"}

        try:
            if self.server_task and not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass

            self.is_running = False
            logger.info(f"A2A Formation Server stopped on port {self.port}")

            return {
                "status": "stopped",
                "formation": self.formation_name,
                "port": self.port
            }

        except Exception as e:
            logger.error(f"Error stopping A2A Formation Server: {e}")
            raise

    async def get_status(self) -> Dict[str, Any]:
        """Get current server status"""
        return {
            "running": self.is_running,
            "formation": self.formation_name,
            "host": self.host,
            "port": self.port,
            "endpoint": f"http://{self.host}:{self.port}" if self.is_running else None,
            "agents": list(self.overlord.agents.keys()) if self.overlord else [],
            "auth_mode": self.auth_mode,
            "trusted_endpoints": self.trusted_endpoints
        }

    async def health_check(self) -> bool:
        """Check if the server is healthy and responding"""
        if not self.is_running:
            return False

        try:
            # Try to connect to the server port
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(1)
                result = s.connect_ex((self.host, self.port))
                return result == 0
        except Exception as e:
            logger.error(f"A2A server health check failed: {e}")
            return False
