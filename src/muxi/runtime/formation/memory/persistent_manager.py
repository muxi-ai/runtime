"""
Persistent memory management for the Overlord.

This module handles all long-term memory operations including adding content,
searching, and clearing persistent memory.
"""

from typing import Any, Dict, List, Optional

from ...services import observability


class PersistentMemoryManager:
    """
    Manages persistent memory operations for the Overlord.

    This class encapsulates all long-term memory functionality that was previously
    embedded in the main Overlord class, providing a cleaner separation of concerns.
    """

    def __init__(self, overlord):
        """
        Initialize the persistent memory manager.

        Args:
            overlord: Reference to the overlord instance
        """
        self.overlord = overlord

    async def add_to_long_term_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        agent_id: Optional[str] = None,
        user_id: Any = None,
    ) -> Optional[str]:
        """
        Add content to the overlord's long-term memory.

        This method stores information in the persistent long-term memory system,
        which maintains knowledge across sessions. Content added to long-term memory
        will be available for semantic retrieval in future conversations.

        Args:
            content: The text content to store. This should be meaningful information
                that's worth retaining for future reference.
            metadata: Optional metadata to associate with the content.
                Useful for categorization and filtering (e.g., by topic, importance).
            embedding: Optional pre-computed embedding vector.
                If provided, skips the embedding generation step.
            agent_id: Optional agent ID to include in metadata.
                Used to track which agent was the source of this information.
            user_id: Optional user ID for multi-user support.
                Required when using Memobase in multi-user mode.

        Returns:
            The ID of the newly created memory entry if successful, None otherwise.
            This ID can be used for later updating or deleting the specific memory.
        """
        if not self.overlord.long_term_memory:
            return None

        # Add agent_id to metadata for context if provided
        full_metadata = metadata or {}
        if agent_id:
            full_metadata["agent_id"] = agent_id

        # Handle multi-user case with Memobase
        if self.overlord.is_multi_user and user_id is not None:
            try:
                # Use external user ID directly - no conversion needed
                memory_id = await self.overlord.long_term_memory.add(
                    content=content,
                    metadata=full_metadata,
                    embedding=embedding,
                    user_id=user_id,
                )

                # Emit memory storage completed event
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "memory_id": memory_id,
                        "memory_type": "long_term",
                        "content_length": len(content),
                    },
                    description="Long-term memory storage completed",
                )

                return memory_id
            except Exception as e:
                # Emit memory storage failed event
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "memory_type": "long_term",
                        "error": str(e),
                    },
                    description=f"Long-term memory storage failed: {e}",
                )
                return None

        # Standard long-term memory case
        try:
            memory_id = await self.overlord.long_term_memory.add(
                content=content,
                metadata=full_metadata,
                embedding=embedding,
            )

            # Emit memory storage completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
                level=observability.EventLevel.DEBUG,
                data={
                    "memory_id": memory_id,
                    "memory_type": "long_term",
                    "content_length": len(content),
                },
                description="Long-term memory storage completed",
            )

            return memory_id
        except Exception as e:
            # Emit memory storage failed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "memory_type": "long_term",
                    "error": str(e),
                },
                description=f"Long-term memory storage failed: {e}",
            )
            return None

    async def search_long_term_memory(
        self,
        query: str,
        agent_id: Optional[str] = None,
        k: int = 5,
        user_id: Any = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory for relevant information.

        Args:
            query: The query text to search for
            agent_id: Optional agent ID to filter results by
            k: The number of results to return
            user_id: Optional user ID for multi-user support
            filter_metadata: Additional metadata filters to apply

        Returns:
            List of relevant memory items from long-term memory
        """
        if not self.overlord.long_term_memory:
            return []

        # Prepare metadata filter
        full_filter = filter_metadata or {}
        if agent_id:
            full_filter["agent_id"] = agent_id

        try:
            # Emit memory search started event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_LOOKUP,
                level=observability.EventLevel.DEBUG,
                data={
                    "query": query[:100],
                    "memory_type": "long_term",
                    "k": k,
                    "agent_id": agent_id,
                    "user_id": str(user_id) if user_id is not None else None,
                },
                description="Starting long-term memory search",
            )

            # Handle multi-user case with Memobase
            if self.overlord.is_multi_user and user_id is not None:
                # Use external user_id directly for database queries
                lt_results = await self.overlord.long_term_memory.search(
                    query=query, limit=k, user_id=user_id, filter_metadata=full_filter
                )
            # Standard long-term memory case
            else:
                lt_results = await self.overlord.long_term_memory.search(
                    query=query, k=k, filter_metadata=full_filter
                )

            # Emit memory search completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "query": query[:100],
                    "memory_type": "long_term",
                    "results_count": len(lt_results),
                },
                description=(f"Long-term memory search completed: " f"{len(lt_results)} results"),
            )

            # Convert to standard format
            results = []
            for item in lt_results:
                results.append(
                    {
                        "text": item[1].get("text", ""),
                        "metadata": item[1].get("metadata", {}),
                        "distance": item[0],
                        "source": "long_term",
                    }
                )

            return results

        except Exception as e:
            #  Warning - TODO: add observability
            # ConversationEvents.MEMORY_LONG_TERM_RETRIEVAL_FAILED
            _ = e  # remove this after implementing observability
            return []

    async def clear_long_term_memory(
        self,
        agent_id: Optional[str] = None,
        user_id: Any = None,
    ) -> None:
        """
        Clear long-term memory for the specified agent or user.

        Args:
            agent_id: Optional agent ID to filter by.
                Only clears memories associated with this specific agent.
            user_id: Optional user ID for multi-user support.
                Only clears memories for this specific user (requires Memobase).
        """
        if not self.overlord.long_term_memory:
            return

        filter_metadata = {}
        if agent_id:
            filter_metadata["agent_id"] = agent_id

        try:
            if self.overlord.is_multi_user and user_id is not None:
                # For multi-user with Memobase - use external user_id directly
                await self.overlord.long_term_memory.clear(
                    user_id=user_id,
                    filter_metadata=filter_metadata if filter_metadata else None,
                )
            else:
                # For standard long-term memory
                await self.overlord.long_term_memory.clear(
                    filter_metadata=filter_metadata if filter_metadata else None
                )
        except Exception as e:
            #  Warning - TODO: add observability
            # ConversationEvents.MEMORY_LONG_TERM_DELETION_FAILED
            _ = e  # remove this after implementing observability

    async def add_message_to_long_term(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
        user_id: Any = None,
    ) -> Optional[str]:
        """
        Add a message to long-term memory with standard metadata.

        Args:
            content: The message content to store
            role: The role of the message sender (e.g., 'user', 'assistant')
            timestamp: The timestamp of the message as a float (unix timestamp)
            agent_id: The ID of the agent involved in the conversation
            user_id: Optional user ID for multi-user support

        Returns:
            The ID of the newly created memory entry if successful, None otherwise
        """
        if not self.overlord.long_term_memory or not self.overlord.is_multi_user or user_id is None:
            return None

        # Skip for anonymous users
        if user_id == "0" or user_id == "anonymous":
            return None

        metadata = {"role": role, "timestamp": timestamp, "agent_id": agent_id}

        # Enhanced message with user context if this is a user message
        if role == "user":
            try:
                # Get user context memory - uses external user ID
                context_memory = await self.overlord.get_user_context(user_id=user_id)

                # If context is available, enhance the message before storing
                if context_memory:
                    # Format context memory for storage with the message
                    context_str = "User Context:\n"
                    for key, value in context_memory.items():
                        if isinstance(value, dict) and "value" in value:
                            # Handle structured context memory format
                            actual_value = value["value"]
                            context_str += f"- {key}: {actual_value}\n"
                        else:
                            # Handle simple format
                            context_str += f"- {key}: {value}\n"

                    # Store the enhanced content
                    enhanced_content = f"{context_str}\n\nUser Message: {content}"
                    metadata["enhanced"] = True
                    metadata["original_content"] = content

                    return await self.overlord.long_term_memory.add(
                        content=enhanced_content, metadata=metadata, user_id=user_id
                    )
                else:
                    # Store the original content
                    return await self.overlord.long_term_memory.add(
                        content=content, metadata=metadata, user_id=user_id
                    )
            except Exception as e:
                # Log error and fall back to original message
                #  Error - TODO: add observability
                # ConversationEvents.MEMORY_LONG_TERM_ENHANCEMENT_FAILED
                _ = e  # remove this after implementing observability
                return await self.overlord.long_term_memory.add(
                    content=content, metadata=metadata, user_id=user_id
                )
        else:
            # For non-user messages, just store directly
            return await self.overlord.long_term_memory.add(
                content=content, metadata=metadata, user_id=user_id
            )
