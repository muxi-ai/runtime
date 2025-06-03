# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Agent - AI Agent Implementation
# Description:  Core implementation of AI agents with memory and tool use
# Role:         Primary interface for language model interactions
# Usage:        Created and managed by the Overlord to process user messages
# Author:       Muxi Framework Team
#
# The Agent class is a fundamental component in the Muxi framework that:
#
# 1. Handles Direct Interactions
#    - Processes user messages and generates responses
#    - Maintains conversation context for coherent exchanges
#    - Integrates with memory systems for contextual awareness
#
# 2. Tool Integration
#    - Connects to external tools via MCP (Model Context Protocol)
#    - Parses and processes tool calls from language model responses
#    - Manages tool invocation and result incorporation
#
# 3. Memory Usage
#    - Delegates memory storage to the overlord
#    - Retrieves relevant context from memory systems
#    - Works with overlord for information extraction
#
# Agents are typically created and managed by the Overlord:
#
# Programmatic creation:
#   agent = overlord.create_agent(
#       agent_id="assistant",
#       model=model,
#       system_message="You are a helpful assistant."
#   )
#
# Direct usage:
#   response = await agent.process_message("Hello, how can you help me?")
#
# This file defines both the Agent class and the supporting MCPServer class
# for external tool integration.
# =============================================================================

import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional, Union

from .mcp.message import MCPMessage
from .mcp.service import MCPService
from .llm import LLM

logger = logging.getLogger(__name__)


