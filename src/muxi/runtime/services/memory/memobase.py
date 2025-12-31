# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Memobase - Multi-User Memory Management System
# Description:  User-aware memory system for storing and retrieving information
# Role:         Provides user-specific context and knowledge management
# Usage:        Used by Overlord to maintain separate memory for each user
# Author:       Muxi Framework Team
#
# The Memobase module provides a sophisticated memory management system that
# maintains separate memory contexts for different users. Key features include:
#
# 1. User-Centric Memory Organization
#    - One memory collection per user
#    - Automatic metadata filtering by user_id
#    - Anonymous user support with fallback behaviors
#
# 2. Context Memory Management
#    - User-specific knowledge storage
#    - Structured knowledge representation
#    - Import/export capabilities for user context
#
# 3. Integration with Vector Storage
#    - Built on top of LongTermMemory for persistent storage
#    - Provides user-specific abstraction over vector database
#    - Supports all search capabilities with user-context awareness
#
# This system enables applications to maintain separate memory contexts for
# different users while providing a unified interface for memory operations.
# =============================================================================

import asyncio
import time
from typing import Any, Dict, List, Optional

from .long_term import LongTermMemory
from .. import observability


class Memobase:
    """
    A multi-user memory manager that provides access to PostgreSQL/PGVector
    storage with user context awareness.

    Memobase allows agents to maintain separate memory contexts for different
    users while providing a unified interface for memory operations. It handles
    anonymous users gracefully and provides specialized functionality for
    managing user context memory.
    """

    # Constants for context memory

    def __init__(self, long_term_memory: LongTermMemory, default_external_user_id: str = "0"):
        """
        Initialize the Memobase memory manager.

        Args:
            long_term_memory: PostgreSQL/PGVector-based long-term memory.
            default_external_user_id: The default external user ID to use ("0" for single-user
                mode).
        """
        self.default_external_user_id = default_external_user_id
        self.long_term_memory = long_term_memory

        # Log initialization
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Memobase initialized",
            data={
                "default_external_user_id": default_external_user_id,
                "long_term_memory_type": type(long_term_memory).__name__,
            },
        )  # Don't let observability failures break initialization

    async def add(
        self,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        external_user_id: Optional[str] = None,
        collection: Optional[str] = None,
    ) -> str:
        """
        Add content to memory for a specific user.

        This method stores information in a user-specific memory collection,
        automatically handling the appropriate collection naming and metadata
        tagging.

        Args:
            content: The content to add to memory.
            embedding: Optional pre-computed embedding for the content.
            metadata: Optional metadata to associate with the content.
            external_user_id: The external user ID for the user. If None, uses the default
                external user ID.
            collection: Optional collection name to store the memory in.
                If None, uses the default user collection.

        Returns:
            The ID of the newly created memory entry.
        """
        external_user_id = (
            external_user_id if external_user_id is not None else self.default_external_user_id
        )

        # Log memory store start
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory store operation",
            data={
                "external_user_id": external_user_id,
                "content_length": len(content) if content else 0,
                "has_embedding": embedding is not None,
                "collection": collection,
                "metadata_keys": list(metadata.keys()) if metadata else [],
            },
        )

        # Skip memory operations for default/anonymous users
        if external_user_id in ["default", "anonymous", "0"]:
            # Log anonymous user skip
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory store for anonymous user",
                data={"external_user_id": external_user_id},
            )
            # Return dummy ID for anonymous users
            return "0"

        metadata = metadata or {}

        # Add external_user_id to metadata
        metadata["external_user_id"] = external_user_id

        # Add timestamp if not provided
        if "timestamp" not in metadata:
            metadata["timestamp"] = time.time()

        # Create a collection name based on the external user ID if not provided
        if collection is None:
            collection = f"user_{external_user_id}"

        try:
            # Add to long-term memory (it will handle collection creation internally)
            memory_id = await self.long_term_memory.add(
                content=content,
                embedding=embedding,
                metadata=metadata,
                external_user_id=external_user_id,
            )

            # Log successful memory store
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.INFO,
                description="Memory store completed successfully",
                data={
                    "external_user_id": external_user_id,
                    "memory_id": memory_id,
                    "collection": collection,
                    "content_length": len(content) if content else 0,
                },
            )

            return memory_id

        except Exception as e:
            # Log memory store error
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="Memory store operation failed",
                data={
                    "external_user_id": external_user_id,
                    "collection": collection,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def search(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        limit: int = 5,
        external_user_id: Optional[str] = None,
        additional_filter: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content in memory for a specific user.

        This method performs a semantic search within a user's memory collection,
        applying appropriate filters to ensure only the user's memories are
        returned.

        Args:
            query: The text query to search for.
            query_embedding: Optional pre-computed embedding.
            limit: Maximum number of results to return.
            external_user_id: The external user ID to search memory for. If None, uses the
                default external user ID.
            additional_filter: Optional additional metadata filter.
            collection: Optional collection name to search in. If None, uses
                the default collection for the user.

        Returns:
            A list of memory entries, ordered by relevance.
        """
        external_user_id = (
            external_user_id if external_user_id is not None else self.default_external_user_id
        )

        # Log memory retrieval start
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory search operation",
            data={
                "external_user_id": external_user_id,
                "query_length": len(query) if query else 0,
                "limit": limit,
                "collection": collection,
                "has_query_embedding": query_embedding is not None,
                "filter_keys": (list(additional_filter.keys()) if additional_filter else []),
            },
        )

        # Skip memory operations for anonymous users
        if external_user_id in ["default", "anonymous", "0"]:
            # Log anonymous user skip
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory search for anonymous user",
                data={"external_user_id": external_user_id},
            )
            # Return empty results for anonymous users
            return []

        additional_filter = additional_filter or {}

        # Add external_user_id to filter
        additional_filter["external_user_id"] = external_user_id

        # Create a collection name based on the external user ID if not provided
        if collection is None:
            collection = f"user_{external_user_id}"

        try:
            # Search long-term memory
            search_results = await self.long_term_memory.search(
                query=query,
                query_embedding=query_embedding,
                filter_metadata=additional_filter,
                limit=limit,
                collection=collection,
                external_user_id=external_user_id,
            )

            # Convert results to standard format
            results = []
            for memory in search_results:
                results.append(
                    {
                        "content": memory.get("text", ""),
                        "metadata": memory.get("metadata", {}),
                        "distance": 1.0
                        - memory.get("score", 0.5),  # Convert similarity score to distance
                        "source": "memobase",
                        "id": memory.get("id"),
                        "created_at": memory.get("created_at"),
                    }
                )

            # Calculate quality metrics from similarity scores
            results_quality_score = (
                sum(memory.get("score", 0.0) for memory in search_results) / len(search_results)
                if search_results
                else 0.0
            )

            # Log successful memory retrieval
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="Memory search completed successfully",
                data={
                    "external_user_id": external_user_id,
                    "collection": collection,
                    "results_count": len(results),
                    "results_quality_score": results_quality_score,
                    "query_length": len(query) if query else 0,
                },
            )

            return results

        except Exception as e:
            # Log memory retrieval error
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_RETRIEVAL_FAILED,
                level=observability.EventLevel.ERROR,
                description="Memory search operation failed",
                data={
                    "external_user_id": external_user_id,
                    "collection": collection,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def build_search_parameters(
        self,
        query: str,
        k: int = 5,
        user_id: Optional[str] = None,
        full_filter: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build search parameters for the Memobase search method.

        Args:
            query: The search query text
            k: Number of results to return
            user_id: Optional user ID for filtering
            full_filter: Optional metadata filter
            collection: Optional collection name

        Returns:
            Dictionary of parameters for the search method
        """
        search_params = {
            "query": query,
            "limit": k,
            "additional_filter": full_filter,
        }

        if user_id is not None:
            search_params["external_user_id"] = user_id

        if collection:
            search_params["collection"] = collection

        return search_params

    async def delete(
        self,
        memory_id: str,
        external_user_id: Optional[str] = None,
    ) -> bool:
        """
        Delete a specific memory entry.

        This method removes a specific memory entry from a user's collection,
        with appropriate handling for anonymous users.

        Args:
            memory_id: The ID of the memory to delete.
            external_user_id: The external user ID associated with this memory. If None, uses the
                default external user ID.

        Returns:
            True if deletion was successful, False otherwise.
        """
        external_user_id = (
            external_user_id if external_user_id is not None else self.default_external_user_id
        )

        # Log memory deletion start
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory deletion operation",
            data={"user_id": external_user_id, "memory_id": memory_id},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if external_user_id == "0":
            # Log anonymous user skip
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory deletion for anonymous user",
                data={"user_id": external_user_id, "memory_id": memory_id},
            )
            # Return success for anonymous users (no-op)
            return True

        try:
            # Delete from long-term memory
            success = await asyncio.to_thread(
                self.long_term_memory.delete,
                memory_id=memory_id,
            )

            # Log successful memory deletion
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.INFO,
                description="Memory deletion completed",
                data={"user_id": external_user_id, "memory_id": memory_id, "success": success},
            )

            return success

        except Exception as e:
            # Log memory deletion error
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                level=observability.EventLevel.ERROR,
                description="Memory deletion operation failed",
                data={
                    "user_id": external_user_id,
                    "memory_id": memory_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def clear_user_memory(self, external_user_id: Optional[str] = None) -> None:
        """
        Clear memory for a specific user by recreating their collection.

        This method deletes all memories associated with a user by dropping
        and recreating their collection.

        Args:
            external_user_id: The external user ID to clear memory for. If None, uses the
                default external user ID.
        """
        external_user_id = (
            external_user_id if external_user_id is not None else self.default_external_user_id
        )

        # Log memory clear start
        observability.observe(
            event_type=observability.SystemEvents.MEMORY_CLEAR,
            level=observability.EventLevel.INFO,
            description="Starting user memory clear operation",
            data={"user_id": external_user_id},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if external_user_id == "0":
            # Log anonymous user skip
            observability.observe(
                event_type=observability.SystemEvents.MEMORY_CLEAR,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory clear for anonymous user",
                data={"user_id": external_user_id},
            )
            # No-op for anonymous users
            return

        # Create a collection name based on the user ID
        collection = f"user_{external_user_id}"

        try:
            # Drop and recreate the collection
            try:
                self.long_term_memory.delete_collection(collection)
            except Exception:
                pass  # Collection might not exist

            self.long_term_memory.create_collection(
                collection, f"Memory collection for user {external_user_id}"
            )

            # Log successful memory clear
            observability.observe(
                event_type=observability.SystemEvents.MEMORY_CLEAR,
                level=observability.EventLevel.INFO,
                description="User memory clear completed successfully",
                data={"user_id": external_user_id, "collection": collection},
            )

        except Exception as e:
            # Log memory clear error
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_CLEAR_FAILED,
                level=observability.EventLevel.ERROR,
                description="User memory clear operation failed",
                data={
                    "user_id": external_user_id,
                    "collection": collection,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def get_user_memories(
        self,
        external_user_id: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        ascending: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get recent memories for a specific user.

        This method retrieves the most recent memories for a user, with
        options for pagination and sorting.

        Args:
            external_user_id: The external user ID to get memories for. If None, uses the
                default external user ID.
            limit: Maximum number of memories to return.
            offset: Number of memories to skip (for pagination).
            sort_by: Field to sort by (created_at, updated_at, id).
            ascending: Whether to sort in ascending order.

        Returns:
            A list of memory entries.
        """
        external_user_id = (
            external_user_id if external_user_id is not None else self.default_external_user_id
        )

        # Log memory retrieval start
        observability.observe(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting user memories retrieval",
            data={
                "user_id": external_user_id,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "ascending": ascending,
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if external_user_id == "0":
            # Log anonymous user skip
            observability.observe(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping user memories retrieval for anonymous user",
                data={"user_id": external_user_id},
            )
            # Return empty list for anonymous users
            return []

        # Create a collection name based on the user ID
        collection = f"user_{external_user_id}"

        try:
            # Get memories from the collection
            memories = self.long_term_memory.get_recent_memories(collection=collection, limit=limit)

            results = [
                {
                    "content": memory.get("text", ""),
                    "metadata": memory.get("meta_data", {}),
                    "id": memory.get("id"),
                    "created_at": memory.get("created_at"),
                    "updated_at": memory.get("updated_at"),
                }
                for memory in memories
            ]

            # Log successful memory retrieval
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="User memories retrieval completed successfully",
                data={
                    "user_id": external_user_id,
                    "collection": collection,
                    "results_count": len(results),
                    "limit": limit,
                },
            )

            return results

        except Exception as e:
            # Log memory retrieval error
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_RETRIEVAL_FAILED,
                level=observability.EventLevel.ERROR,
                description="User memories retrieval operation failed",
                data={
                    "user_id": external_user_id,
                    "collection": collection,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise
