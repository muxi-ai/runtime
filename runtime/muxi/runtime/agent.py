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

import asyncio
import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

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

        # Debug logging to see what we got
        logger.debug(f"Raw response type: {type(raw_response)}")
        logger.debug(f"Raw response: {str(raw_response)[:200]}...")  # Truncate for readability

        # Extract the actual content string from the response
        if isinstance(raw_response, str):
            content = raw_response
            logger.debug("Used string path")
        elif hasattr(raw_response, 'choices') and raw_response.choices:
            # Handle ChatCompletionResponse object
            message = raw_response.choices[0].message
            logger.debug(f"Message type: {type(message)}")
            logger.debug(f"Message: {message}")
            if isinstance(message, dict):
                content = message.get('content', '')
                logger.debug("Used ChatCompletionResponse dict path")
            else:
                # Handle message as object with content attribute/property
                content = getattr(message, 'content', '')
                logger.debug("Used ChatCompletionResponse object path")
            logger.debug("Used ChatCompletionResponse path")
        elif isinstance(raw_response, dict) and 'choices' in raw_response:
            # Handle dict response format
            content = raw_response['choices'][0]['message']['content']
            logger.debug("Used dict path")
        else:
            # Try to extract content from string representation if it's embedded
            response_str = str(raw_response)
            if "content': '" in response_str or 'content": "' in response_str:
                # Try to extract content from string representation
                import re
                pattern = r"'content': '([^']*)'|\"content\": \"([^']*)\""
                content_match = re.search(pattern, response_str)
                if content_match:
                    content = content_match.group(1) or content_match.group(2)
                    logger.debug("Extracted content from string representation")
                else:
                    content = response_str
                    logger.debug("Used full string representation")
            else:
                content = response_str
                logger.debug("Used fallback string conversion")

        logger.debug(f"Final extracted content: {content[:100]}...")

        # Create response message
        response = MCPMessage(role="assistant", content=content)

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
        Send an A2A (Agent-to-Agent) message directly to another agent.

        This method handles both local and external communication directly,
        using the overlord only for discovery and resource access, not routing.

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
        if not self.overlord:
            raise RuntimeError("Agent has no overlord reference for A2A communication")

        # Check if we can send A2A messages
        if not getattr(self, 'a2a_internal', True):
            raise RuntimeError(
                f"Agent {self.agent_id} is not configured for A2A communication"
            )

        # Generate message ID for tracking
        import uuid
        message_id = str(uuid.uuid4())

        # First, try to find the target agent locally
        if target_agent_id in self.overlord.agents:
            return await self._send_local_a2a_message(
                target_agent_id=target_agent_id,
                message=message,
                message_type=message_type,
                context=context,
                wait_for_response=wait_for_response,
                timeout=timeout,
                message_id=message_id
            )

        # If not local, try external communication
        return await self._send_external_a2a_message(
            target_agent_id=target_agent_id,
            message=message,
            message_type=message_type,
            context=context,
            wait_for_response=wait_for_response,
            timeout=timeout,
            message_id=message_id
        )

    async def _send_local_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        wait_for_response: bool,
        timeout: int,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Send A2A message to a local agent directly."""
        target_agent = self.overlord.agents[target_agent_id]

        # Check if target agent accepts internal A2A
        if not getattr(target_agent, 'a2a_internal', True):
            raise RuntimeError(
                f"Target agent '{target_agent_id}' is not configured for A2A communication"
            )

        # Log the A2A communication
        logger.info(
            f"A2A Message (local): {self.agent_id} -> {target_agent_id} "
            f"({message_type}, id: {message_id})"
        )

        try:
            # Send message directly to target agent with timeout
            response = await asyncio.wait_for(
                target_agent.handle_a2a_message(
                    source_agent_id=self.agent_id,
                    message=message,
                    message_type=message_type,
                    context=context,
                    message_id=message_id
                ),
                timeout=timeout
            )

            # Return response if this was a request and caller wants to wait
            if message_type == "request" and wait_for_response:
                return response
            else:
                return None

        except asyncio.TimeoutError:
            logger.error(
                f"Local A2A message timed out after {timeout}s: "
                f"{self.agent_id} -> {target_agent_id}"
            )
            if message_type == "request" and wait_for_response:
                return {
                    "status": "error",
                    "error": f"Message timed out after {timeout} seconds",
                    "message_id": message_id
                }
            else:
                raise
        except Exception as e:
            logger.error(f"Local A2A message failed: {e}")
            if message_type == "request" and wait_for_response:
                return {
                    "status": "error",
                    "error": f"Message failed: {str(e)}",
                    "message_id": message_id
                }
            else:
                raise

    async def _send_external_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        wait_for_response: bool,
        timeout: int,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Send A2A message to an external agent via registry client."""
        # Get registry client from overlord
        registry_client = getattr(self.overlord, 'external_registry_client', None)
        if not registry_client:
            raise RuntimeError("No external registry client available for external A2A")

        # Check if this agent can send external messages
        if not getattr(self, 'a2a_external', True):
            raise RuntimeError(
                f"Agent {self.agent_id} is not configured for external A2A communication"
            )

        # Log the external A2A communication
        logger.info(
            f"A2A Message (external): {self.agent_id} -> {target_agent_id} "
            f"({message_type}, id: {message_id})"
        )

        try:
            # 1. Discover the target agent via registry
            logger.debug(f"Discovering external agent: {target_agent_id}")
            discovered_agents = await registry_client.discover_agents()

            # Find the target agent across all registries
            target_agent_url = None
            all_matches = []  # Collect all matching agents

            if isinstance(discovered_agents, dict):
                # Multiple registries
                for registry_url, agents in discovered_agents.items():
                    for agent_card in agents:
                        if ((hasattr(agent_card, 'name') and
                             agent_card.name == target_agent_id) or
                            (hasattr(agent_card, 'muxi_agent_id') and
                             agent_card.muxi_agent_id == target_agent_id)):
                            all_matches.append(agent_card)
                            logger.debug(
                                f"Found potential agent {target_agent_id} at {agent_card.url}"
                            )
            else:
                # Single registry
                for agent_card in discovered_agents:
                    if ((hasattr(agent_card, 'name') and
                         agent_card.name == target_agent_id) or
                        (hasattr(agent_card, 'muxi_agent_id') and
                         agent_card.muxi_agent_id == target_agent_id)):
                        all_matches.append(agent_card)
                        logger.debug(
                            f"Found potential agent {target_agent_id} at {agent_card.url}"
                        )

            # Handle duplicate agent registrations by preferring specific criteria
            if all_matches:
                if len(all_matches) == 1:
                    target_agent_url = all_matches[0].url
                else:
                    # Multiple matches found - prefer one that DOESN'T start
                    # with our own formation's port
                    # Get our own formation port to avoid selecting ourselves
                    our_port = "8080"  # Default
                    if (self.overlord and
                            hasattr(self.overlord, 'formation_config')):
                        formation_config = self.overlord.formation_config
                        if formation_config:
                            a2a_config = formation_config.get('a2a', {})
                            server_config = a2a_config.get('server', {})
                            our_port = str(server_config.get('port', 8080))

                    # Prefer agents that are NOT on our own formation port
                    preferred_match = None
                    for match in all_matches:
                        if f":{our_port}/" not in match.url:
                            preferred_match = match
                            break

                    # If no non-local match found, take the last one (most recent registration)
                    target_agent_url = (preferred_match or all_matches[-1]).url

                    logger.info(
                        f"Multiple agents found for {target_agent_id}, "
                        f"selected: {target_agent_url}"
                    )

                logger.debug(f"Selected agent {target_agent_id} at {target_agent_url}")

            if not target_agent_url:
                error_msg = f"Agent {target_agent_id} not found in external registries"
                logger.error(error_msg)
                if message_type == "request" and wait_for_response:
                    return {
                        "status": "error",
                        "error": error_msg,
                        "message_id": message_id
                    }
                else:
                    raise RuntimeError(error_msg)

            # 2. Prepare A2A message payload
            message_payload = {
                "message": message if isinstance(message, str) else str(message),
                "message_type": message_type,
                "context": context or {},
                "message_id": message_id
            }

            # 3. Apply authentication based on discovered agent requirements
            from muxi.runtime.a2a.auth import get_auth_manager, AuthType

            auth_manager = get_auth_manager()

            # Get authentication requirements from the discovered agent
            auth_type = AuthType.NONE
            auth_required = False

            # Find the matching discovered agent to get auth requirements
            matching_agent = None
            if discovered_agents:
                if isinstance(discovered_agents, dict):
                    # Multiple registries - search all
                    for registry_url, agent_list in discovered_agents.items():
                        for agent_card in agent_list:
                            if ((hasattr(agent_card, 'name') and agent_card.name == target_agent_id) or
                                (hasattr(agent_card, 'muxi_agent_id') and agent_card.muxi_agent_id == target_agent_id)):
                                matching_agent = agent_card
                                break
                        if matching_agent:
                            break
                else:
                    # Single registry
                    for agent_card in discovered_agents:
                        if ((hasattr(agent_card, 'name') and agent_card.name == target_agent_id) or
                            (hasattr(agent_card, 'muxi_agent_id') and agent_card.muxi_agent_id == target_agent_id)):
                            matching_agent = agent_card
                            break

            # Extract authentication requirements
            if matching_agent and hasattr(matching_agent, 'authentication') and matching_agent.authentication:
                auth_info = matching_agent.authentication
                auth_type = AuthType(auth_info.type.value if hasattr(auth_info.type, 'value') else str(auth_info.type))
                auth_required = auth_info.required
                logger.debug(f"Agent {target_agent_id} requires {auth_type} authentication (required: {auth_required})")
            else:
                logger.debug(f"No authentication requirements found for {target_agent_id}")

            # Prepare headers with authentication
            headers = {"Content-Type": "application/json"}

            # For HMAC and JWT authentication, we need the full request context
            if auth_type in [AuthType.HMAC, AuthType.JWT]:
                # Extract base URL and construct proper endpoint first
                parsed_url = urlparse(target_agent_url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                endpoint_url = f"{base_url}/agents/{target_agent_id}/message"

                # Convert message payload to JSON string for HMAC calculation
                payload_json = json.dumps(message_payload)

                auth_success, headers = await auth_manager.apply_authentication_with_context(
                    target_agent_id, auth_type, headers, endpoint_url, "POST", payload_json, auth_required
                )
            else:
                auth_success, headers = await auth_manager.apply_authentication(
                    target_agent_id, auth_type, headers, auth_required
                )

            if not auth_success and auth_required:
                error_msg = f"Authentication failed for {target_agent_id} (requires {auth_type})"
                logger.error(error_msg)
                if message_type == "request" and wait_for_response:
                    return {
                        "status": "error",
                        "error": error_msg,
                        "message_id": message_id
                    }
                else:
                    raise RuntimeError(error_msg)

            # 4. Send direct HTTP request to target agent
            import httpx

            # Extract base URL and construct proper endpoint
            # The target_agent_url might be in format: http://localhost:8080/writer-agent
            # But formation server expects: http://localhost:8080/agents/writer-agent/message

            # Parse the URL to extract base and agent parts
            parsed_url = urlparse(target_agent_url)

            # Extract the base URL (protocol + netloc)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # The agent ID should be the target_agent_id, not from the URL path
            # Formation server expects: /agents/{agent_id}/message
            endpoint_url = f"{base_url}/agents/{target_agent_id}/message"

            logger.debug(f"Sending HTTP request to: {endpoint_url}")
            if auth_type != AuthType.NONE:
                logger.debug(f"Using {auth_type} authentication for {target_agent_id}")

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=message_payload,
                    headers=headers
                )

                # 4. Handle HTTP response
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info(
                        f"External A2A message successful: {self.agent_id} -> {target_agent_id} "
                        f"(status: {response_data.get('status', 'unknown')})"
                    )

                    if message_type == "request" and wait_for_response:
                        return response_data
                    else:
                        return None

                else:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    logger.error(f"External A2A request failed: {error_msg}")

                    if message_type == "request" and wait_for_response:
                        return {
                            "status": "error",
                            "error": error_msg,
                            "message_id": message_id
                        }
                    else:
                        raise RuntimeError(f"External A2A request failed: {error_msg}")

        except httpx.TimeoutException:
            error_msg = f"Request timed out after {timeout} seconds"
            logger.error(f"External A2A message timed out: {error_msg}")
            if message_type == "request" and wait_for_response:
                return {
                    "status": "error",
                    "error": error_msg,
                    "message_id": message_id
                }
            else:
                raise RuntimeError(error_msg)

        except Exception as e:
            logger.error(f"External A2A message failed: {e}")
            if message_type == "request" and wait_for_response:
                return {
                    "status": "error",
                    "error": f"External message failed: {str(e)}",
                    "message_id": message_id
                }
            else:
                raise

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
        to this agent. It recognizes different collaboration patterns and handles
        them appropriately.

        Args:
            source_agent_id: The ID of the agent that sent the message
            message: The message content (can be text or structured data)
            message_type: Type of message ("request", "notification", "response")
            context: Optional context information from the sender
            message_id: Unique message ID for tracking

        Returns:
            Response data if this is a "request" message, otherwise None
        """
        # Check if this is a collaboration message with special handling
        collaboration_type = None
        if context and isinstance(context, dict):
            collaboration_type = context.get("collaboration_type")

        try:
            if collaboration_type == "consultation":
                return await self._handle_consultation_request(
                    source_agent_id, message, context, message_id
                )
            elif collaboration_type == "information_sharing":
                return await self._handle_information_sharing(
                    source_agent_id, message, context, message_id
                )
            elif collaboration_type == "peer_coordination":
                return await self._handle_peer_coordination(
                    source_agent_id, message, context, message_id
                )
            else:
                # Default handling for generic A2A messages
                return await self._handle_generic_a2a_message(
                    source_agent_id, message, message_type, context, message_id
                )

        except Exception as e:
            logger.error(f"Error handling A2A message: {e}")
            if message_type == "request":
                return {
                    "status": "error",
                    "error": f"Failed to process message: {str(e)}",
                    "agent_id": self.agent_id,
                    "message_id": message_id
                }
            return None

    async def _handle_consultation_request(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle a consultation request from another agent."""
        topic = context.get("topic", str(message))
        consultation_context = context.get("context", {})

        # Create a consultation-specific prompt
        prompt_parts = [
            f"CONSULTATION REQUEST from Agent {source_agent_id}:",
            f"Topic: {topic}",
            f"Question: {message}",
        ]

        if consultation_context:
            prompt_parts.append(f"Context: {consultation_context}")

        prompt_parts.extend([
            "",
            "Please provide expert advice and helpful guidance on this topic.",
            "Be specific, actionable, and professional in your response."
        ])

        consultation_prompt = "\n".join(prompt_parts)

        # Process the consultation through the agent's model directly
        raw_response = await self.model.chat(
            [{"role": "user", "content": consultation_prompt}]
        )

        # Debug: Log what we received
        logger.debug(f"Consultation raw response type: {type(raw_response)}")
        logger.debug(f"Consultation raw response: {str(raw_response)[:100]}...")

        # For A2A protocol compatibility, ensure we return a clean string
        # Handle different response formats and extract text content
        content = None

        try:
            if isinstance(raw_response, str):
                content = raw_response
                logger.debug("Consultation: Used string path")
            elif hasattr(raw_response, 'choices') and raw_response.choices:
                # Handle ChatCompletionResponse object
                choice = raw_response.choices[0]
                message_obj = choice.message
                logger.debug(f"Consultation choice type: {type(choice)}")
                logger.debug(f"Consultation message obj type: {type(message_obj)}")

                # Try multiple ways to extract content
                if hasattr(message_obj, 'content') and message_obj.content:
                    content = str(message_obj.content)
                    logger.debug("Consultation: Used message.content attribute")
                elif isinstance(message_obj, dict) and 'content' in message_obj:
                    content = str(message_obj['content'])
                    logger.debug("Consultation: Used message dict content")
                elif hasattr(message_obj, 'get') and message_obj.get('content'):
                    content = str(message_obj.get('content'))
                    logger.debug("Consultation: Used message.get content")
                else:
                    # Convert the message object to string and try to extract content
                    message_str = str(message_obj)
                    if "'content':" in message_str:
                        import re
                        match = re.search(r"'content':\s*'([^']*)'", message_str)
                        if match:
                            content = match.group(1)
                            logger.debug("Consultation: Extracted from string representation")
                        else:
                            content = f"Consultation response for topic: {topic}"
                            logger.warning("Consultation: Failed regex extraction")
                    else:
                        content = f"Consultation response for topic: {topic}"
                        logger.warning(f"Consultation: No content found in: {message_str[:200]}")
            elif isinstance(raw_response, dict) and 'choices' in raw_response:
                # Handle dict response format
                try:
                    content = str(raw_response['choices'][0]['message']['content'])
                    logger.debug("Consultation: Used dict path")
                except (KeyError, IndexError) as e:
                    logger.error(f"Consultation: Error extracting from dict: {e}")
                    content = f"Consultation response for topic: {topic}"
            else:
                # Unknown format
                content = f"Consultation response for topic: {topic}"
                logger.warning(f"Consultation: Unknown response format: {type(raw_response)}")

        except Exception as e:
            logger.error(f"Consultation: Content extraction error: {e}")
            content = f"Consultation response for topic: {topic}"

        # Ensure content is a valid string
        if not content or not isinstance(content, str):
            content = f"Consultation response for topic: {topic}"
            logger.warning("Consultation: Used fallback content due to extraction failure")

        if not content.strip():
            content = f"Consultation response for topic: {topic}"
            logger.warning("Consultation: Used fallback content due to empty result")

        logger.debug(f"Consultation final content: {content[:100]}...")

        logger.info(
            f"Agent {self.agent_id} provided consultation to {source_agent_id} "
            f"on topic: {topic}"
        )

        response_dict = {
            "status": "success",
            "response": content,  # Clean string for A2A protocol compatibility
            "consultation_topic": topic,
            "expert_agent": self.agent_id,
            "message_id": message_id
        }

        return response_dict

    async def _handle_information_sharing(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None
    ) -> None:
        """Handle information sharing notification from another agent."""
        topic = context.get("topic", "general")
        relevance_reason = context.get("relevance_reason")

        # Log the shared information
        log_parts = [
            f"Agent {self.agent_id} received shared information from {source_agent_id}",
            f"Topic: {topic}",
            f"Content: {message}"
        ]

        if relevance_reason:
            log_parts.append(f"Relevance: {relevance_reason}")

        logger.info(" | ".join(log_parts))

        # Optionally store the shared information in memory
        if self.overlord and hasattr(self.overlord, "add_to_buffer_memory"):
            try:
                await self.overlord.add_to_buffer_memory(
                    message=f"Shared info from {source_agent_id}: {message}",
                    metadata={
                        "type": "shared_information",
                        "source_agent": source_agent_id,
                        "topic": topic,
                        "relevance_reason": relevance_reason
                    },
                    agent_id=self.agent_id
                )
            except Exception as e:
                logger.warning(f"Failed to store shared information: {e}")

        return None  # Notifications don't return responses

    async def _handle_peer_coordination(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle peer coordination request from another agent."""
        coordination_type = context.get("coordination_type", "sync")
        details = context.get("details", {})

        # Create coordination-specific response based on type
        if coordination_type == "handoff":
            response_content = await self._handle_task_handoff(source_agent_id, details)
        elif coordination_type == "sync":
            response_content = await self._handle_synchronization(source_agent_id, details)
        elif coordination_type == "parallel":
            response_content = await self._handle_parallel_coordination(source_agent_id, details)
        else:
            response_content = f"Acknowledged coordination request: {coordination_type}"

        logger.info(
            f"Agent {self.agent_id} coordinated with {source_agent_id} "
            f"({coordination_type})"
        )

        return {
            "status": "success",
            "response": response_content,
            "coordination_type": coordination_type,
            "coordinated_with": self.agent_id,
            "message_id": message_id
        }

    async def _handle_task_handoff(
        self, source_agent_id: str, details: Dict[str, Any]
    ) -> str:
        """Handle a task handoff coordination."""
        task = details.get("task", "Unknown task")
        next_step = details.get("next_step", "Continue work")
        artifacts = details.get("artifacts", [])

        response_parts = [
            f"Task handoff acknowledged from {source_agent_id}",
            f"Completed task: {task}",
            f"Next step: {next_step}"
        ]

        if artifacts:
            response_parts.append(f"Received artifacts: {', '.join(artifacts)}")

        response_parts.append("Ready to proceed with next phase.")

        return "\n".join(response_parts)

    async def _handle_synchronization(
        self, source_agent_id: str, details: Dict[str, Any]
    ) -> str:
        """Handle a synchronization coordination."""
        sync_point = details.get("sync_point", "general")
        status = details.get("status", "in_progress")

        return (
            f"Synchronization with {source_agent_id} at {sync_point}. "
            f"My status: {status}. Ready for next coordinated step."
        )

    async def _handle_parallel_coordination(
        self, source_agent_id: str, details: Dict[str, Any]
    ) -> str:
        """Handle parallel work coordination."""
        work_area = details.get("work_area", "general")
        dependencies = details.get("dependencies", [])

        response_parts = [
            f"Parallel coordination with {source_agent_id} on {work_area}"
        ]

        if dependencies:
            response_parts.append(f"Shared dependencies: {', '.join(dependencies)}")

        response_parts.append("Coordinating parallel execution.")

        return "\n".join(response_parts)

    async def _handle_generic_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        message_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Handle generic A2A messages (fallback for non-collaboration patterns)."""
        if message_type == "request":
            # For generic requests, try to process using the agent's model
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

    async def request_consultation(
        self,
        target_agent_id: str,
        topic: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Request consultation/help from another agent on a specific topic.

        This is a core collaboration pattern where one agent asks another for
        assistance, advice, or expertise on a particular subject.

        Args:
            target_agent_id: The ID of the agent to consult
            topic: The subject matter needing consultation
            context: Optional additional context for the consultation
            timeout: Maximum time to wait for response

        Returns:
            Consultation response with advice/help, or None if failed

        Example:
            >>> response = await agent.request_consultation(
            ...     target_agent_id="security-expert",
            ...     topic="Best practices for API authentication",
            ...     context={"project": "user-management-api"}
            ... )
        """
        consultation_data = {
            "collaboration_type": "consultation",
            "topic": topic,
            "context": context or {},
            "requester_id": self.agent_id
        }

        try:
            response = await self.send_a2a_message(
                target_agent_id=target_agent_id,
                message=topic,
                message_type="request",
                context=consultation_data,
                wait_for_response=True,
                timeout=timeout
            )

            if response and response.get("status") == "success":
                logger.info(
                    f"Agent {self.agent_id} received consultation from {target_agent_id} "
                    f"on topic: {topic}"
                )
                return response
            else:
                logger.warning(
                    f"Consultation failed: {self.agent_id} -> {target_agent_id} "
                    f"on topic: {topic}"
                )
                return None

        except Exception as e:
            logger.error(f"Consultation error: {e}")
            return None

    async def share_information(
        self,
        target_agent_id: str,
        information: Union[str, Dict[str, Any]],
        topic: str,
        relevance_reason: Optional[str] = None
    ) -> bool:
        """
        Proactively share information with another agent.

        This collaboration pattern allows agents to share relevant findings,
        insights, or data that might be useful for other agents' work.

        Args:
            target_agent_id: The ID of the agent to share information with
            information: The information content to share
            topic: The topic/category of the information
            relevance_reason: Optional explanation of why this is relevant

        Returns:
            True if information was shared successfully, False otherwise

        Example:
            >>> success = await agent.share_information(
            ...     target_agent_id="research-agent",
            ...     information="New security vulnerability found in library X",
            ...     topic="security_alerts",
            ...     relevance_reason="You're working on dependency analysis"
            ... )
        """
        sharing_data = {
            "collaboration_type": "information_sharing",
            "topic": topic,
            "relevance_reason": relevance_reason,
            "shared_by": self.agent_id,
            "timestamp": datetime.datetime.now().isoformat()
        }

        try:
            await self.send_a2a_message(
                target_agent_id=target_agent_id,
                message=information,
                message_type="notification",
                context=sharing_data,
                wait_for_response=False
            )

            logger.info(
                f"Agent {self.agent_id} shared information with {target_agent_id} "
                f"on topic: {topic}"
            )
            return True

        except Exception as e:
            logger.error(f"Information sharing error: {e}")
            return False

    async def register_expertise(
        self,
        expertise_areas: List[str],
        proficiency_levels: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Register areas of expertise with the overlord for discovery by other agents.

        This allows agents to declare their specializations so other agents
        can find and consult them on relevant topics.

        Args:
            expertise_areas: List of topics/domains this agent has expertise in
            proficiency_levels: Optional mapping of area -> proficiency level
                ("novice", "intermediate", "expert", "master")

        Returns:
            True if expertise was registered successfully

        Example:
            >>> await agent.register_expertise(
            ...     expertise_areas=["machine_learning", "data_analysis"],
            ...     proficiency_levels={
            ...         "machine_learning": "expert",
            ...         "data_analysis": "master"
            ...     }
            ... )
        """
        if not self.overlord or not hasattr(self.overlord, 'register_agent_expertise'):
            logger.warning("Overlord does not support expertise registry")
            return False

        try:
            return await self.overlord.register_agent_expertise(
                agent_id=self.agent_id,
                expertise_areas=expertise_areas,
                proficiency_levels=proficiency_levels or {}
            )
        except Exception as e:
            logger.error(f"Expertise registration error: {e}")
            return False

    async def find_expert(
        self,
        topic: str,
        min_proficiency: str = "intermediate"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Find agents with expertise in a specific topic.

        This method helps agents discover other agents who can provide
        expert consultation on particular subjects.

        Args:
            topic: The topic/domain to find experts for
            min_proficiency: Minimum required proficiency level

        Returns:
            Dict mapping agent_id to expert information including proficiency

        Example:
            >>> experts = await agent.find_expert(
            ...     topic="security",
            ...     min_proficiency="expert"
            ... )
            >>> print(experts)
            {
                "security-agent": {
                    "proficiency": "master",
                    "description": "Cybersecurity specialist",
                    "expertise_areas": ["security", "penetration_testing"]
                }
            }
        """
        if not self.overlord or not hasattr(self.overlord, 'find_experts'):
            return {}

        try:
            return await self.overlord.find_experts(
                topic=topic,
                min_proficiency=min_proficiency,
                requesting_agent_id=self.agent_id
            )
        except Exception as e:
            logger.error(f"Expert discovery error: {e}")
            return {}

    async def coordinate_with_peer(
        self,
        peer_agent_id: str,
        coordination_type: str,
        details: Dict[str, Any],
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Coordinate work with a peer agent on interdependent tasks.

        This pattern enables agents to synchronize their work when they're
        working on related or dependent tasks.

        Args:
            peer_agent_id: The ID of the peer agent to coordinate with
            coordination_type: Type of coordination ("sync", "handoff", "parallel")
            details: Coordination details and context
            timeout: Maximum time to wait for coordination response

        Returns:
            Coordination response or None if failed

        Example:
            >>> response = await agent.coordinate_with_peer(
            ...     peer_agent_id="deployment-agent",
            ...     coordination_type="handoff",
            ...     details={
            ...         "task": "API testing complete",
            ...         "next_step": "deployment",
            ...         "artifacts": ["test_results.json", "coverage_report.html"]
            ...     }
            ... )
        """
        coordination_data = {
            "collaboration_type": "peer_coordination",
            "coordination_type": coordination_type,
            "details": details,
            "coordinator_id": self.agent_id
        }

        try:
            response = await self.send_a2a_message(
                target_agent_id=peer_agent_id,
                message=f"Coordination request: {coordination_type}",
                message_type="request",
                context=coordination_data,
                wait_for_response=True,
                timeout=timeout
            )

            if response and response.get("status") == "success":
                logger.info(
                    f"Agent {self.agent_id} coordinated with {peer_agent_id} "
                    f"({coordination_type})"
                )
                return response
            else:
                logger.warning(
                    f"Coordination failed: {self.agent_id} -> {peer_agent_id} "
                    f"({coordination_type})"
                )
                return None

        except Exception as e:
            logger.error(f"Coordination error: {e}")
            return None