class Agent:
    """
    An agent that interacts with users and tools.

    The Agent class manages interactions between users and language models,
    using its overlord's memory systems for context retention and retrieval.
    It can process messages, invoke tools via MCP, and maintain conversation state.
    """

    def __init__(
        self,
        model: LLM,
        overlord: Any,  # Forward reference to Overlord
        system_message: Optional[str] = None,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        request_timeout: Optional[int] = None,
        a2a_internal: bool = True,
        a2a_external: bool = True,
    ):
        """
        Initialize the agent with a model, overlord, and optional parameters.

        Args:
            model: The language model for the agent to use. This model handles
                the core intelligence of the agent.
            overlord: The overlord that manages this agent. Provides
                access to memory systems and coordinates multi-agent systems.
            system_message: Optional system message to set the agent's behavior
                and persona. Defines the agent's role and capabilities.
            agent_id: Optional unique ID for the agent. If None, generates a UUID.
                Used for identification in memory systems and routing.
            name: Optional name for the agent (e.g., "Customer Service Bot").
                Used for display purposes.
            request_timeout: Optional timeout in seconds for MCP requests.
                Defaults to overlord's timeout if not specified.
            a2a_internal: Whether this agent participates in intra-formation A2A
                communication. Default True.
            a2a_external: Whether this agent participates in external A2A
                communication. Default True.
        """
        self.model = model
        self.overlord = overlord

        # Set up agent identification
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name or f"Agent-{self.agent_id}"

        # Set up system message
        self.system_message = system_message or (
            "You are a helpful assistant that responds accurately to user queries. "
            "Provide detailed, factual responses and be transparent about uncertainty."
        )

        # Set up A2A configuration (single source of truth)
        self.a2a_internal = a2a_internal
        self.a2a_external = a2a_external

        # Set request timeout (use overlord's if not specified)
        if request_timeout is not None:
            self.request_timeout = request_timeout
        elif hasattr(overlord, "request_timeout"):
            self.request_timeout = overlord.request_timeout
        else:
            self.request_timeout = 60  # Default fallback

        # Set up MCP service access
        self._mcp_service = MCPService.get_instance()

        # Initialize the context with system message
        self._messages = []
        if self.system_message:
            self._messages.append({"role": "system", "content": self.system_message})

    def get_mcp_service(self) -> MCPService:
        """
        Get the centralized MCP service for tool integrations.

        Returns:
            The MCPService instance used by this agent for connecting to
            and interacting with external tools.
        """
        return self._mcp_service

    async def process_message(
        self, message: Union[str, MCPMessage], user_id: Optional[int] = None
    ) -> MCPMessage:
        """
        Process a message from the user and generate a response.

        This method handles:
        1. Converting input to MCPMessage format
        2. Adding the message to memory via the overlord
        3. Updating conversation context
        4. Processing the message with the model
        5. Handling any tool calls in the response
        6. Storing the response in memory

        Args:
            message: The message from the user, either as a string or an MCPMessage.
                Contains the content to be processed by the agent.
            user_id: Optional user ID for multi-user support. Used for memory
                isolation and user-specific context.

        Returns:
            The agent's response as an MCPMessage, possibly including tool call results.
        """
        # Convert string message to MCPMessage if needed
        if isinstance(message, str):
            content = message
            message_obj = MCPMessage(role="user", content=content)
        else:
            content = message.content
            message_obj = message

        # Let overlord handle memory management
        timestamp = datetime.datetime.now().timestamp()
        if self.overlord and hasattr(self.overlord, "add_message_to_memory"):
            await self.overlord.add_message_to_memory(
                content=content,
                role="user",
                timestamp=timestamp,
                agent_id=self.agent_id,
                user_id=user_id,
            )

        # Add message to conversation context
        self._messages.append({"role": "user", "content": message_obj.content})

        # Process the message with the model directly
        raw_response = await self.model.chat(self._messages)

        # Create response message
        response = MCPMessage(role="assistant", content=raw_response)

        # Add response to conversation context
        self._messages.append({"role": "assistant", "content": response.content})

        # Let overlord handle memory management for the response
        if self.overlord and hasattr(self.overlord, "add_message_to_memory"):
            timestamp = datetime.datetime.now().timestamp()
            await self.overlord.add_message_to_memory(
                content=response.content,
                role="assistant",
                timestamp=timestamp,
                agent_id=self.agent_id,
                user_id=user_id,
            )

        # User information extraction is handled by the overlord
        if (
            user_id is not None
            and user_id != 0  # Skip extraction for anonymous users
            and self.overlord
            and hasattr(self.overlord, "handle_user_information_extraction")
        ):
            # Process this conversation turn for user information extraction
            await self.overlord.handle_user_information_extraction(
                user_message=content,
                agent_response=response.content,
                user_id=user_id,
                agent_id=self.agent_id,
            )

        return response

    async def run(self, input_text: str, use_memory: bool = True) -> str:
        """
        Run the agent with the given input text and return a text response.

        This is a simplified interface that handles:
        1. Retrieving relevant context from memory (if use_memory=True)
        2. Processing the input with context
        3. Returning just the text content of the response

        Args:
            input_text: The input text to process. The user's message or query.
            use_memory: Whether to use memory for context enhancement. When True,
                relevant memories will be retrieved and included in the prompt.

        Returns:
            The agent's response as a plain text string.
        """
        # Initialize context
        context = ""

        # Retrieve relevant memories if requested
        if use_memory:
            memories = await self.get_relevant_memories(input_text)
            if memories:
                memory_text = "\n".join([mem["text"] for mem in memories])
                context = f"Previous conversation context:\n{memory_text}\n\n"

        # Combine context with input
        full_input = f"{context}User: {input_text}"

        # Process with the model
        response = await self.process_message(full_input)

        return response.content

    async def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get relevant memories from the overlord's memory systems.

        This method searches through the overlord's memory systems to find
        information relevant to the current query. It can search both buffer
        memory (for recent context) and long-term memory (for persistent knowledge).

        Args:
            query: The search query to find relevant memories.
            limit: Maximum number of memories to return.

        Returns:
            List of memory dictionaries containing relevant information.
        """
        memories = []
        if self.overlord and hasattr(self.overlord, "search_memory"):
            memories = await self.overlord.search_memory(
                query=query, agent_id=self.agent_id, k=limit
            )
        return memories

    def discover_agents(
        self, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Discover other agents available for A2A (Agent-to-Agent) communication.

        This is the simple discovery method for local formations. The agent asks
        its overlord what other agents exist and what they can do.

        Args:
            capability_filter: Optional list of required capabilities to filter agents by.
                Only agents with at least one of these capabilities will be returned.

        Returns:
            Dict mapping agent_id to agent information including:
            - description: Agent's description/purpose
            - capabilities: List of agent's available capabilities
            - status: Always 'active' for agents in the local formation

        Example:
            >>> # Weather agent discovers calendar agents
            >>> calendar_agents = agent.discover_agents(['calendar_lookup'])
            >>> print(calendar_agents)
            {
                'calendar-agent': {
                    'description': 'Manages calendar events and scheduling',
                    'capabilities': ['calendar_lookup', 'schedule_meeting'],
                    'status': 'active'
                }
            }
        """
        if not self.overlord or not hasattr(self.overlord, 'get_available_agents_for_a2a'):
            return {}

        return self.overlord.get_available_agents_for_a2a(
            requesting_agent_id=self.agent_id,
            capability_filter=capability_filter
        )

    async def invoke_tool(
        self, tool_name: str, parameters: Dict[str, Any], server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke a tool via the centralized MCP service.

        This method sends a tool call to the MCP service and returns the result.
        The MCP service handles routing to the appropriate server.

        Args:
            tool_name: The name of the tool to call. Must match a tool provided
                by a connected MCP server.
            parameters: The parameters to pass to the tool. Must match the
                expected parameters for the specified tool.
            server_id: Optional specific server ID to use. If not provided,
                the MCP service will route to an appropriate server.

        Returns:
            The result of the tool call as a dictionary.

        Raises:
            Exception: Any error from the MCP service during tool invocation
        """
        return await self._mcp_service.invoke_tool(
            tool_name=tool_name,
            parameters=parameters,
            server_id=server_id,
            request_timeout=self.request_timeout,
        )

    async def send_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Send an A2A (Agent-to-Agent) message to another agent in the formation.

        This is the simple messaging method for local formations. The agent asks
        its overlord to route the message to the target agent and optionally waits
        for a response.

        Args:
            target_agent_id: The ID of the agent to send the message to
            message: The message content (can be text or structured data)
            message_type: Type of message ("request", "notification", "response")
            context: Optional context information to include with the message
            wait_for_response: Whether to wait for a response (only for "request" type)
            timeout: Maximum time to wait for response in seconds

        Returns:
            Response from target agent if wait_for_response=True and message_type="request",
            otherwise None

        Example:
            >>> # Send a request and wait for response
            >>> response = await agent.send_a2a_message(
            ...     target_agent_id="calendar-agent",
            ...     message="Check availability for tomorrow 2-3pm",
            ...     message_type="request"
            ... )

            >>> # Send a notification (no response expected)
            >>> await agent.send_a2a_message(
            ...     target_agent_id="notification-agent",
            ...     message="Task completed successfully",
            ...     message_type="notification",
            ...     wait_for_response=False
            ... )
        """
        if not self.overlord or not hasattr(self.overlord, 'route_a2a_message'):
            raise RuntimeError("Overlord does not support A2A messaging")

        # Check if we can send A2A messages
        if not getattr(self, 'a2a_internal', True):
            raise RuntimeError(
                f"Agent {self.agent_id} is not configured for A2A communication"
            )

        return await self.overlord.route_a2a_message(
            source_agent_id=self.agent_id,
            target_agent_id=target_agent_id,
            message=message,
            message_type=message_type,
            context=context,
            wait_for_response=wait_for_response,
            timeout=timeout
        )

    async def handle_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming A2A message from another agent.

        This method is called by the overlord when another agent sends a message
        to this agent. It can be overridden by subclasses to implement custom
        A2A message handling logic.

        Args:
            source_agent_id: The ID of the agent that sent the message
            message: The message content (can be text or structured data)
            message_type: Type of message ("request", "notification", "response")
            context: Optional context information from the sender
            message_id: Unique message ID for tracking

        Returns:
            Response data if this is a "request" message, otherwise None
        """
        # Default handling based on message type
        if message_type == "request":
            # For requests, try to process using the agent's model
            try:
                # Create a context-enhanced prompt
                prompt_parts = [f"A2A Request from {source_agent_id}: {message}"]

                if context:
                    prompt_parts.append(f"Context: {context}")

                prompt_parts.append(
                    "Please provide a helpful response to this agent-to-agent request."
                )

                full_prompt = "\n".join(prompt_parts)

                # Process the message through the agent's model
                response = await self.process_message(full_prompt)

                return {
                    "status": "success",
                    "response": response.content,
                    "agent_id": self.agent_id,
                    "message_id": message_id
                }

            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "agent_id": self.agent_id,
                    "message_id": message_id
                }

        elif message_type == "notification":
            # For notifications, just acknowledge receipt
            logger.info(
                f"Agent {self.agent_id} received notification from {source_agent_id}: {message}"
            )
            return None

        elif message_type == "response":
            # For responses, log the response (typically handled by the sender)
            logger.info(f"Agent {self.agent_id} received response from {source_agent_id}")
            return None

        else:
            logger.warning(f"Agent {self.agent_id} received unknown message type: {message_type}")
            return None
