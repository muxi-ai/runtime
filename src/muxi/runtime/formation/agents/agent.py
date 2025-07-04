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
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from ...datatypes.response import MuxiResponse
from ...datatypes.intent import IntentType, IntentDetectionContext
from ...services.mcp.service import MCPService
from ...services.llm import LLM
from ...services.intent import IntentDetectionService
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
        self._current_user_id = None  # Track current user for tool invocations
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
            if hasattr(self.model, "get_embedding"):
                embedding_fn = self.model.get_embedding
            elif hasattr(self.model, "embed"):
                embedding_fn = self.model.embed

            # Get formation config from overlord if available
            formation_config = None
            if hasattr(self.overlord, "formation_config") and self.overlord.formation_config:
                formation_config = self.overlord.formation_config

            # Create knowledge handler using the factory method with formation config
            self.knowledge_handler = await KnowledgeHandler.from_agent_config(
                agent_id=self.agent_id,
                knowledge_config=knowledge_config,
                generate_embeddings_fn=embedding_fn,
                formation_config=formation_config,
                short_term_memory=getattr(self.overlord, "buffer_memory", None),
                auto_inject_knowledge=True,
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

    async def search_knowledge(
        self,
        query: str,
        limit: int = 5,
        include_memory: bool = True,
        unified: bool = False,
        # Enhanced coordination features (always enabled)
        deduplicate: bool = True,
        context_budget: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """
        Search the agent's knowledge base and memory for relevant information.

        This method provides unified search across both domain knowledge sources
        and conversational memory, with enhanced coordination features always enabled.

        Args:
            query: The search query string
            limit: Maximum number of results to return per source
            include_memory: Whether to include memory search results
            unified: Return full dictionary format with separate source results
            deduplicate: Remove duplicate content between sources (always enabled)
            context_budget: Total context budget to allocate across sources

        Returns:
            List of unified results (default) or dictionary with separate source results
        """
        if not self.knowledge_handler:
            return {"knowledge": [], "memory": [], "unified": []} if unified else []

        try:
            # Smart query routing (always enabled)
            strategy = await self._analyze_query_for_routing(query)

            # Dynamic context budget management (always enabled)
            if context_budget:
                knowledge_limit, memory_limit = self._allocate_context_budget(
                    context_budget, strategy, limit
                )
            else:
                # Use strategy-based limits when no budget specified
                if strategy == "knowledge_only":
                    knowledge_limit, memory_limit = limit, 0
                elif strategy == "memory_only":
                    knowledge_limit, memory_limit = 0, limit
                else:  # strategy == "both"
                    knowledge_limit, memory_limit = limit, limit

            # Perform unified search with allocated limits
            results = await self.knowledge_handler.search_unified(
                query=query,
                knowledge_limit=knowledge_limit,
                memory_limit=memory_limit if include_memory else 0,
                include_memory=include_memory,
                session_id=session_id,
            )

            # Content deduplication (always enabled)
            if deduplicate and include_memory:
                results = self._deduplicate_results(results)

            # Enhanced unified ranking (always enabled)
            if include_memory:
                enhanced_unified = self._create_enhanced_unified_ranking(
                    knowledge_results=results.get("knowledge", []),
                    memory_results=results.get("memory", []),
                    query=query,
                    strategy=strategy,
                    budget=context_budget or (limit * 2),
                )
                results["unified"] = enhanced_unified

            # Return format based on unified parameter
            if unified:
                return results
            else:
                # Return enhanced unified results as the default
                return results.get("unified", results.get("knowledge", []))

        except Exception as e:
            self.logger.error(f"Error in enhanced knowledge search: {e}")
            return {"knowledge": [], "memory": [], "unified": []} if unified else []

    async def _analyze_query_for_routing(self, query: str) -> str:
        """
        Analyze query to determine optimal search strategy.

        Uses the IntentDetectionService for language-agnostic intent detection
        to determine whether to search knowledge bases, memory, or both.

        Args:
            query: The search query to analyze

        Returns:
            Search strategy: "knowledge_only", "memory_only", or "both"
        """
        # Try to use intent detection service if available
        try:
            # Get or create intent detection service
            if not hasattr(self, "_intent_detector"):
                # Use existing model instance
                llm_service = self.model

                self._intent_detector = IntentDetectionService(
                    llm_service=llm_service, enable_cache=True
                )

            # Detect query type using LLM
            # Add recent conversation context if available
            context = IntentDetectionContext(
                recent_messages=(
                    [
                        {"role": msg.role, "content": msg.content[:200]}
                        for msg in self._messages[-5:]  # Last 5 messages
                    ]
                    if hasattr(self, "_messages") and self._messages
                    else None
                )
            )

            result = await self._intent_detector.detect_intent(
                text=query, intent_type=IntentType.QUERY_TYPE, context=context
            )

            # Map intent to strategy
            if result.confidence > 0.7:  # High confidence
                if result.intent == "knowledge":
                    return "knowledge_only"
                elif result.intent == "memory":
                    return "memory_only"
                elif result.intent == "mixed":
                    return "both"

            # Low confidence or unclear - use both
            return "both"

        except Exception as e:
            # Fall back to simple keyword-based detection
            if hasattr(self, "logger"):
                self.logger.warning(f"Intent detection failed, using fallback: {str(e)}")
            return self._fallback_query_routing(query)

    def _fallback_query_routing(self, query: str) -> str:
        """
        Fallback keyword-based query routing.

        Used when intent detection service is not available.
        """
        query_lower = query.lower()

        # Simple heuristics for fallback
        memory_keywords = [
            "remember",
            "last time",
            "previously",
            "you said",
            "we discussed",
            "earlier",
        ]
        knowledge_keywords = ["what is", "how to", "explain", "define", "why", "tutorial"]

        has_memory = any(keyword in query_lower for keyword in memory_keywords)
        has_knowledge = any(keyword in query_lower for keyword in knowledge_keywords)

        if has_memory and not has_knowledge:
            return "memory_only"
        elif has_knowledge and not has_memory:
            return "knowledge_only"
        else:
            return "both"

    def _allocate_context_budget(
        self, total_budget: int, strategy: str, base_limit: int
    ) -> tuple[int, int]:
        """
        Allocate context budget between knowledge and memory sources.

        Allocates context budget between knowledge and memory sources by
        intelligently distributing the available context budget based on the
        determined search strategy.

        Args:
            total_budget: Total context budget to allocate
            strategy: Search strategy ("knowledge_only", "memory_only", or "both")
            base_limit: Base limit per source when strategy is "both"

        Returns:
            Tuple of (knowledge_limit, memory_limit)
        """
        if strategy == "knowledge_only":
            return (total_budget, 0)
        elif strategy == "memory_only":
            return (0, total_budget)
        else:
            # For "both" strategy, allocate based on a balanced approach
            # Give slight preference to knowledge for factual queries
            # but ensure both sources get meaningful allocation

            if total_budget <= 2:
                # Very small budget - give one to each
                return (1, 1)
            elif total_budget <= 4:
                # Small budget - split evenly
                half = total_budget // 2
                return (half, total_budget - half)
            else:
                # Larger budget - use 60/40 split favoring knowledge
                # but ensure minimum of 2 for each source
                knowledge_portion = max(2, int(total_budget * 0.6))
                memory_portion = max(2, total_budget - knowledge_portion)

                # Adjust if we exceeded total budget
                if knowledge_portion + memory_portion > total_budget:
                    knowledge_portion = total_budget - memory_portion

                return (knowledge_portion, memory_portion)

    def _deduplicate_results(
        self, results: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Remove duplicate content between knowledge and memory results.

        Removes duplicate content between knowledge and memory results by identifying
        and removing semantically similar content between knowledge sources
        and memory to avoid redundant information in the unified results.

        Args:
            results: Dictionary with 'knowledge' and 'memory' result lists

        Returns:
            Dictionary with deduplicated results
        """
        knowledge_results = results.get("knowledge", [])
        memory_results = results.get("memory", [])

        if not knowledge_results or not memory_results:
            return results

        # Simple text-based deduplication
        # For more sophisticated deduplication, we could use embedding similarity
        deduplicated_memory = []

        # Extract content from knowledge results for comparison
        knowledge_contents = set()
        for k_result in knowledge_results:
            content = k_result.get("content", "").strip().lower()
            if content:
                # Use first 100 characters as a fingerprint
                knowledge_contents.add(content[:100])

        # Filter memory results that don't significantly overlap with knowledge
        for m_result in memory_results:
            memory_content = m_result.get("content", "").strip().lower()
            if not memory_content:
                continue

            # Check for significant overlap with knowledge content
            memory_fingerprint = memory_content[:100]
            is_duplicate = False

            for k_fingerprint in knowledge_contents:
                # Calculate simple overlap ratio
                if len(memory_fingerprint) > 0 and len(k_fingerprint) > 0:
                    # Simple string similarity check
                    overlap = self._calculate_text_overlap(memory_fingerprint, k_fingerprint)
                    if overlap > 0.7:  # 70% similarity threshold
                        is_duplicate = True
                        break

            if not is_duplicate:
                deduplicated_memory.append(m_result)

        return {"knowledge": knowledge_results, "memory": deduplicated_memory}

    def _calculate_text_overlap(self, text1: str, text2: str) -> float:
        """
        Calculate simple text overlap ratio between two strings.

        Args:
            text1: First text string
            text2: Second text string

        Returns:
            Overlap ratio between 0.0 and 1.0
        """
        if not text1 or not text2:
            return 0.0

        # Simple word-based overlap calculation
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0

    def _create_enhanced_unified_ranking(
        self,
        knowledge_results: List[Dict[str, Any]],
        memory_results: List[Dict[str, Any]],
        query: str,
        strategy: str,
        budget: int,
    ) -> List[Dict[str, Any]]:
        """
        Create enhanced unified ranking of knowledge and memory results.

        Creates enhanced unified ranking of knowledge and memory results by intelligently
        combining and ranking results from both sources based on relevance,
        recency, and the search strategy used.

        Args:
            knowledge_results: Results from knowledge sources
            memory_results: Results from memory sources
            query: Original search query for relevance scoring
            strategy: Search strategy used
            budget: Total context budget to respect

        Returns:
            List of unified results ranked by enhanced scoring
        """
        unified_results = []

        # Add knowledge results with enhanced scoring
        for result in knowledge_results:
            enhanced_result = result.copy()
            enhanced_result["source_type"] = "knowledge"

            # Calculate enhanced score based on strategy
            base_score = result.get("relevance", result.get("score", 0.5))

            if strategy == "knowledge_only":
                # Boost knowledge scores when it's the primary source
                enhanced_score = min(1.0, base_score * 1.2)
            elif strategy == "both":
                # Standard scoring for balanced approach
                enhanced_score = base_score
            else:
                # Lower knowledge scores when memory is preferred
                enhanced_score = base_score * 0.8

            enhanced_result["enhanced_score"] = enhanced_score
            unified_results.append(enhanced_result)

        # Add memory results with enhanced scoring
        for result in memory_results:
            enhanced_result = result.copy()
            enhanced_result["source_type"] = "memory"

            # Calculate enhanced score based on strategy
            base_score = result.get("relevance", result.get("score", 0.5))

            # Memory results often have recency bonus
            recency_bonus = self._calculate_recency_bonus(result)

            if strategy == "memory_only":
                # Boost memory scores when it's the primary source
                enhanced_score = min(1.0, (base_score + recency_bonus) * 1.2)
            elif strategy == "both":
                # Add recency bonus for balanced approach
                enhanced_score = min(1.0, base_score + recency_bonus)
            else:
                # Lower memory scores when knowledge is preferred
                enhanced_score = (base_score + recency_bonus) * 0.8

            enhanced_result["enhanced_score"] = enhanced_score
            unified_results.append(enhanced_result)

        # Sort by enhanced score (descending)
        unified_results.sort(key=lambda x: x.get("enhanced_score", 0), reverse=True)

        # Respect context budget
        if len(unified_results) > budget:
            unified_results = unified_results[:budget]

        # Add ranking metadata
        for i, result in enumerate(unified_results):
            result["unified_rank"] = i + 1
            result["strategy_used"] = strategy

        return unified_results

    def _calculate_recency_bonus(self, result: Dict[str, Any]) -> float:
        """
        Calculate recency bonus for memory results.

        Args:
            result: Memory search result

        Returns:
            Recency bonus value between 0.0 and 0.3
        """
        # Look for timestamp in various possible fields
        timestamp = result.get("timestamp") or result.get("created_at") or result.get("time")

        if not timestamp:
            return 0.0

        try:
            current_time = time.time()

            # Convert timestamp to float if it's not already
            if isinstance(timestamp, str):
                # Try to parse ISO format or other common formats
                import datetime

                try:
                    dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp = dt.timestamp()
                except (ValueError, TypeError):
                    return 0.0

            # Calculate age in hours
            age_hours = (current_time - timestamp) / 3600

            # Recency bonus decreases with age
            if age_hours < 1:
                return 0.3  # Very recent (last hour)
            elif age_hours < 24:
                return 0.2  # Recent (last day)
            elif age_hours < 168:  # Last week
                return 0.1
            else:
                return 0.0  # Older than a week

        except (ValueError, TypeError, AttributeError):
            return 0.0

    async def process_message(
        self,
        message: Union[str, MuxiResponse],
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
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
        # Store current user_id for tool invocations
        self._current_user_id = user_id

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
                session_id=session_id,
                request_id=request_id,
            )

        # Add message to conversation context
        self._messages.append({"role": "user", "content": message_obj.content})

        # Search knowledge and memory if handler is available
        context_enhancement = ""

        # First, check for recent document uploads
        recent_docs = []
        if self.overlord and hasattr(self.overlord, "get_recent_documents"):
            # Pass session_id to get documents from the current session
            recent_docs = self.overlord.get_recent_documents(session_id=session_id)

        if self._knowledge_config:  # Check if knowledge config exists
            try:
                # Use unified search to get both knowledge and memory context
                search_results = await self.search_knowledge(
                    query=content, limit=5, include_memory=True, unified=True, session_id=session_id
                )

                # Build enhanced context from unified results
                knowledge_results = search_results.get("knowledge", [])
                memory_results = search_results.get("memory", [])

                if knowledge_results or memory_results or recent_docs:
                    context_parts = []

                    # Add recent document uploads first (highest priority)
                    if recent_docs:
                        context_parts.extend(self._format_recent_documents(recent_docs))

                    # Add domain knowledge context
                    if knowledge_results:
                        context_parts.append("--- Domain Knowledge ---")
                        for result in knowledge_results:
                            context_parts.append(f"• {result.get('content', '')}")
                        context_parts.append("--- End Domain Knowledge ---")

                    # Add memory context
                    if memory_results:
                        context_parts.append("--- Recent Context ---")
                        for result in memory_results:
                            context_parts.append(f"• {result.get('content', '')}")
                        context_parts.append("--- End Recent Context ---")

                    context_enhancement = "\n\n" + "\n".join(context_parts) + "\n\n"

                    # Add enhanced context to the conversation
                    enhanced_message = f"{content}{context_enhancement}"
                    self._messages[-1]["content"] = enhanced_message

                    # Log unified search success
                    observability.observe(
                        event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
                        level=observability.EventLevel.INFO,
                        data={
                            "agent_id": self.agent_id,
                            "knowledge_results_count": len(knowledge_results),
                            "memory_results_count": len(memory_results),
                            "recent_docs_count": len(recent_docs),
                            "query": content[:100],
                            "unified_search": True,
                        },
                        description=(
                            f"Context search completed for agent {self.agent_id}: "
                            f"{len(recent_docs)} recent docs, {len(knowledge_results)} knowledge, "
                            f"{len(memory_results)} memory results"
                        ),
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
        else:
            # No knowledge config, but still check for recent documents
            # Get recent docs again if we didn't already
            if not recent_docs and self.overlord and hasattr(self.overlord, "get_recent_documents"):
                recent_docs = self.overlord.get_recent_documents(session_id=session_id)

            if recent_docs:
                context_parts = self._format_recent_documents(recent_docs)

                context_enhancement = "\n\n" + "\n".join(context_parts) + "\n\n"

                # Add enhanced context to the conversation
                enhanced_message = f"{content}{context_enhancement}"
                self._messages[-1]["content"] = enhanced_message

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

        # Check if agent needs clarification from user
        clarification_request = await self._check_agent_clarification_needs(
            content, message_obj.content
        )

        # Create response message
        response = MuxiResponse(role="assistant", content=content)

        # Note: clarification_request is tracked in observability but not stored in response

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

    def _format_recent_documents(self, recent_docs: List[Dict[str, Any]]) -> List[str]:
        """
        Format recent documents into context parts.

        Args:
            recent_docs: List of recent document dictionaries

        Returns:
            List of formatted context strings
        """
        context_parts = []
        context_parts.append("--- Recently Uploaded Documents ---")
        for doc in recent_docs:
            context_parts.append(f"Filename: {doc.get('filename', 'Unknown')}")
            # Join content list if it's a list
            doc_content = doc.get("content", "")
            if isinstance(doc_content, list):
                # Check if list contains bytes
                if doc_content and isinstance(doc_content[0], bytes):
                    # List of bytes - try to decode each
                    decoded_parts = []
                    for part in doc_content:
                        try:
                            decoded_parts.append(
                                part.decode("utf-8") if isinstance(part, bytes) else str(part)
                            )
                        except (UnicodeDecodeError, AttributeError) as e:
                            observability.observe(
                                event_type=observability.SystemEvents.SERVICE_WARNING,
                                level=observability.EventLevel.WARNING,
                                data={
                                    "agent_id": self.agent_id,
                                    "error": str(e),
                                    "content_type": "binary_list_item",
                                },
                                description=f"Failed to decode binary content in document list: {type(e).__name__}",
                            )
                            decoded_parts.append("[Binary content]")
                    doc_content = "\n".join(decoded_parts)
                else:
                    # List of strings
                    doc_content = "\n".join(str(item) for item in doc_content)
            elif isinstance(doc_content, bytes):
                # Handle binary content - decode if possible or show placeholder
                try:
                    doc_content = doc_content.decode("utf-8")
                except (UnicodeDecodeError, AttributeError) as e:
                    observability.observe(
                        event_type=observability.SystemEvents.SERVICE_WARNING,
                        level=observability.EventLevel.WARNING,
                        data={
                            "agent_id": self.agent_id,
                            "error": str(e),
                            "content_type": "binary_file",
                        },
                        description=f"Failed to decode binary file content: {type(e).__name__}",
                    )
                    doc_content = "[Binary file content - unable to display as text]"
            context_parts.append(f"{doc_content}")
            context_parts.append("")  # Empty line between docs
        context_parts.append("--- End Recently Uploaded Documents ---")
        return context_parts

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
                "original_response": agent_response,
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

        Uses the IntentDetectionService for language-agnostic clarification detection.

        Args:
            agent_response: The agent's response text
            user_message: The original user message

        Returns:
            Dictionary mapping information categories to specific questions
        """
        try:
            # Get or create intent detection service
            if not hasattr(self, "_intent_detector"):
                # Use existing model instance
                llm_service = self.model

                self._intent_detector = IntentDetectionService(
                    llm_service=llm_service, enable_cache=True
                )

            # Use intent detection for clarification categories
            context = IntentDetectionContext(
                recent_messages=[
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": agent_response},
                ]
            )

            result = await self._intent_detector.detect_intent(
                text=agent_response, intent_type=IntentType.CLARIFICATION_CATEGORY, context=context
            )

            required_info = {}

            # If we detected a clarification category with good confidence
            if result.confidence > 0.6 and result.intent != "none":
                # Extract the actual question
                question = result.extracted_question
                if not question:
                    # Fall back to extracting question from response
                    question = await self._extract_question_for_category(
                        agent_response, result.intent
                    )

                if question:
                    required_info[result.intent] = question

            # Check alternatives for additional categories
            if result.alternatives:
                for alt in result.alternatives:
                    if alt["confidence"] > 0.5 and alt["intent"] not in required_info:
                        question = await self._extract_question_for_category(
                            agent_response, alt["intent"]
                        )
                        if question:
                            required_info[alt["intent"]] = question

            return required_info

        except Exception as e:
            # Fall back to keyword-based detection
            if hasattr(self, "logger"):
                self.logger.warning(
                    f"Intent detection for clarification failed, using fallback: {str(e)}"
                )
            return await self._fallback_extract_information_requests(agent_response, user_message)

    async def _fallback_extract_information_requests(
        self, agent_response: str, user_message: str
    ) -> Dict[str, str]:
        """
        Fallback keyword-based information request extraction.

        Used when intent detection service is not available.
        """
        # Common information categories and their question patterns
        info_categories = {
            "budget": [
                r"(?i)(?:budget|cost|price|money|funding|spend)",
                r"(?i)(?:how much|what(?:'s| is) (?:the )?(?:cost|price))",
            ],
            "timeline": [
                r"(?i)(?:when|timeline|deadline|schedule|time)",
                r"(?i)(?:how (?:long|soon)|by when)",
            ],
            "preferences": [
                r"(?i)(?:prefer|preference|like|want|style|approach)",
                r"(?i)(?:which (?:type|kind|option)|what (?:type|kind))",
            ],
            "requirements": [
                r"(?i)(?:require|requirement|need|must|should|specification)",
                r"(?i)(?:what (?:features|capabilities|functionality))",
            ],
            "scope": [
                r"(?i)(?:scope|scale|size|extent|coverage)",
                r"(?i)(?:how (?:big|large|extensive|comprehensive))",
            ],
            "location": [
                r"(?i)(?:where|location|place|region|area)",
                r"(?i)(?:which (?:location|place|area))",
            ],
        }

        required_info = {}

        # Extract questions for each category found in the response
        for category, patterns in info_categories.items():
            for pattern in patterns:
                if re.search(pattern, agent_response):
                    # Extract the actual question from the response
                    question = await self._extract_question_for_category(agent_response, category)
                    if question:
                        required_info[category] = question
                        break

        return required_info

    async def _extract_question_for_category(self, response: str, category: str) -> Optional[str]:
        """
        Extract the specific question for a given information category.

        Args:
            response: Agent's response text
            category: Information category (budget, timeline, etc.)

        Returns:
            The extracted question or a generated question for the category
        """
        # Split response into sentences
        sentences = re.split(r"[.!?]+", response)

        # Category-specific keywords to look for
        category_keywords = {
            "budget": ["budget", "cost", "price", "money", "funding", "spend"],
            "timeline": ["when", "timeline", "deadline", "schedule", "time"],
            "preferences": ["prefer", "preference", "like", "want", "style"],
            "requirements": ["require", "requirement", "need", "must", "specification"],
            "scope": ["scope", "scale", "size", "extent", "coverage"],
            "location": ["where", "location", "place", "region", "area"],
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
            "location": "Where should this be implemented or focused?",
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

            # Get credential resolver from overlord's MCP coordinator if available
            credential_resolver = None
            if self.overlord and hasattr(self.overlord, "mcp_coordinator"):
                credential_resolver = self.overlord.mcp_coordinator

            if server_id:
                result = await self._mcp_service.invoke_tool(
                    server_id,
                    tool_name,
                    parameters,
                    timeout=self.request_timeout,
                    user_id=self._current_user_id,
                    credential_resolver=credential_resolver,
                )
            else:
                # Try to find the tool in any available server
                servers = self._mcp_service.get_servers()
                result = None
                for server_name in servers:
                    try:
                        result = await self._mcp_service.invoke_tool(
                            server_name,
                            tool_name,
                            parameters,
                            timeout=self.request_timeout,
                            user_id=self._current_user_id,
                            credential_resolver=credential_resolver,
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
            # Check if this is a MissingCredentialError
            from ..memory.credential_resolver import MissingCredentialError

            if isinstance(e, MissingCredentialError):
                # Trigger clarification flow through overlord
                if self.overlord and hasattr(self.overlord, "handle_missing_credential"):
                    await self.overlord.handle_missing_credential(
                        service=e.service,
                        user_id=e.user_id,
                        context={
                            "agent_id": self.agent_id,
                            "tool_name": tool_name,
                            "server_id": server_id,
                        },
                    )
                    # Re-raise to let overlord handle the clarification
                    raise
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
