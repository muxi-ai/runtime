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
import json
import time
from typing import Any, Dict, List, Optional, Union

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
    CONTEXT_MEMORY_COLLECTION = "context_memory"
    CONTEXT_MEMORY_TYPE = "context_memory"

    def __init__(self, long_term_memory: LongTermMemory, default_user_id: int = 0):
        """
        Initialize the Memobase memory manager.

        Args:
            long_term_memory: PostgreSQL/PGVector-based long-term memory.
            default_user_id: The default user ID to use (0 for single-user
                mode).
        """
        self.default_user_id = default_user_id
        self.long_term_memory = long_term_memory

        # Log initialization
        observability.emit_event(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Memobase initialized",
            data={
                "default_user_id": default_user_id,
                "long_term_memory_type": type(long_term_memory).__name__,
            },
        )  # Don't let observability failures break initialization

    async def add(
        self,
        content: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        collection: Optional[str] = None,
    ) -> int:
        """
        Add content to memory for a specific user.

        This method stores information in a user-specific memory collection,
        automatically handling the appropriate collection naming and metadata
        tagging.

        Args:
            content: The content to add to memory.
            embedding: Optional pre-computed embedding for the content.
            metadata: Optional metadata to associate with the content.
            user_id: The user ID to add memory for. If None, uses the default
                user.
            collection: Optional collection name to store the memory in.
                If None, uses the default user collection.

        Returns:
            The ID of the newly created memory entry.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log memory store start
        observability.emit_event(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory store operation",
            data={
                "user_id": user_id,
                "content_length": len(content) if content else 0,
                "has_embedding": embedding is not None,
                "collection": collection,
                "metadata_keys": list(metadata.keys()) if metadata else [],
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory store for anonymous user",
                data={"user_id": user_id},
            )
            # Return dummy ID for anonymous users
            return 0

        metadata = metadata or {}

        # Add user_id to metadata
        metadata["user_id"] = user_id

        # Add timestamp if not provided
        if "timestamp" not in metadata:
            metadata["timestamp"] = time.time()

        # Create a collection name based on the user ID if not provided
        if collection is None:
            collection = f"user_{user_id}"

        try:
            # Ensure the collection exists
            try:
                self.long_term_memory._ensure_collection_exists(None, collection)
            except Exception:
                # If calling with None session fails, create collection properly
                self.long_term_memory.create_collection(collection, f"Memory for user {user_id}")

            # Add to long-term memory
            memory_id = await asyncio.to_thread(
                self.long_term_memory.add,
                text=content,
                embedding=embedding,
                metadata=metadata,
                collection=collection,
            )

            # Log successful memory store
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.INFO,
                description="Memory store completed successfully",
                data={
                    "user_id": user_id,
                    "memory_id": memory_id,
                    "collection": collection,
                    "content_length": len(content) if content else 0,
                },
            )

            return memory_id

        except Exception as e:
            # Log memory store error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="Memory store operation failed",
                data={
                    "user_id": user_id,
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
        user_id: Optional[int] = None,
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
            user_id: The user ID to search memory for. If None, uses the
                default user.
            additional_filter: Optional additional metadata filter.
            collection: Optional collection name to search in. If None, uses
                the default collection for the user.

        Returns:
            A list of memory entries, ordered by relevance.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log memory retrieval start
        observability.emit_event(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory search operation",
            data={
                "user_id": user_id,
                "query_length": len(query) if query else 0,
                "limit": limit,
                "collection": collection,
                "has_query_embedding": query_embedding is not None,
                "filter_keys": (list(additional_filter.keys()) if additional_filter else []),
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory search for anonymous user",
                data={"user_id": user_id},
            )
            # Return empty results for anonymous users
            return []

        additional_filter = additional_filter or {}

        # Add user_id to filter
        additional_filter["user_id"] = user_id

        # Create a collection name based on the user ID if not provided
        if collection is None:
            collection = f"user_{user_id}"

        try:
            # Search long-term memory
            search_results = await asyncio.to_thread(
                self.long_term_memory.search,
                query=query,
                query_embedding=query_embedding,
                filter_metadata=additional_filter,
                k=limit,
                collection=collection,
            )

            # Convert results to standard format
            results = []
            for distance, memory in search_results:
                results.append(
                    {
                        "content": memory.get("text", ""),
                        "metadata": memory.get("meta_data", {}),
                        "distance": distance,
                        "source": "memobase",
                        "id": memory.get("id"),
                        "created_at": memory.get("created_at"),
                    }
                )

            # Log successful memory retrieval
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="Memory search completed successfully",
                data={
                    "user_id": user_id,
                    "collection": collection,
                    "results_count": len(results),
                    "query_length": len(query) if query else 0,
                },
            )

            return results

        except Exception as e:
            # Log memory retrieval error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="Memory search operation failed",
                data={
                    "user_id": user_id,
                    "collection": collection,
                    "query": query,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def delete(
        self,
        memory_id: int,
        user_id: Optional[int] = None,
    ) -> bool:
        """
        Delete a specific memory entry.

        This method removes a specific memory entry from a user's collection,
        with appropriate handling for anonymous users.

        Args:
            memory_id: The ID of the memory to delete.
            user_id: The user ID associated with this memory. If None, uses the
                default user.

        Returns:
            True if deletion was successful, False otherwise.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log memory deletion start
        observability.emit_event(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting memory deletion operation",
            data={"user_id": user_id, "memory_id": memory_id},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory deletion for anonymous user",
                data={"user_id": user_id, "memory_id": memory_id},
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
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.INFO,
                description="Memory deletion completed",
                data={"user_id": user_id, "memory_id": memory_id, "success": success},
            )

            return success

        except Exception as e:
            # Log memory deletion error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="Memory deletion operation failed",
                data={
                    "user_id": user_id,
                    "memory_id": memory_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def clear_user_memory(self, user_id: Optional[int] = None) -> None:
        """
        Clear memory for a specific user by recreating their collection.

        This method deletes all memories associated with a user by dropping
        and recreating their collection.

        Args:
            user_id: The user ID to clear memory for. If None, uses the
                default user.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log memory clear start
        observability.emit_event(
            event_type=observability.SystemEvents.MEMORY_CLEAR,
            level=observability.EventLevel.INFO,
            description="Starting user memory clear operation",
            data={"user_id": user_id},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.SystemEvents.MEMORY_CLEAR,
                level=observability.EventLevel.DEBUG,
                description="Skipping memory clear for anonymous user",
                data={"user_id": user_id},
            )
            # No-op for anonymous users
            return

        # Create a collection name based on the user ID
        collection = f"user_{user_id}"

        try:
            # Drop and recreate the collection
            try:
                self.long_term_memory.delete_collection(collection)
            except Exception:
                pass  # Collection might not exist

            self.long_term_memory.create_collection(
                collection, f"Memory collection for user {user_id}"
            )

            # Log successful memory clear
            observability.emit_event(
                event_type=observability.SystemEvents.MEMORY_CLEAR,
                level=observability.EventLevel.INFO,
                description="User memory clear completed successfully",
                data={"user_id": user_id, "collection": collection},
            )

        except Exception as e:
            # Log memory clear error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User memory clear operation failed",
                data={
                    "user_id": user_id,
                    "collection": collection,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    def get_user_memories(
        self,
        user_id: Optional[int] = None,
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
            user_id: The user ID to get memories for. If None, uses the
                default user.
            limit: Maximum number of memories to return.
            offset: Number of memories to skip (for pagination).
            sort_by: Field to sort by (created_at, updated_at, id).
            ascending: Whether to sort in ascending order.

        Returns:
            A list of memory entries.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log memory retrieval start
        observability.emit_event(
            event_type=observability.ConversationEvents.REQUEST_PROCESSING,
            level=observability.EventLevel.INFO,
            description="Starting user memories retrieval",
            data={
                "user_id": user_id,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "ascending": ascending,
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                level=observability.EventLevel.DEBUG,
                description="Skipping user memories retrieval for anonymous user",
                data={"user_id": user_id},
            )
            # Return empty list for anonymous users
            return []

        # Create a collection name based on the user ID
        collection = f"user_{user_id}"

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
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_LONG_TERM_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="User memories retrieval completed successfully",
                data={
                    "user_id": user_id,
                    "collection": collection,
                    "results_count": len(results),
                    "limit": limit,
                },
            )

            return results

        except Exception as e:
            # Log memory retrieval error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User memories retrieval operation failed",
                data={
                    "user_id": user_id,
                    "collection": collection,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def add_user_context_memory(
        self,
        user_id: Optional[int] = None,
        knowledge: Dict[str, Any] = None,
        source: str = "explicit_upload",
        importance: float = 0.9,
    ) -> List[str]:
        """
        Add or update context memory about a user.

        This method stores persistent information about a user that should be
        accessible across conversations, such as preferences, profile information,
        or other user-specific context.

        Args:
            user_id: The user's ID. If None, uses the default user.
            knowledge: Dictionary of knowledge items where keys are knowledge
                categories and values are the corresponding information.
            source: Where this knowledge came from.
            importance: Importance score for this knowledge (0.0 to 1.0).
                Higher values make it more likely to be retrieved.

        Returns:
            List of memory IDs for the added knowledge items.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log context memory addition start
        observability.emit_event(
            event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
            level=observability.EventLevel.INFO,
            description="Starting user context memory addition",
            data={
                "user_id": user_id,
                "knowledge_keys": list(knowledge.keys()) if knowledge else [],
                "source": source,
                "importance": importance,
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
                level=observability.EventLevel.DEBUG,
                description="Skipping context memory addition for anonymous user",
                data={"user_id": user_id},
            )
            # Return empty list for anonymous users
            return []

        knowledge = knowledge or {}
        memory_ids = []

        try:
            # Ensure context memory collection exists
            collection_name = f"{self.CONTEXT_MEMORY_COLLECTION}_{user_id}"
            try:
                self.long_term_memory._ensure_collection_exists(None, collection_name)
            except Exception:
                self.long_term_memory.create_collection(
                    collection_name, f"Context memory for user {user_id}"
                )

            # Process each knowledge item
            for key, value in knowledge.items():
                # Format the content as "key: value"
                if isinstance(value, (dict, list)):
                    # Convert complex objects to JSON string
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)

                content = f"{key}: {value_str}"

                # Add metadata
                metadata = {
                    "type": self.CONTEXT_MEMORY_TYPE,
                    "key": key,
                    "source": source,
                    "importance": importance,
                    "user_id": user_id,
                }

                # Add to memory
                memory_id = await self.add(
                    content=content,
                    metadata=metadata,
                    user_id=user_id,
                    collection=collection_name,
                )

                memory_ids.append(memory_id)

            # Log successful context memory addition
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
                level=observability.EventLevel.INFO,
                description="User context memory addition completed successfully",
                data={
                    "user_id": user_id,
                    "collection": collection_name,
                    "memory_ids": memory_ids,
                    "knowledge_count": len(knowledge),
                },
            )

            return memory_ids

        except Exception as e:
            # Log context memory addition error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User context memory addition operation failed",
                data={
                    "user_id": user_id,
                    "source": source,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def get_user_context_memory(
        self,
        user_id: Optional[int] = None,
        keys: Optional[List[str]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Retrieve context memory about a user.

        This method fetches persistent user information that has been previously
        stored with add_user_context_memory, optionally filtering to specific keys.

        Args:
            user_id: The user's ID. If None, uses the default user.
            keys: Optional list of specific knowledge keys to retrieve.
                If None, retrieves all context memory.
            limit: Maximum number of knowledge items to retrieve.

        Returns:
            Dictionary of knowledge items where keys are knowledge categories
            and values are the corresponding information.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log context memory retrieval start
        observability.emit_event(
            event_type=observability.ConversationEvents.MEMORY_CONTEXT_RETRIEVED,
            level=observability.EventLevel.INFO,
            description="Starting user context memory retrieval",
            data={"user_id": user_id, "keys": keys, "limit": limit},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                description="Skipping context memory retrieval for anonymous user",
                data={"user_id": user_id},
            )
            # Return empty dictionary for anonymous users
            return {}

        collection_name = f"{self.CONTEXT_MEMORY_COLLECTION}_{user_id}"

        try:
            # Check if collection exists
            try:
                self.long_term_memory._ensure_collection_exists(None, collection_name)
            except Exception:
                # Collection doesn't exist, return empty dict
                observability.emit_event(
                    event_type=observability.ConversationEvents.MEMORY_CONTEXT_RETRIEVED,
                    level=observability.EventLevel.DEBUG,
                    description="Context memory collection does not exist",
                    data={"user_id": user_id, "collection": collection_name},
                )
                return {}

            # Prepare filter
            filter_params = {
                "type": self.CONTEXT_MEMORY_TYPE,
                "user_id": user_id,
            }

            results = []

            if keys:
                # Get specific keys
                for key in keys:
                    key_filter = filter_params.copy()
                    key_filter["key"] = key

                    key_results = await self.search(
                        query=key,  # Use key as query for better matching
                        user_id=user_id,
                        additional_filter=key_filter,
                        collection=collection_name,
                        limit=1,  # Only need the most recent/relevant for each key
                    )

                    results.extend(key_results)
            else:
                # Get all context memory
                # Use empty query to match all items
                results = await self.search(
                    query="",
                    user_id=user_id,
                    additional_filter=filter_params,
                    collection=collection_name,
                    limit=limit,
                )

            # Format results as a dictionary
            knowledge = {}
            for item in results:
                # Parse content in format "key: value"
                content = item["content"]
                if ": " in content:
                    key, value_str = content.split(": ", 1)

                    # Try to parse JSON values
                    try:
                        # Check if it's a JSON object or array
                        if (value_str.startswith("{") and value_str.endswith("}")) or (
                            value_str.startswith("[") and value_str.endswith("]")
                        ):
                            value = json.loads(value_str)
                        else:
                            value = value_str
                    except json.JSONDecodeError:
                        value = value_str

                    knowledge[key.strip()] = value

            # Log successful context memory retrieval
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="User context memory retrieval completed successfully",
                data={
                    "user_id": user_id,
                    "collection": collection_name,
                    "knowledge_keys": list(knowledge.keys()),
                    "results_count": len(results),
                },
            )

            return knowledge

        except Exception as e:
            # Log context memory retrieval error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User context memory retrieval operation failed",
                data={
                    "user_id": user_id,
                    "collection": collection_name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def import_user_context_memory(
        self,
        data_source: Union[str, Dict[str, Any]],
        user_id: Optional[int] = None,
        format: str = "json",
        source: str = "import",
        importance: float = 0.9,
    ) -> List[str]:
        """
        Import context memory from a file or data structure.

        This method provides a convenient way to bulk-import user knowledge
        from external sources like files or structured data objects.

        Args:
            data_source: Path to file or data structure containing knowledge.
            user_id: The user's ID. If None, uses the default user.
            format: Format of the data ("json" or "dict").
            source: Source identifier for the imported knowledge.
            importance: Importance score for this knowledge (0.0 to 1.0).

        Returns:
            List of memory IDs for the added knowledge items.

        Raises:
            ValueError: If the format is unsupported or the data cannot be parsed.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log context memory import start
        observability.emit_event(
            event_type=observability.ConversationEvents.CONTENT_PROCESSED,
            level=observability.EventLevel.INFO,
            description="Starting user context memory import",
            data={
                "user_id": user_id,
                "data_source_type": type(data_source).__name__,
                "format": format,
                "source": source,
                "importance": importance,
            },
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.DEBUG,
                description="Skipping context memory import for anonymous user",
                data={"user_id": user_id},
            )
            # Return empty list for anonymous users
            return []

        try:
            # Load data based on format
            if format == "json" and isinstance(data_source, str):
                try:
                    with open(data_source, "r") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    raise ValueError(f"Failed to load JSON file: {e}")
            elif isinstance(data_source, dict):
                data = data_source
            else:
                raise ValueError(f"Unsupported format: {format}")

            # Add the knowledge
            memory_ids = await self.add_user_context_memory(
                user_id=user_id,
                knowledge=data,
                source=source,
                importance=importance,
            )

            # Log successful context memory import
            observability.emit_event(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.INFO,
                description="User context memory import completed successfully",
                data={
                    "user_id": user_id,
                    "memory_ids": memory_ids,
                    "knowledge_count": len(data) if isinstance(data, dict) else 0,
                    "format": format,
                },
            )

            return memory_ids

        except Exception as e:
            # Log context memory import error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User context memory import operation failed",
                data={
                    "user_id": user_id,
                    "format": format,
                    "source": source,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def clear_user_context_memory(
        self,
        user_id: Optional[int] = None,
        keys: Optional[List[str]] = None,
    ) -> bool:
        """
        Clear context memory for a specific user.

        This method removes persistent user information, either all of it
        or just specific keys, supporting data deletion requirements.

        Args:
            user_id: The user's ID. If None, uses the default user.
            keys: Optional list of specific knowledge keys to clear.
                If None, clears all context memory.

        Returns:
            True if the operation was successful, False otherwise.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log context memory clear start
        observability.emit_event(
            event_type=observability.SystemEvents.MEMORY_CONTEXT_CLEARED,
            level=observability.EventLevel.INFO,
            description="Starting user context memory clear",
            data={"user_id": user_id, "keys": keys, "clear_all": keys is None},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.SystemEvents.MEMORY_CONTEXT_CLEARED,
                level=observability.EventLevel.DEBUG,
                description="Skipping context memory clear for anonymous user",
                data={"user_id": user_id},
            )
            # Return success for anonymous users (no-op)
            return True

        collection_name = f"{self.CONTEXT_MEMORY_COLLECTION}_{user_id}"

        try:
            if keys:
                # Clear specific keys
                for key in keys:
                    # Find memories with this key
                    filter_params = {
                        "type": self.CONTEXT_MEMORY_TYPE,
                        "key": key,
                        "user_id": user_id,
                    }

                    results = await self.search(
                        query="",
                        user_id=user_id,
                        additional_filter=filter_params,
                        collection=collection_name,
                        limit=100,  # Set a reasonable limit
                    )

                    # Delete each memory
                    for item in results:
                        if "id" in item:
                            await asyncio.to_thread(
                                self.long_term_memory.delete,
                                memory_id=item["id"],
                            )
            else:
                # Clear all context memory by recreating the collection
                try:
                    self.long_term_memory.delete_collection(collection_name)
                    self.long_term_memory.create_collection(
                        collection_name, f"Context memory for user {user_id}"
                    )
                except Exception:
                    # Log successful context memory clear
                    observability.emit_event(
                        event_type=observability.SystemEvents.MEMORY_CONTEXT_CLEARED,
                        level=observability.EventLevel.ERROR,
                        description="Failed to clear context memory collection",
                        data={"user_id": user_id, "collection": collection_name},
                    )
                    return False

            # Log successful context memory clear
            observability.emit_event(
                event_type=observability.SystemEvents.MEMORY_CONTEXT_CLEARED,
                level=observability.EventLevel.INFO,
                description="User context memory clear completed successfully",
                data={
                    "user_id": user_id,
                    "collection": collection_name,
                    "keys": keys,
                    "clear_all": keys is None,
                },
            )

            return True

        except Exception as e:
            # Log context memory clear error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User context memory clear operation failed",
                data={
                    "user_id": user_id,
                    "collection": collection_name,
                    "keys": keys,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

    async def update_user_context_memory(
        self,
        user_id: Optional[int] = None,
        key: str = None,
        value: Any = None,
        source: str = "update",
        importance: float = 0.9,
    ) -> int:
        """
        Update a specific key in user context memory.

        This method provides a convenient way to update a single piece of
        user information by first removing any existing values for the key
        and then adding the new value.

        Args:
            user_id: The user's ID. If None, uses the default user.
            key: The key to update.
            value: The new value for the key.
            source: Source identifier for this update.
            importance: Importance score for this knowledge (0.0 to 1.0).

        Returns:
            The memory ID of the updated item, or 0 if update failed.
        """
        user_id = user_id if user_id is not None else self.default_user_id

        # Log context memory update start
        observability.emit_event(
            event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
            level=observability.EventLevel.INFO,
            description="Starting user context memory update",
            data={"user_id": user_id, "key": key, "source": source, "importance": importance},
        )

        # Skip memory operations for anonymous users (user_id=0)
        if user_id == 0:
            # Log anonymous user skip
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
                level=observability.EventLevel.DEBUG,
                description="Skipping context memory update for anonymous user",
                data={"user_id": user_id, "key": key},
            )
            # Return 0 for anonymous users
            return 0

        if key is None:
            return 0

        try:
            # First clear the existing key if it exists
            await self.clear_user_context_memory(user_id=user_id, keys=[key])

            # Then add the new value
            memory_ids = await self.add_user_context_memory(
                user_id=user_id,
                knowledge={key: value},
                source=source,
                importance=importance,
            )

            memory_id = memory_ids[0] if memory_ids else 0

            # Log successful context memory update
            observability.emit_event(
                event_type=observability.ConversationEvents.MEMORY_CONTEXT_UPDATED,
                level=observability.EventLevel.INFO,
                description="User context memory update completed successfully",
                data={"user_id": user_id, "key": key, "memory_id": memory_id, "source": source},
            )

            return memory_id

        except Exception as e:
            # Log context memory update error
            observability.emit_event(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                description="User context memory update operation failed",
                data={
                    "user_id": user_id,
                    "key": key,
                    "source": source,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise
