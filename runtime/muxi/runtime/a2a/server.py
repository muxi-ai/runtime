"""
A2A Agent Server Implementation

This module implements the A2A agent server using Google's official a2a-sdk package
as the foundation, with integration into MUXI's existing agent architecture.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import socket
from contextlib import closing

# Google's a2a-sdk imports (required dependency)
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.events import EventQueue, InMemoryQueueManager
from a2a.types import Message, AgentCard, TextPart
from a2a.server.apps.starlette_app import A2AStarletteApplication


class MUXIAgentExecutor(AgentExecutor):
    """
    MUXI-specific A2A agent executor that integrates with existing agent architecture
    """

    def __init__(self, agent_instance=None, logger=None):
        """Initialize the MUXI agent executor"""
        self.agent_instance = agent_instance
        self.logger = logger or logging.getLogger(__name__)

    async def execute(self, request: RequestContext, queue: EventQueue) -> None:
        """Execute the agent request and publish events to the queue"""
        try:
            self.logger.debug(f"Executing A2A request for task {request.task_id}")

            # If we have a MUXI agent instance, delegate to it
            if (self.agent_instance and
                    hasattr(self.agent_instance, 'process_a2a_message')):

                # Extract message content from the request
                message_content = None
                if hasattr(request, 'task') and request.task and hasattr(request.task, 'content'):
                    message_content = request.task.content
                elif (hasattr(request, 'request') and request.request and
                      hasattr(request.request, 'message')):
                    message_content = request.request.message.content

                response_content = await self.agent_instance.process_a2a_message(
                    message=message_content or "No message content",
                    sender="unknown"
                )
            else:
                # Fallback response for testing/development
                agent_id = (self.agent_instance.agent_id
                            if self.agent_instance else 'unknown')
                response_content = f"Echo from {agent_id}: A2A message received"

            # Create a response message and publish to queue
            text_part = TextPart(text=response_content)
            response_message = Message(
                messageId=f"msg_{request.task_id}",
                contextId=request.context_id,
                taskId=request.task_id,
                parts=[text_part],
                role="agent"
            )

            queue.enqueue_event(response_message)

        except Exception as e:
            self.logger.error(f"Error executing A2A request: {e}")
            error_text_part = TextPart(text=f"Error processing request: {str(e)}")
            error_message = Message(
                messageId=f"error_{request.task_id}",
                contextId=request.context_id,
                taskId=request.task_id,
                parts=[error_text_part],
                role="agent"
            )
            queue.enqueue_event(error_message)

    async def cancel(self, request: RequestContext, queue: EventQueue) -> None:
        """Cancel the agent execution"""
        self.logger.info(f"Cancelling A2A request for task {request.task_id}")
        # For now, just log the cancellation
        # In a full implementation, we'd need to handle actual cancellation


def create_basic_agent_card(agent_id: str, name: str, description: str = None) -> AgentCard:
    """Create a basic AgentCard for the A2A server"""
    return AgentCard(
        name=name,
        description=description or f"MUXI agent: {name}",
        url=f"http://localhost:8000/agents/{agent_id}",
        capabilities={},  # Empty dict instead of list
        defaultInputModes=[],
        defaultOutputModes=[],
        skills=[],
        version="1.0.0"
    )


class A2AAgentServer:
    """
    A2A Agent Server that wraps Google's a2a-sdk with MUXI integration
    """

    def __init__(self, agent_instance=None, port: Optional[int] = None):
        """Initialize the A2A agent server"""
        self.agent_instance = agent_instance
        self.port = port or self._find_free_port()
        agent_id = agent_instance.agent_id if agent_instance else 'unknown'
        agent_name = getattr(agent_instance, 'name', agent_id)
        self.logger = logging.getLogger(f"{__name__}.{agent_id}")

        # Create a basic agent card for the A2A server
        self.agent_card = create_basic_agent_card(
            agent_id=agent_id,
            name=agent_name,
            description=f"MUXI A2A agent: {agent_name}"
        )

        # Create the required components for the A2A server
        self.agent_executor = MUXIAgentExecutor(agent_instance, self.logger)
        self.task_store = InMemoryTaskStore()
        self.queue_manager = InMemoryQueueManager()

        # Create the request handler
        self.request_handler = DefaultRequestHandler(
            agent_executor=self.agent_executor,
            task_store=self.task_store,
            queue_manager=self.queue_manager
        )

        # Create the Starlette app using A2AStarletteApplication
        self.app = A2AStarletteApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        self.server_task = None
        self.is_running = False

    def _find_free_port(self) -> int:
        """Find a free port for the server"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    async def start(self) -> Dict[str, Any]:
        """Start the A2A server"""
        try:
            import uvicorn

            config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="info"
            )

            server = uvicorn.Server(config)
            self.server_task = asyncio.create_task(server.serve())
            self.is_running = True

            self.logger.info(f"A2A server started on port {self.port}")

            return {
                "status": "started",
                "port": self.port,
                "endpoint": f"http://localhost:{self.port}",
                "agent_id": self.agent_instance.agent_id if self.agent_instance else "unknown"
            }

        except Exception as e:
            self.logger.error(f"Failed to start A2A server: {e}")
            raise

    async def stop(self) -> Dict[str, Any]:
        """Stop the A2A server"""
        try:
            if self.server_task and not self.server_task.done():
                self.server_task.cancel()
                try:
                    await self.server_task
                except asyncio.CancelledError:
                    pass

            self.is_running = False
            self.logger.info(f"A2A server stopped on port {self.port}")

            return {
                "status": "stopped",
                "port": self.port,
                "agent_id": self.agent_instance.agent_id if self.agent_instance else "unknown"
            }

        except Exception as e:
            self.logger.error(f"Error stopping A2A server: {e}")
            raise

    async def get_status(self) -> Dict[str, Any]:
        """Get the current status of the A2A server"""
        return {
            "running": self.is_running,
            "port": self.port,
            "endpoint": f"http://localhost:{self.port}" if self.is_running else None,
            "agent_id": self.agent_instance.agent_id if self.agent_instance else "unknown"
        }

    async def health_check(self) -> bool:
        """Check if the server is healthy"""
        try:
            if not self.is_running:
                return False

            # Try to connect to the server port
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', self.port))
                return result == 0

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False


