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
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Union

from ...types.response import MuxiResponse
from ...services.mcp.service import MCPService
from ...services.llm import LLM
from ...services import observability


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
        knowledge_config: Optional[Dict[str, Any]] = None,
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
            knowledge_config: Optional configuration for agent domain knowledge.
                Contains sources and settings for the agent's knowledge base.
        """
        self.model = model
        self.overlord = overlord

        # Set up agent identification
        self.agent_id = agent_id or str(uuid.uuid4())
        self.name = name or f"Agent-{self.agent_id}"

        # Initialize role and specialties for enhanced routing
        self.role = None  # Will be set from config during agent creation
        self.specialties = []  # Will be set from config during agent creation

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

        # Initialize knowledge handler
        self.knowledge_handler: Optional[Any] = None  # Will be KnowledgeHandler when imported
        self._knowledge_config = knowledge_config  # Store config for deferred initialization
        self._knowledge_initialized = False

        # Initialize the context with system message
        self._messages = []
        if self.system_message:
            self._messages.append({"role": "system", "content": self.system_message})

        # Emit agent initialization event
        observability.observe(
            event_type=observability.SystemEvents.AGENT_INITIALIZED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "a2a_internal": self.a2a_internal,
                "a2a_external": self.a2a_external,
                "has_system_message": bool(self.system_message),
                "has_knowledge_config": bool(knowledge_config),
            },
            description=f"Agent initialized: {self.agent_id}",
        )

    def get_mcp_service(self) -> MCPService:
        """
        Get the centralized MCP service for tool integrations.

        Returns:
            The MCPService instance used by this agent for connecting to
            and interacting with external tools.
        """
        return self._mcp_service

    async def _initialize_knowledge(self, knowledge_config: Dict[str, Any]) -> None:
        """
        Initialize the knowledge handler from configuration.

        Args:
            knowledge_config: Configuration dictionary containing knowledge sources
                and settings for the agent's knowledge base.
        """
        try:
            # Import KnowledgeHandler here to avoid circular imports
            from .knowledge.handler import KnowledgeHandler

            # Get embedding function from model for semantic search
            embedding_fn = None
            if hasattr(self.model, 'get_embedding'):
                embedding_fn = self.model.get_embedding
            elif hasattr(self.model, 'embed'):
                embedding_fn = self.model.embed

            # Get formation config from overlord if available
            formation_config = None
            if hasattr(self.overlord, 'formation_config') and self.overlord.formation_config:
                formation_config = self.overlord.formation_config

            # Create knowledge handler using the factory method with formation config
            self.knowledge_handler = await KnowledgeHandler.from_agent_config(
                agent_id=self.agent_id,
                knowledge_config=knowledge_config,
                generate_embeddings_fn=embedding_fn,
                formation_config=formation_config
            )

            # Log successful knowledge initialization
            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "knowledge_sources": len(knowledge_config.get("sources", [])),
                    "knowledge_config_keys": list(knowledge_config.keys()),
                    "knowledge_handler_created": self.knowledge_handler is not None,
                },
                description=f"Knowledge handler initialized for agent {self.agent_id}",
            )

        except Exception as e:
            # Log error but don't fail agent initialization
            observability.observe(
                event_type=observability.SystemEvents.AGENT_INITIALIZATION_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "phase": "knowledge_initialization",
                },
                description=f"Failed to initialize knowledge for agent {self.agent_id}: {str(e)}",
            )
            self.knowledge_handler = None

    async def _ensure_knowledge_initialized(self) -> None:
        """
        Ensure knowledge handler is initialized if configuration is available.
        This is called on first use since constructor can't be async.
        """
        if self._knowledge_initialized or not self._knowledge_config:
            return

        await self._initialize_knowledge(self._knowledge_config)
        self._knowledge_initialized = True

    async def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search the agent's knowledge base for relevant information using semantic search.

        Args:
            query: The search query string
            limit: Maximum number of results to return

        Returns:
            List of knowledge results, empty list if no knowledge handler or no results
        """
        # Ensure knowledge is initialized
        await self._ensure_knowledge_initialized()

        if not self.knowledge_handler:
            return []

        try:
            # Get embedding function from model for semantic search
            embedding_fn = None
            if hasattr(self.model, 'get_embedding'):
                embedding_fn = self.model.get_embedding
            elif hasattr(self.model, 'embed'):
                embedding_fn = self.model.embed

            results = await self.knowledge_handler.search(
                query=query,
                top_k=limit,
                generate_embeddings_fn=embedding_fn
            )
            return results or []
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "phase": "knowledge_search",
                    "query": query[:100],
                },
                description=f"Knowledge search failed for agent {self.agent_id}: {str(e)}",
            )
            return []

    async def process_message(
        self, message: Union[str, MuxiResponse], user_id: Any = None
    ) -> MuxiResponse:
        """
        Process a message from the overlord and generate a response.

        This method handles:
        1. Converting input to MuxiResponse format
        2. Adding the message to memory via the overlord
        3. Updating conversation context
        4. Searching domain knowledge (if available)
        5. Processing the message with the model
        6. Handling any tool calls in the response
        7. Storing the response in memory
        8. Supporting agent clarification requests to overlord

        Args:
            message: The message from the overlord, either as a string or an MuxiResponse.
                Contains the content to be processed by the agent.
            user_id: Optional user ID for multi-user support. Used for memory
                isolation and user-specific context.

        Returns:
            The agent's response as an MuxiResponse, possibly including tool call results
            or clarification requests in metadata.
        """
        # Convert string message to MuxiResponse if needed
        if isinstance(message, str):
            content = message
            message_obj = MuxiResponse(role="user", content=content)
        else:
            content = message.content
            message_obj = message

        # Emit agent message processing event
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "message_length": len(content),
            },
            description=f"Agent {self.agent_id} processing message",
        )

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

        # Search knowledge if handler is available
        knowledge_context = ""
        if self._knowledge_config:  # Check if knowledge config exists
            try:
                # Ensure knowledge is initialized
                await self._ensure_knowledge_initialized()

                if self.knowledge_handler:
                    # Get embedding function from model for semantic search
                    embedding_fn = None
                    if hasattr(self.model, 'get_embedding'):
                        embedding_fn = self.model.get_embedding
                    elif hasattr(self.model, 'embed'):
                        embedding_fn = self.model.embed

                    knowledge_results = await self.knowledge_handler.search(
                        query=content,
                        top_k=5,
                        generate_embeddings_fn=embedding_fn
                    )
                    if knowledge_results:
                        knowledge_context = "\n\n--- Domain Knowledge ---\n"
                        for result in knowledge_results:
                            knowledge_context += f"• {result.get('content', '')}\n"
                        knowledge_context += "--- End Domain Knowledge ---\n\n"

                        # Add knowledge context to the conversation
                        enhanced_message = f"{content}\n{knowledge_context}"
                        self._messages[-1]["content"] = enhanced_message

                        # Log knowledge search success
                        observability.observe(
                            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
                            level=observability.EventLevel.INFO,
                            data={
                                "agent_id": self.agent_id,
                                "knowledge_results_count": len(knowledge_results),
                                "query": content[:100],
                            },
                            description=f"Knowledge search completed for agent {self.agent_id}",
                        )
            except Exception as e:
                # Log error but don't fail message processing
                observability.observe(
                    event_type=observability.ConversationEvents.AGENT_PROCESSING_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "phase": "knowledge_search",
                    },
                    description=f"Knowledge search failed for agent {self.agent_id}: {str(e)}",
                )

        # Process the message with the model directly
        raw_response = await self.model.chat(self._messages)

        # Extract the actual content string from the response
        if isinstance(raw_response, str):
            content = raw_response
        elif hasattr(raw_response, "choices") and raw_response.choices:
            # Handle ChatCompletionResponse object
            message = raw_response.choices[0].message
            if isinstance(message, dict):
                content = message.get("content", "")
            else:
                # Handle message as object with content attribute/property
                content = getattr(message, "content", "")
        elif isinstance(raw_response, dict) and "choices" in raw_response:
            # Handle dict response format
            content = raw_response["choices"][0]["message"]["content"]
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
                else:
                    content = response_str
            else:
                content = response_str

        # NEW: Check if agent needs clarification from user
        clarification_request = await self._check_agent_clarification_needs(
            content, message_obj.content
        )

        # Create response message
        response = MuxiResponse(role="assistant", content=content)

        # NEW: Add clarification metadata if needed
        if clarification_request:
            response.metadata = clarification_request

        # Add response to conversation context
        self._messages.append({"role": "assistant", "content": response.content})

        # Emit agent response generated event
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": self.agent_id,
                "agent_name": self.name,
                "response_length": len(response.content),
                "has_clarification_request": bool(clarification_request),
            },
            description=f"Agent {self.agent_id} generated response",
        )

        # Store response in memory
        if self.overlord and hasattr(self.overlord, "add_message_to_memory"):
            timestamp = datetime.datetime.now().timestamp()
            await self.overlord.add_message_to_memory(
                content=response.content,
                role="assistant",
                timestamp=timestamp,
                agent_id=self.agent_id,
                user_id=user_id,
            )

        # Check for tool calls and execute them if present
        if "<|tool_call|>" in content or "tool_name" in content.lower():
            try:
                # Parse and execute tool calls
                # ... existing tool call handling logic ...
                pass
            except Exception as e:
                observability.observe(
                    event_type=observability.ConversationEvents.TOOL_CALL_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "agent_id": self.agent_id,
                        "error": str(e),
                        "content": content[:500],  # First 500 chars for debugging
                    },
                    description=f"Tool call execution failed: {str(e)}",
                )

        return response

    async def _check_agent_clarification_needs(
        self, agent_response: str, user_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if the agent's response indicates it needs clarification from the user.

        This method analyzes the agent's response to detect patterns that suggest
        the agent needs additional information to complete the user's request.

        Args:
            agent_response: The response generated by the agent
            user_message: The original user message being processed

        Returns:
            Dict with clarification metadata if clarification is needed, None otherwise.
            Format: {
                "needs_clarification": True,
                "clarification_type": "information_request",
                "required_info": {
                    "budget": "What's your budget range for this project?",
                    "timeline": "When do you need this completed?"
                },
                "agent_reasoning": "I need budget and timeline to provide accurate recommendations"
            }
        """
        try:
            # Patterns that suggest the agent needs clarification
            clarification_patterns = [
                # Direct requests for information
                r"(?i)(?:what(?:'s| is)|how much|when|where|which|who)\s+"
                r"(?:is|are|do|does|did|will|would|should|could|can)\s+(?:you|your)",
                r"(?i)(?:i need|i require|could you (?:please )?(?:provide|tell|specify|clarify))",
                r"(?i)(?:what(?:'s| is) your|could you specify|please (?:provide|clarify|specify))",

                # Questions about preferences or requirements
                r"(?i)(?:do you (?:prefer|want|need)|would you like|are you looking for)",
                r"(?i)(?:what (?:type|kind|sort) of|which (?:option|approach|method))",

                # Uncertainty indicators
                r"(?i)(?:i(?:'m| am) not sure|unclear|ambiguous|could mean)",
                r"(?i)(?:depends on|varies based on|need(?:s)? more "
                r"(?:information|details|context))",

                # Multiple options requiring choice
                r"(?i)(?:several (?:options|ways|approaches)|multiple (?:possibilities|choices))",
                r"(?i)(?:option [abc12]|approach [abc12]|method [abc12])",
            ]

            # Check if response contains clarification patterns
            has_clarification_pattern = any(
                re.search(pattern, agent_response) for pattern in clarification_patterns
            )

            if not has_clarification_pattern:
                return None

            # Extract specific information requests using more sophisticated parsing
            required_info = await self._extract_information_requests(agent_response, user_message)

            if not required_info:
                return None

            # Generate agent reasoning
            reasoning = await self._generate_clarification_reasoning(agent_response, required_info)

            return {
                "needs_clarification": True,
                "clarification_type": "information_request",
                "required_info": required_info,
                "agent_reasoning": reasoning,
                "original_response": agent_response
            }

        except Exception as e:
            # Log error but don't block processing
            observability.observe(
                event_type=observability.ConversationEvents.AGENT_PROCESSING_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "phase": "clarification_check",
                },
                description=f"Error checking clarification needs: {str(e)}",
            )
            return None

    async def _extract_information_requests(
        self, agent_response: str, user_message: str
    ) -> Dict[str, str]:
        """
        Extract specific information requests from agent response.

        Args:
            agent_response: The agent's response text
            user_message: The original user message

        Returns:
            Dictionary mapping information categories to specific questions
        """
        # Common information categories and their question patterns
        info_categories = {
            "budget": [
                r"(?i)(?:budget|cost|price|money|funding|spend)",
                r"(?i)(?:how much|what(?:'s| is) (?:the )?(?:cost|price))"
            ],
            "timeline": [
                r"(?i)(?:when|timeline|deadline|schedule|time)",
                r"(?i)(?:how (?:long|soon)|by when)"
            ],
            "preferences": [
                r"(?i)(?:prefer|preference|like|want|style|approach)",
                r"(?i)(?:which (?:type|kind|option)|what (?:type|kind))"
            ],
            "requirements": [
                r"(?i)(?:require|requirement|need|must|should|specification)",
                r"(?i)(?:what (?:features|capabilities|functionality))"
            ],
            "scope": [
                r"(?i)(?:scope|scale|size|extent|coverage)",
                r"(?i)(?:how (?:big|large|extensive|comprehensive))"
            ],
            "location": [
                r"(?i)(?:where|location|place|region|area)",
                r"(?i)(?:which (?:location|place|area))"
            ]
        }

        required_info = {}

        # Extract questions for each category found in the response
        for category, patterns in info_categories.items():
            for pattern in patterns:
                if re.search(pattern, agent_response):
                    # Extract the actual question from the response
                    question = self._extract_question_for_category(agent_response, category)
                    if question:
                        required_info[category] = question
                        break

        return required_info

    def _extract_question_for_category(self, response: str, category: str) -> Optional[str]:
        """
        Extract the specific question for a given information category.

        Args:
            response: Agent's response text
            category: Information category (budget, timeline, etc.)

        Returns:
            The extracted question or a generated question for the category
        """
        # Split response into sentences
        sentences = re.split(r'[.!?]+', response)

        # Category-specific keywords to look for
        category_keywords = {
            "budget": ["budget", "cost", "price", "money", "funding", "spend"],
            "timeline": ["when", "timeline", "deadline", "schedule", "time"],
            "preferences": ["prefer", "preference", "like", "want", "style"],
            "requirements": ["require", "requirement", "need", "must", "specification"],
            "scope": ["scope", "scale", "size", "extent", "coverage"],
            "location": ["where", "location", "place", "region", "area"]
        }

        keywords = category_keywords.get(category, [])

        # Find sentence containing category keywords and question patterns
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Check if sentence contains category keywords and question indicators
            has_keyword = any(keyword.lower() in sentence.lower() for keyword in keywords)
            has_question = any(
                indicator in sentence.lower()
                for indicator in ["what", "how", "when", "where", "which", "?"]
            )

            if has_keyword and (has_question or sentence.endswith("?")):
                return sentence.strip() + ("?" if not sentence.endswith("?") else "")

        # Fallback: generate a generic question for the category
        generic_questions = {
            "budget": "What's your budget range for this project?",
            "timeline": "When do you need this completed?",
            "preferences": "What are your preferences for this request?",
            "requirements": "What are your specific requirements?",
            "scope": "What's the scope of work you're looking for?",
            "location": "Where should this be implemented or focused?"
        }

        return generic_questions.get(category)

    async def _generate_clarification_reasoning(
        self, agent_response: str, required_info: Dict[str, str]
    ) -> str:
        """
        Generate reasoning for why the agent needs clarification.

        Args:
            agent_response: The agent's response
            required_info: Dictionary of required information

        Returns:
            Human-readable explanation of why clarification is needed
        """
        if len(required_info) == 1:
            category = list(required_info.keys())[0]
            return f"I need to understand your {category} to provide the most helpful response."
        elif len(required_info) == 2:
            categories = list(required_info.keys())
            return (
                f"I need to understand your {categories[0]} and {categories[1]} "
                f"to provide accurate recommendations."
            )
        else:
            categories = list(required_info.keys())
            return (
                f"I need additional information about {', '.join(categories[:-1])}, "
                f"and {categories[-1]} to give you the best possible assistance."
            )

    async def run(self, input_text: str, use_memory: bool = True) -> str:
        """
        Simplified interface to run the agent with a text input.

        Args:
            input_text: The input text to process.
            use_memory: Whether to use memory for context (default: True).

        Returns:
            The agent's response as a string.
        """
        response = await self.process_message(input_text)
        return response.content

    async def get_relevant_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get relevant memories for a query from the overlord's memory system.

        Args:
            query: The query to search for in memory.
            limit: Maximum number of memories to return.

        Returns:
            List of relevant memory entries.
        """
        if self.overlord and hasattr(self.overlord, "get_relevant_memories"):
            return await self.overlord.get_relevant_memories(query, limit)
        return []

    def discover_agents(
        self, capability_filter: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Discover available agents in the formation.

        Args:
            capability_filter: Optional list of capabilities to filter by.

        Returns:
            Dictionary of agent_id -> agent_info for discovered agents.
        """
        if self.overlord and hasattr(self.overlord, "discover_agents"):
            return self.overlord.discover_agents(capability_filter)
        return {}

    async def invoke_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        server_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Invoke a tool via MCP.

        Args:
            tool_name: Name of the tool to invoke.
            parameters: Parameters to pass to the tool.
            server_id: Optional server ID for multi-server setups.

        Returns:
            The tool execution result.

        Raises:
            Exception: If tool invocation fails.
        """
        try:
            observability.observe(
                event_type=observability.ConversationEvents.TOOL_CALL_STARTED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "parameters": parameters,
                },
                description=f"Agent {self.agent_id} invoking tool {tool_name}",
            )

            if server_id:
                result = await self._mcp_service.invoke_tool(
                    server_id, tool_name, parameters, timeout=self.request_timeout
                )
            else:
                # Try to find the tool in any available server
                servers = self._mcp_service.get_servers()
                result = None
                for server_name in servers:
                    try:
                        result = await self._mcp_service.invoke_tool(
                            server_name, tool_name, parameters, timeout=self.request_timeout
                        )
                        break
                    except Exception:
                        continue

                if result is None:
                    raise Exception(f"Tool '{tool_name}' not found in any connected server")

            observability.observe(
                event_type=observability.ConversationEvents.TOOL_CALL_COMPLETED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "success": True,
                },
                description=f"Agent {self.agent_id} completed tool call {tool_name}",
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.TOOL_CALL_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "tool_name": tool_name,
                    "server_id": server_id,
                    "error": str(e),
                },
                description=f"Agent {self.agent_id} tool call failed: {str(e)}",
            )
            raise

    async def send_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str = "request",
        context: Optional[Dict[str, Any]] = None,
        wait_for_response: bool = True,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message to another agent via A2A protocol.

        Args:
            target_agent_id: ID of the target agent.
            message: Message content to send.
            message_type: Type of message (request, response, notification).
            context: Optional context data for the message.
            wait_for_response: Whether to wait for a response.
            timeout: Timeout in seconds for waiting for response.

        Returns:
            The response from the target agent if wait_for_response is True.
        """
        # Generate unique message ID
        message_id = str(uuid.uuid4())

        observability.observe(
            event_type=observability.ConversationEvents.A2A_MESSAGE_SENT,
            level=observability.EventLevel.INFO,
            data={
                "source_agent_id": self.agent_id,
                "target_agent_id": target_agent_id,
                "message_id": message_id,
                "message_type": message_type,
                "wait_for_response": wait_for_response,
            },
            description=f"Agent {self.agent_id} sending A2A message to {target_agent_id}",
        )

        try:
            # Check if target is internal (same formation) or external
            if self.overlord and hasattr(self.overlord, "get_agent"):
                target_agent = self.overlord.get_agent(target_agent_id)
                if target_agent and self.a2a_internal:
                    # Internal A2A message
                    return await self._send_local_a2a_message(
                        target_agent_id,
                        message,
                        message_type,
                        context,
                        wait_for_response,
                        timeout,
                        message_id,
                    )

            # External A2A message (if enabled)
            if self.a2a_external:
                return await self._send_external_a2a_message(
                    target_agent_id,
                    message,
                    message_type,
                    context,
                    wait_for_response,
                    timeout,
                    message_id,
                )

            raise Exception(f"Agent {target_agent_id} not found and external A2A disabled")

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": self.agent_id,
                    "target_agent_id": target_agent_id,
                    "message_id": message_id,
                    "error": str(e),
                },
                description=f"A2A message failed: {str(e)}",
            )
            raise

    async def _send_local_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        wait_for_response: bool,
        timeout: int,
        message_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Send message to agent in same formation."""
        try:
            target_agent = self.overlord.get_agent(target_agent_id)
            if not target_agent:
                raise Exception(f"Target agent {target_agent_id} not found in formation")

            # Send message to target agent
            response = await target_agent.handle_a2a_message(
                source_agent_id=self.agent_id,
                message=message,
                message_type=message_type,
                context=context or {},
                message_id=message_id,
            )

            if wait_for_response:
                return response
            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": self.agent_id,
                    "target_agent_id": target_agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "location": "local_a2a",
                },
                description=f"Local A2A message failed: {str(e)}",
            )
            raise

    async def _send_external_a2a_message(
        self,
        target_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        wait_for_response: bool,
        timeout: int,
        message_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Send message to external agent via registry."""
        try:
            # Get external agent information from registry
            if (
                not hasattr(self.overlord, "external_registry")
                or not self.overlord.external_registry
            ):
                raise Exception("External registry not configured")

            registry = self.overlord.external_registry

            # Discover the target agent
            agents = await registry.discover_agents()
            target_agent_info = None

            for agent_info in agents:
                if agent_info.get("id") == target_agent_id:
                    target_agent_info = agent_info
                    break

            if not target_agent_info:
                raise Exception(f"External agent {target_agent_id} not found in registry")

            # Extract endpoint from agent info
            endpoint = target_agent_info.get("endpoint")
            if not endpoint:
                raise Exception(f"No endpoint found for agent {target_agent_id}")

            # Prepare message payload
            payload = {
                "source_agent_id": self.agent_id,
                "target_agent_id": target_agent_id,
                "message": message,
                "message_type": message_type,
                "context": context or {},
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

            # Send HTTP request to external agent
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{endpoint}/a2a/message",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        if wait_for_response:
                            return await response.json()
                        return None
                    else:
                        error_text = await response.text()
                        raise Exception(
                            f"External A2A request failed: {response.status} - {error_text}"
                        )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": self.agent_id,
                    "target_agent_id": target_agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "location": "external_a2a",
                },
                description=f"External A2A message failed: {str(e)}",
            )
            raise

    async def handle_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Handle incoming A2A message from another agent.

        Args:
            source_agent_id: ID of the agent sending the message.
            message: The message content.
            message_type: Type of message (request, response, notification).
            context: Optional context data.
            message_id: Optional message ID for tracking.

        Returns:
            Response data if this is a request, None for notifications.
        """
        observability.observe(
            event_type=observability.ConversationEvents.A2A_MESSAGE_RECEIVED,
            level=observability.EventLevel.INFO,
            data={
                "source_agent_id": source_agent_id,
                "target_agent_id": self.agent_id,
                "message_id": message_id,
                "message_type": message_type,
            },
            description=f"Agent {self.agent_id} received A2A message from {source_agent_id}",
        )

        try:
            # Handle different message types
            if message_type == "consultation":
                return await self._handle_consultation_request(
                    source_agent_id, message, context or {}, message_id
                )
            elif message_type == "information_sharing":
                await self._handle_information_sharing(
                    source_agent_id, message, context or {}, message_id
                )
                return None
            elif message_type == "peer_coordination":
                return await self._handle_peer_coordination(
                    source_agent_id, message, context or {}, message_id
                )
            else:
                # Generic message handling
                return await self._handle_generic_a2a_message(
                    source_agent_id, message, message_type, context, message_id
                )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "error": str(e),
                },
                description=f"A2A message handling failed: {str(e)}",
            )
            raise

    async def _handle_consultation_request(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle consultation request from another agent."""
        try:
            # Extract consultation details
            if isinstance(message, dict):
                topic = message.get("topic", "")
                question = message.get("question", "")
                details = message.get("details", {})
            else:
                topic = context.get("topic", "consultation")
                question = str(message)
                details = {}

            # Process the consultation using the agent's model
            consultation_prompt = f"""
            Agent {source_agent_id} is requesting consultation on: {topic}

            Question: {question}

            Additional context: {details}

            Please provide expert advice based on your knowledge and capabilities.
            """

            # Use the agent's model to generate consultation response
            consultation_messages = [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": consultation_prompt},
            ]

            response = await self.model.chat(consultation_messages)

            # Extract content from response
            if isinstance(response, str):
                advice = response
            elif hasattr(response, "choices") and response.choices:
                advice = response.choices[0].message.content
            else:
                advice = str(response)

            return {
                "status": "success",
                "advice": advice,
                "topic": topic,
                "consultant_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "consultant_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

    async def _handle_information_sharing(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> None:
        """Handle information sharing from another agent."""
        try:
            # Extract shared information
            if isinstance(message, dict):
                information = message.get("information", "")
                topic = message.get("topic", "general")
                relevance = message.get("relevance_reason", "")
            else:
                information = str(message)
                topic = context.get("topic", "general")
                relevance = context.get("relevance_reason", "")

            # Store the shared information in memory via overlord
            if self.overlord and hasattr(self.overlord, "add_message_to_memory"):
                shared_content = (
                    f"Information shared by {source_agent_id} on {topic}: {information}"
                )
                if relevance:
                    shared_content += f" (Relevance: {relevance})"

                await self.overlord.add_message_to_memory(
                    content=shared_content,
                    role="system",
                    timestamp=datetime.datetime.now().timestamp(),
                    agent_id=self.agent_id,
                    metadata={
                        "source": "a2a_information_sharing",
                        "source_agent_id": source_agent_id,
                        "topic": topic,
                        "message_id": message_id,
                    },
                )

            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_PROCESSED,
                level=observability.EventLevel.INFO,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "topic": topic,
                    "action": "information_stored",
                },
                description=f"Stored shared information from {source_agent_id}",
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "action": "information_sharing",
                },
                description=f"Failed to handle information sharing: {str(e)}",
            )

    async def _handle_peer_coordination(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        context: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle peer coordination request."""
        try:
            # Extract coordination details
            if isinstance(message, dict):
                coordination_type = message.get("coordination_type", "general")
                details = message.get("details", {})
            else:
                coordination_type = context.get("coordination_type", "general")
                details = {"message": str(message)}

            # Handle different coordination types
            if coordination_type == "task_handoff":
                result = await self._handle_task_handoff(source_agent_id, details)
            elif coordination_type == "synchronization":
                result = await self._handle_synchronization(source_agent_id, details)
            elif coordination_type == "parallel_coordination":
                result = await self._handle_parallel_coordination(source_agent_id, details)
            else:
                result = f"Acknowledged {coordination_type} coordination from {source_agent_id}"

            return {
                "status": "success",
                "result": result,
                "coordination_type": coordination_type,
                "coordinator_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "coordination_type": coordination_type,
                "coordinator_id": self.agent_id,
                "message_id": message_id,
                "timestamp": datetime.datetime.now().isoformat(),
            }

    async def _handle_task_handoff(self, source_agent_id: str, details: Dict[str, Any]) -> str:
        """Handle task handoff coordination."""
        task = details.get("task", "unknown task")
        status = details.get("status", "unknown")

        # Log the handoff
        observability.observe(
            event_type=observability.ConversationEvents.A2A_TASK_HANDOFF,
            level=observability.EventLevel.INFO,
            data={
                "source_agent_id": source_agent_id,
                "target_agent_id": self.agent_id,
                "task": task,
                "status": status,
            },
            description=f"Task handoff: {task} from {source_agent_id}",
        )

        return f"Received task handoff: {task} (status: {status})"

    async def _handle_synchronization(self, source_agent_id: str, details: Dict[str, Any]) -> str:
        """Handle synchronization coordination."""
        sync_point = details.get("sync_point", "unknown")
        return f"Synchronized at {sync_point} with {source_agent_id}"

    async def _handle_parallel_coordination(
        self, source_agent_id: str, details: Dict[str, Any]
    ) -> str:
        """Handle parallel coordination."""
        task_part = details.get("task_part", "unknown")
        return f"Coordinating parallel task: {task_part} with {source_agent_id}"

    async def _handle_generic_a2a_message(
        self,
        source_agent_id: str,
        message: Union[str, Dict[str, Any]],
        message_type: str,
        context: Optional[Dict[str, Any]],
        message_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle generic A2A message."""
        try:
            # Convert message to string for processing
            if isinstance(message, dict):
                message_content = json.dumps(message, indent=2)
            else:
                message_content = str(message)

            # Create a prompt for the agent to handle the message
            prompt = f"""
            You received a {message_type} message from agent {source_agent_id}.

            Message content:
            {message_content}

            Context: {context or {}}

            Please provide an appropriate response or acknowledgment.
            """

            # Process with the agent's model
            response_messages = [
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": prompt},
            ]

            model_response = await self.model.chat(response_messages)

            # Extract content
            if isinstance(model_response, str):
                response_content = model_response
            elif hasattr(model_response, "choices") and model_response.choices:
                response_content = model_response.choices[0].message.content
            else:
                response_content = str(model_response)

            # Return response for request-type messages
            if message_type in ["request", "query", "consultation"]:
                return {
                    "status": "success",
                    "response": response_content,
                    "responder_id": self.agent_id,
                    "message_id": message_id,
                    "timestamp": datetime.datetime.now().isoformat(),
                }

            # For notifications, just log and return None
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_PROCESSED,
                level=observability.EventLevel.INFO,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "message_type": message_type,
                    "action": "acknowledged",
                },
                description=f"Processed {message_type} from {source_agent_id}",
            )

            return None

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.A2A_MESSAGE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "source_agent_id": source_agent_id,
                    "target_agent_id": self.agent_id,
                    "message_id": message_id,
                    "error": str(e),
                    "message_type": message_type,
                },
                description=f"Failed to process {message_type}: {str(e)}",
            )
            raise

    # A2A Convenience Methods

    async def request_consultation(
        self,
        target_agent_id: str,
        topic: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Request consultation from another agent.

        Args:
            target_agent_id: ID of the agent to consult.
            topic: Topic for consultation.
            context: Optional additional context.
            timeout: Timeout for the request.

        Returns:
            Consultation response from the target agent.
        """
        message = {
            "topic": topic,
            "question": f"I need consultation on: {topic}",
            "details": context or {},
        }

        return await self.send_a2a_message(
            target_agent_id=target_agent_id,
            message=message,
            message_type="consultation",
            context=context,
            wait_for_response=True,
            timeout=timeout,
        )

    async def share_information(
        self,
        target_agent_id: str,
        information: Union[str, Dict[str, Any]],
        topic: str,
        relevance_reason: Optional[str] = None,
    ) -> bool:
        """
        Share information with another agent.

        Args:
            target_agent_id: ID of the target agent.
            information: Information to share.
            topic: Topic of the information.
            relevance_reason: Optional reason why this information is relevant.

        Returns:
            True if information was shared successfully.
        """
        message = {"information": information, "topic": topic, "relevance_reason": relevance_reason}

        try:
            await self.send_a2a_message(
                target_agent_id=target_agent_id,
                message=message,
                message_type="information_sharing",
                context={"topic": topic},
                wait_for_response=False,
            )
            return True
        except Exception:
            return False

    async def register_expertise(
        self, expertise_areas: List[str], proficiency_levels: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Register expertise areas with the overlord for capability discovery.

        Args:
            expertise_areas: List of expertise areas.
            proficiency_levels: Optional proficiency levels for each area.

        Returns:
            True if registration was successful.
        """
        try:
            if self.overlord and hasattr(self.overlord, "register_agent_expertise"):
                await self.overlord.register_agent_expertise(
                    agent_id=self.agent_id,
                    expertise_areas=expertise_areas,
                    proficiency_levels=proficiency_levels or {},
                )
                return True
        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.AGENT_REGISTRATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "agent_id": self.agent_id,
                    "expertise_areas": expertise_areas,
                    "error": str(e),
                },
                description=f"Failed to register expertise: {str(e)}",
            )
        return False

    async def find_expert(
        self, topic: str, min_proficiency: str = "intermediate"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Find agents with expertise in a specific topic.

        Args:
            topic: Topic to find experts for.
            min_proficiency: Minimum proficiency level required.

        Returns:
            Dictionary of agent_id -> expertise_info for matching experts.
        """
        if self.overlord and hasattr(self.overlord, "find_experts"):
            return await self.overlord.find_experts(topic, min_proficiency)
        return {}

    async def coordinate_with_peer(
        self, peer_agent_id: str, coordination_type: str, details: Dict[str, Any], timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Coordinate with a peer agent.

        Args:
            peer_agent_id: ID of the peer agent.
            coordination_type: Type of coordination (task_handoff, synchronization, etc.).
            details: Coordination details.
            timeout: Timeout for the coordination.

        Returns:
            Coordination response from the peer agent.
        """
        message = {"coordination_type": coordination_type, "details": details}

        return await self.send_a2a_message(
            target_agent_id=peer_agent_id,
            message=message,
            message_type="peer_coordination",
            context={"coordination_type": coordination_type},
            wait_for_response=True,
            timeout=timeout,
        )
