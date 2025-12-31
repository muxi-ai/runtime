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
                    external_user_id=user_id,
                )

                # Emit memory storage completed event
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_LONG_TERM_ENHANCED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "memory_id": memory_id,
                        "memory_type": "long_term",
                        "content_length": len(content),
                        "has_metadata": metadata is not None and len(metadata) > 0,
                        "embedding_dimensions": len(embedding) if embedding else None,
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
                    "has_metadata": metadata is not None and len(metadata) > 0,
                    "embedding_dimensions": len(embedding) if embedding else None,
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
        collections: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory for relevant information.

        Args:
            query: The query text to search for
            agent_id: Optional agent ID to filter results by
            k: The number of results to return
            user_id: Optional user ID for multi-user support
            filter_metadata: Additional metadata filters to apply
            collections: Optional list of collections to search. If None, searches all collections.

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
                    "collections": collections,
                    "collections_count": len(collections) if collections else 1,
                },
                description="Starting long-term memory search",
            )

            # Helper function to call the appropriate search method with correct parameters
            async def search_collection(collection=None):
                memory_backend = self.overlord.long_term_memory

                # Use the backend's build_search_parameters method if available
                if hasattr(memory_backend, "build_search_parameters"):
                    search_params = memory_backend.build_search_parameters(
                        query=query,
                        k=k,
                        user_id=user_id if self.overlord.is_multi_user else None,
                        full_filter=full_filter,
                        collection=collection,
                    )
                else:
                    # Fallback for backends without the new method
                    search_params = {
                        "query": query,
                        "k": k,
                    }
                    if full_filter:
                        search_params["filter_metadata"] = full_filter
                    if collection:
                        search_params["collection"] = collection

                return await memory_backend.search(**search_params)

            # If collections are specified, search each one and merge results
            if collections:
                all_results = []

                for collection in collections:
                    collection_results = await search_collection(collection)
                    all_results.extend(collection_results)

                # Sort merged results by relevance score (distance) and take top k
                # Handle both dict and tuple formats with defensive type checking
                def get_sort_key(item):
                    if isinstance(item, dict):
                        score = item.get("score", 0.0)
                        try:
                            return float(score)
                        except (ValueError, TypeError):
                            raise TypeError(
                                f"Score value not numeric for dict result: type={type(score).__name__}"
                            )
                    elif isinstance(item, (tuple, list)):
                        if len(item) < 1:
                            raise TypeError(
                                f"Tuple/list result must have at least one element for score: "
                                f"type={type(item).__name__}, length={len(item)}"
                            )
                        try:
                            return float(item[0])
                        except (ValueError, TypeError):
                            raise TypeError(
                                f"Score value not numeric for {type(item).__name__} result: "
                                f"type={type(item[0]).__name__}"
                            )
                    else:
                        raise TypeError(
                            f"Unexpected result type in memory search: type={type(item).__name__}"
                        )

                all_results.sort(key=get_sort_key)
                lt_results = all_results[:k]
            else:
                # No collections specified, search all collections
                lt_results = await search_collection()

            # Calculate quality metrics from results
            results_quality_score = 0.0
            if lt_results:
                scores = []
                for item in lt_results:
                    if isinstance(item, dict):
                        scores.append(item.get("score", 0.0))
                    elif isinstance(item, (tuple, list)) and len(item) > 0:
                        scores.append(float(item[0]))
                results_quality_score = sum(scores) / len(scores) if scores else 0.0

            # Emit memory search completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "query": query[:100],
                    "memory_type": "long_term",
                    "results_count": len(lt_results),
                    "results_quality_score": results_quality_score,
                    "collections_searched": collections if collections else "all",
                    "collections_count": len(collections) if collections else 1,
                },
                description=(f"Long-term memory search completed: " f"{len(lt_results)} results"),
            )

            # Convert to standard format
            results = []
            for item in lt_results:
                # Handle both dict format (from LongTermMemory) and tuple format (from other backends)
                if isinstance(item, dict):
                    # LongTermMemory returns dicts with keys: id, text, metadata, score
                    results.append(
                        {
                            "text": item.get("text", ""),
                            "metadata": item.get("metadata", {}),
                            "distance": item.get("score", 0.0),  # score is actually distance/similarity
                            "source": "long_term",
                        }
                    )
                else:
                    # Tuple format: (distance, metadata_dict)
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
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_RETRIEVAL_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "k": k,
                    "user_id": str(user_id) if user_id else None,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Long-term memory retrieval failed",
            )
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
                    external_user_id=user_id,
                    filter_metadata=filter_metadata if filter_metadata else None,
                )
            else:
                # For standard long-term memory
                await self.overlord.long_term_memory.clear(
                    filter_metadata=filter_metadata if filter_metadata else None
                )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_CLEAR_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "user_id": str(user_id) if user_id else None,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Long-term memory clear failed",
            )

    async def add_message_to_long_term(
        self,
        content: str,
        role: str,
        timestamp: float,
        agent_id: str,
        user_id: Any = None,
        collection: str = "conversations",
    ) -> Optional[str]:
        """
        Add a message to long-term memory with standard metadata.

        Args:
            content: The message content to store
            role: The role of the message sender (e.g., 'user', 'assistant')
            timestamp: The timestamp of the message as a float (unix timestamp)
            agent_id: The ID of the agent involved in the conversation
            user_id: Optional user ID for multi-user support
            collection: The collection to store the message in (default: "conversations")

        Returns:
            The ID of the newly created memory entry if successful, None otherwise
        """
        if not self.overlord.long_term_memory or user_id is None:
            return None

        # Skip for anonymous users in multi-user mode only
        # In single-user mode, user_id="0" is normal and expected
        if self.overlord.is_multi_user and (user_id == 0 or user_id == "0"):
            return None

        metadata = {"role": role, "timestamp": timestamp, "agent_id": agent_id}

        # IMPORTANT: Always store the ORIGINAL message, never enhanced
        # Enhancement should only happen during retrieval for context
        return await self.overlord.long_term_memory.add(
            content=content,  # Always store original content
            metadata=metadata,
            external_user_id=user_id,
            collection=collection,
        )