class A2AServerManager:
    """
    Manager for multiple A2A agent servers
    """

    def __init__(self):
        """Initialize the A2A server manager"""
        self.servers: Dict[str, A2AAgentServer] = {}
        self.logger = logging.getLogger(f"{__name__}.ServerManager")

    async def start_server(self, agent_instance, port: Optional[int] = None) -> Dict[str, Any]:
        """Start an A2A server for an agent"""
        agent_id = agent_instance.agent_id

        if agent_id in self.servers:
            self.logger.warning(f"Server for agent {agent_id} already exists")
            return await self.servers[agent_id].get_status()

        server = A2AAgentServer(agent_instance, port)
        self.servers[agent_id] = server

        result = await server.start()
        self.logger.info(f"Started A2A server for agent {agent_id} on port {server.port}")

        return result

    async def stop_server(self, agent_id: str) -> Dict[str, Any]:
        """Stop an A2A server for an agent"""
        if agent_id not in self.servers:
            raise ValueError(f"No server found for agent {agent_id}")

        server = self.servers[agent_id]
        result = await server.stop()
        del self.servers[agent_id]

        self.logger.info(f"Stopped A2A server for agent {agent_id}")
        return result

    async def stop_all_servers(self) -> Dict[str, Any]:
        """Stop all A2A servers"""
        results = {}

        for agent_id in list(self.servers.keys()):
            try:
                results[agent_id] = await self.stop_server(agent_id)
            except Exception as e:
                self.logger.error(f"Error stopping server for {agent_id}: {e}")
                results[agent_id] = {"status": "error", "message": str(e)}

        return results

    async def get_server_info(self, agent_id: str) -> Dict[str, Any]:
        """Get information about a specific server"""
        if agent_id not in self.servers:
            raise ValueError(f"No server found for agent {agent_id}")

        return await self.servers[agent_id].get_status()

    async def get_all_servers_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all servers"""
        results = {}

        for agent_id, server in self.servers.items():
            try:
                results[agent_id] = await server.get_status()
            except Exception as e:
                self.logger.error(f"Error getting info for {agent_id}: {e}")
                results[agent_id] = {"status": "error", "message": str(e)}

        return results

    async def health_check_all(self) -> Dict[str, bool]:
        """Health check all servers"""
        results = {}

        for agent_id, server in self.servers.items():
            try:
                results[agent_id] = await server.health_check()
            except Exception as e:
                self.logger.error(f"Health check failed for {agent_id}: {e}")
                results[agent_id] = False

        return results
