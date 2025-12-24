# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Buffer Memory - Smart Context Window Implementation
# Description:  Hybrid recency and semantic search memory buffer implementation
# Role:         Provides temporary conversation memory with semantic search
# Usage:        Used by the Overlord to maintain conversation context
# Author:       Muxi Framework Team
#
# The Buffer Memory is a sophisticated working memory system that combines:
#
# 1. Recency-Based Memory
#    - Maintains a fixed-size context window of recent messages
#    - Ensures immediate conversation context is preserved
#    - Supports filtering by metadata (agent_id, user_id, etc.)
#
# 2. Semantic Search Capability
#    - Uses FAISS vector index for efficient similarity search
#    - Maintains embeddings for all messages in the buffer
#    - Enables retrieving contextually relevant information
#
# 3. Hybrid Retrieval Approach
#    - Combines recency and semantic relevance scores
#    - Configurable recency bias for different use cases
#    - Graceful fallback to recency-only if vector search unavailable
#
# The WorkingMemory uses a two-tiered size system:
#   - context_window (max_size): The number of recent messages to include
#   - buffer_multiplier: Total buffer capacity = max_size × buffer_multiplier
#
# This design addresses the need for a larger storage capacity while
# maintaining a smaller, focused context window for immediate conversations.
#
# Example usage:
#
#   # Create buffer memory with semantic search (local mode)
#   model = OpenAIModel(model="text-embedding-3-small")
#   buffer = WorkingMemory(
#       max_size=10,              # Context window size
#       buffer_multiplier=10,     # Total capacity = 10 × 10 = 100
#       model=model               # For generating embeddings
#   )
#
#   # Create buffer memory with remote FAISS/FAISSx server
#   buffer = WorkingMemory(
#       max_size=10,
#       buffer_multiplier=10,
#       model=model,
#       mode="remote",
#       remote={
#           "url": "tcp://localhost:45678",
#           "api_key": "your_api_key",
#           "tenant": "your_tenant"
#       }
#   )
#
#   # Add items to buffer
#   await buffer.add("User message", {"role": "user"})
#   await buffer.add("Assistant response", {"role": "assistant"})
#
#   # Search for relevant content
#   results = await buffer.search("topic of interest", recency_bias=0.3)
#
# The implementation includes thread-safety, automatic index rebuilding,
# and comprehensive error handling for production-grade reliability.
# =============================================================================

import collections
import signal
import time
from typing import Any, Dict, List, Optional

from faissx import client as faiss
import numpy as np
import multitasking

from .. import observability
from ..llm import LLM

# Set multitasking to thread mode for shared memory access
multitasking.set_engine("thread")

# Kill all tasks on ctrl-c for clean shutdown
# Only register signal handlers in main thread to avoid errors in tests
try:
    signal.signal(signal.SIGINT, multitasking.killall)
except ValueError:
    # Signal handlers can only be registered in main thread
    # This is expected in tests or when imported from threads
    pass


class WorkingMemory:
    """
    Working memory system with buffer management and vector search capabilities.

    WorkingMemory provides a hybrid memory system that combines recency-based retrieval
    with semantic search powered by FAISS/FAISSx. It maintains a buffer of messages with
    associated metadata and vector embeddings for efficient contextual search.

    The buffer operates with two key size parameters:
    - max_size (context window): Number of most recent items to include when retrieving by recency
    - buffer_multiplier: Factor to determine total buffer capacity (max_size × buffer_multiplier)

    This enables maintaining a larger storage for vector search while keeping a smaller
    context window for recent conversations.

    Supports both local and remote FAISS modes:
    - Local mode: Uses local FAISS for in-memory vector storage
    - Remote mode: Connects to remote FAISS/FAISSx server for distributed vector storage

    When no embedding model is configured, automatically falls back to local
    sentence-transformer embeddings (all-MiniLM-L6-v2, 384 dimensions).
    """

    # Namespaces excluded from FIFO cleanup
    _NAMESPACES_EXCLUDED_FROM_FIFO = [
        "knowledge",
        "sops",
        "user_synopsis_identity",  # Permanent cache, explicit invalidation
        "user_synopsis_context",  # TTL-based, self-managing
    ]

    def __init__(
        self,
        formation_id: str,
        max_size: int = 10,
        buffer_multiplier: int = 10,
        dimension: int = 1536,
        model=None,
        mode: str = "local",
        remote: Optional[Dict[str, Any]] = None,
        max_memory_mb: int = 1000,
        fifo_interval_min: int = 5,
    ):
        """
        Initialize working memory with vector search capabilities.

        Args:
            formation_id: The formation ID for scoping data
            max_size: The context window size - number of recent messages to include
                when retrieving by recency. Default is 10.
            buffer_multiplier: Multiplier to determine total buffer capacity.
                Total capacity = max_size × buffer_multiplier. Default is 10.
            dimension: Dimension of embedding vectors. Default is 1536, which matches
                OpenAI's text-embedding-3-small model.
            model: Optional language model instance for generating embeddings.
                Must have an async embed(text) method. If None, vector search
                will be disabled and only recency-based retrieval will be used.
            mode: FAISS mode - "local" for in-memory storage or "remote" for
                server-based storage. Default is "local".
            remote: Remote server configuration when mode is "remote". Should contain:
                - url: FAISS/FAISSx server URL (e.g., "tcp://localhost:45678")
                - api_key: Optional API key for authentication
                - tenant: Optional tenant ID for multi-tenancy
            max_memory_mb: Maximum memory usage in MB for FIFO cleanup. Default is 1000.
            fifo_interval_min: Minimum interval in minutes for FIFO cleanup. Default is 5.
        """
        # Formation ID for scoping
        self.formation_id = formation_id

        # Buffer size and content
        self.max_size = max_size
        self.buffer_multiplier = buffer_multiplier
        self.buffer_size = max_size * buffer_multiplier
        self.buffer = collections.deque(maxlen=self.buffer_size)
        self.max_memory_mb = max_memory_mb
        self.fifo_interval_min = fifo_interval_min

        # Vector search configuration
        self.mode = mode
        self.remote = remote or {}
        self.has_vector_search = True

        # Model can be either an LLM instance or a model name string
        self._model = None
        self._model_name = None
        self._use_local_embeddings = False
        self._local_embedding_logged = False

        if model:
            if isinstance(model, str):
                # Model name provided - will create LLM instance lazily
                self._model_name = model
                self.dimension = dimension
            else:
                # Assume it's an LLM instance
                self._model = model
                self.dimension = dimension
        else:
            # No embedding model configured - use local fallback
            self._use_local_embeddings = True
            from .local_embeddings import get_local_embedding_dimension

            self.dimension = get_local_embedding_dimension()

        # Configure FAISS for remote mode (FAISSx-specific)
        if mode == "remote" and self.remote:
            faiss.configure(
                server=self.remote.get("url"),
                api_key=self.remote.get("api_key"),
                tenant_id=self.remote.get("tenant"),
            )
        elif mode != "local" and mode != "remote":
            raise ValueError(f"Invalid mode: {mode}. Must be 'local' or 'remote'")

        # Initialize vector storage
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index_mapping = {}  # Maps buffer indices to FAISS indices
        self.index_count = 0  # Counter for FAISS indices
        self.needs_rebuild = False  # Flag to track if index needs rebuilding

        # Key-value store for exact lookups with TTL
        self.kv_store = {}
        self.kv_expiry = {}

        # Start the background FIFO cleanup task
        fifo_cleanup_task(self)

    @property
    def model(self):
        """Get the model, creating it lazily if needed.

        If no API-based embedding model is configured, returns a LocalEmbeddingProvider
        that uses sentence-transformers for local embedding generation.
        """
        # Check if we should use local embeddings
        if self._use_local_embeddings:
            if self._model is None:
                from .local_embeddings import LocalEmbeddingProvider

                self._model = LocalEmbeddingProvider()

                # Log once about using local embeddings
                if not self._local_embedding_logged:
                    observability.observe(
                        event_type=observability.ConversationEvents.REQUEST_PROCESSING,
                        level=observability.EventLevel.INFO,
                        data={
                            "embedding_model": "all-MiniLM-L6-v2",
                            "dimension": self.dimension,
                            "type": "local_fallback",
                        },
                        description=(
                            "Using local embedding model for buffer memory (all-MiniLM-L6-v2). "
                            "For better quality, configure: llm.models.embedding"
                        ),
                    )
                    self._local_embedding_logged = True
            return self._model

        # API-based embedding model
        if self._model is None and self._model_name:
            # Create LLM instance lazily
            # Note: This is synchronous creation, which should work for most cases
            # If async is needed, the model creation should happen in add/search methods
            try:
                self._model = LLM(model=self._model_name)
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.LLM_INITIALIZATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "model_name": self._model_name,
                        "error": str(e),
                    },
                    description=f"Failed to create LLM instance for embeddings: {e}",
                )
                # Disable vector search if model creation fails
                self._model_name = None
                self.has_vector_search = False
        return self._model

    async def add(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, namespace: str = "buffer"
    ) -> None:
        """
        Add an item to the buffer memory.

        This method adds a new text item to the buffer with its associated metadata.
        If a language model is available, it also generates and stores an embedding
        vector for the text, enabling semantic search functionality.

        Args:
            text: The text content to add to the buffer. This is what will be searched
                and retrieved later.
            metadata: Optional dictionary of metadata associated with this text.
                Can include any contextual information like timestamps, user IDs,
                message roles, etc. Default is an empty dictionary.
            namespace: Namespace for organizing items (e.g., "buffer", "doc").
                Used for namespaced ID generation. Default is "buffer".
        """
        # Initialize metadata dictionary if None
        if metadata is None:
            metadata = {}

        # Automatically add formation_id to metadata
        metadata["formation_id"] = self.formation_id

        # Create item with text, metadata, timestamp, and namespace
        item = {
            "text": text,
            "metadata": metadata,
            "timestamp": time.time(),
            "namespace": namespace,
        }

        # Generate embedding if model is available and text is not empty
        if self.model and text and text.strip():
            try:
                # Generate embedding for the text
                embedding = await self.model.embed(text)

                # Handle different response types from LLM.embed()
                if hasattr(embedding, "embedding"):
                    embedding_vector = embedding.embedding
                elif hasattr(embedding, "data") and len(embedding.data) > 0:
                    embedding_vector = embedding.data[0].embedding
                elif isinstance(embedding, list):
                    embedding_vector = embedding
                else:
                    embedding_vector = list(embedding)

                item["embedding"] = embedding_vector

                # Record the mapping from buffer index to FAISS index
                buffer_idx = len(self.buffer)
                self.index_mapping[buffer_idx] = self.index_count

                # Normalize embedding for better cosine similarity in FAISS
                embedding_array = np.array([embedding_vector], dtype=np.float32)
                norm = np.linalg.norm(embedding_array[0])
                if norm > 0:
                    embedding_array = embedding_array / norm

                # Add the normalized embedding to the FAISS index
                self.index.add(embedding_array)

                # Increment the FAISS index counter
                self.index_count += 1
            except Exception as e:
                # Handle embedding generation failures gracefully
                _ = e  # remove this after implementing observability
                item["embedding"] = None
        else:
            # No embedding if model is not available
            item["embedding"] = None

        # Add item to the buffer
        self.buffer.append(item)

        # Check if we need to rebuild the index (buffer is full and items were removed)
        if len(self.buffer) == self.buffer_size and self.model:
            self.needs_rebuild = True

    def _rebuild_index(self) -> None:
        """
        Rebuild the FAISS index after buffer overflow.

        This internal method rebuilds the FAISS index and mapping when the buffer
        is full and new items have displaced old ones. It ensures the vector search
        stays in sync with the actual buffer contents.
        """
        if not self.model:
            return

        # Create a new index with the same dimension
        new_index = faiss.IndexFlatL2(self.dimension)
        new_mapping = {}
        new_count = 0

        # Add embeddings from the current buffer to the new index
        embeddings = []
        for i, item in enumerate(self.buffer):
            if "embedding" in item and item["embedding"] is not None:
                embeddings.append(item["embedding"])
                new_mapping[i] = new_count
                new_count += 1

        # Add collected embeddings to the index if any exist
        if embeddings:
            embeddings_array = np.array(embeddings, dtype=np.float32)
            new_index.add(embeddings_array)

        # Replace the old index and mapping
        self.index = new_index
        self.index_mapping = new_mapping
        self.index_count = new_count
        self.needs_rebuild = False

    def check_memory_usage_and_cleanup(self) -> None:
        """
        Check memory usage and perform FIFO cleanup if needed.
        Now includes KV store cleanup for non-excluded namespaces.

        This method checks if the estimated buffer memory usage exceeds the configured
        max_memory_mb limit. If so, it removes the oldest items from the buffer
        and rebuilds the index to maintain memory constraints.

        The buffer manages its own memory budget based on the configured limit
        rather than checking system-wide memory usage.

        IMPORTANT: Only removes items with namespace="buffer" to protect knowledge
        and uploaded documents from being evicted.
        """
        try:
            # Estimate current memory usage of the buffer (rough approximation)
            # Each item has text + metadata + embedding (if present)
            estimated_usage_mb = 0
            buffer_namespace_indices = []  # Track indices of buffer namespace items

            for i, item in enumerate(self.buffer):
                # Rough estimate: text size + metadata size + embedding size
                text_size = len(item["text"].encode("utf-8"))
                metadata_size = len(str(item["metadata"]).encode("utf-8"))
                embedding_size = 0
                if item.get("embedding"):
                    embedding_size = len(item["embedding"]) * 4  # 4 bytes per float32

                item_size_mb = (text_size + metadata_size + embedding_size) / (1024**2)
                estimated_usage_mb += item_size_mb

                # Track buffer namespace items for potential removal
                if item.get("namespace", "buffer") == "buffer":
                    buffer_namespace_indices.append(i)

            # Include KV store items in memory estimation
            if self.kv_store:
                for key, value in self.kv_store.items():
                    # Estimate size of key and value
                    key_size = len(key.encode("utf-8"))
                    value_size = len(str(value).encode("utf-8"))
                    kv_item_size_mb = (key_size + value_size) / (1024**2)
                    estimated_usage_mb += kv_item_size_mb

            #     f"Buffer memory usage: {estimated_usage_mb:.2f}MB, "
            #     f"configured limit: {self.max_memory_mb}MB"
            # )

            # If we exceed the configured limit, remove oldest items from buffer namespace only
            if estimated_usage_mb > self.max_memory_mb and buffer_namespace_indices:
                # Calculate how many buffer items to remove (25% of buffer items)
                items_to_remove = max(1, len(buffer_namespace_indices) // 4)
                #     f"Buffer memory limit ({self.max_memory_mb}MB) exceeded. "
                #     f"Removing {items_to_remove} oldest items from buffer namespace"
                # )

                # Remove oldest buffer namespace items efficiently
                # Sort indices to remove oldest items first
                buffer_namespace_indices.sort()
                indices_to_remove = set(buffer_namespace_indices[:items_to_remove])

                # Create new deque with same maxlen, keeping only non-removed items
                new_buffer = collections.deque(maxlen=self.buffer.maxlen)
                for i, item in enumerate(self.buffer):
                    if i not in indices_to_remove:
                        new_buffer.append(item)

                # Replace the buffer
                self.buffer = new_buffer

                # Rebuild the index after removing items
                if self.model:
                    self._rebuild_index()

            # NEW: KV Store cleanup
            if self.kv_store and estimated_usage_mb > self.max_memory_mb:
                # Get all namespaces in KV store
                all_namespaces = set()
                for key in self.kv_store.keys():
                    if ":" in key:  # Format: "namespace:actual_key"
                        namespace = key.split(":", 1)[0]
                        all_namespaces.add(namespace)

                # Clean up non-excluded namespaces
                for namespace in all_namespaces:
                    if namespace in self._NAMESPACES_EXCLUDED_FROM_FIFO:
                        continue

                    # Get all items in this namespace sorted by timestamp
                    namespace_items = []
                    for key in list(self.kv_store.keys()):
                        if key.startswith(f"{namespace}:"):
                            item = self.kv_store[key]
                            # Add timestamp if not present (use current time as fallback)
                            timestamp = item.get("timestamp", item.get("created_at", time.time()))
                            namespace_items.append((timestamp, key))

                    # Sort by timestamp (oldest first) and remove oldest items
                    namespace_items.sort()

                    # Remove oldest 10% of items in this namespace
                    items_to_remove = max(1, len(namespace_items) // 10)
                    for _, key in namespace_items[:items_to_remove]:
                        del self.kv_store[key]
                        # Log the removal for observability
                        #     f"Removed KV item {key} from namespace {namespace}"
                        # )

        except Exception as e:
            _ = e  # remove this after implementing observability

    def _recency_search(
        self,
        limit: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        use_entire_buffer: bool = True,
        namespace: str = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the buffer based on recency only.

        This internal method searches the buffer based solely on recency (most recent first)
        and applies optional metadata filtering. It's used as a fallback when vector
        search is not available or as part of the hybrid search approach.

        Args:
            limit: Maximum number of results to return. Default is 10.
            filter_metadata: Optional dictionary of metadata for filtering.
                Only items with matching metadata values will be included.
            use_entire_buffer: Whether to search the entire buffer or just the context window
                (max_size most recent items).

        Returns:
            List of buffer items (dictionaries) with matching metadata,
            ordered by recency (most recent first).
        """
        # Determine search scope - either entire buffer or just the context window
        if use_entire_buffer:
            recent_items = list(self.buffer)
        else:
            # Use only the most recent items (up to max_size) - the context window
            recent_items = list(self.buffer)[-self.max_size:]

        # Apply filtering if specified
        if filter_metadata or namespace or session_id:
            results = []
            for item in reversed(recent_items):  # Reverse to get most recent first
                # Apply namespace filter if provided
                if namespace and item.get("namespace") != namespace:
                    continue

                # Check formation_id match (always filter by formation)
                if item.get("metadata", {}).get("formation_id") != self.formation_id:
                    continue

                # Apply session_id filter if provided
                if session_id and item.get("metadata", {}).get("session_id") != session_id:
                    continue

                # Check if all metadata filter criteria match
                if filter_metadata and not all(
                    key in item["metadata"] and item["metadata"][key] == value
                    for key, value in filter_metadata.items()
                ):
                    continue

                # Include a copy of the item to avoid modifying the buffer
                results.append(item.copy())
                # Stop if we've reached the limit
                if len(results) >= limit:
                    break
            return results
        else:
            # If no filtering, still filter by formation_id
            results = []
            for item in reversed(recent_items):
                if item.get("metadata", {}).get("formation_id") == self.formation_id:
                    results.append(item.copy())
                    if len(results) >= limit:
                        break
            return results

    async def search(
        self,
        query: str,
        limit: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        query_vector: Optional[List[float]] = None,
        recency_bias: float = 0.3,
        namespace: str = None,
        session_id: Optional[str] = None,
        session_bias: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search the buffer using vector similarity and recency.

        This method performs a hybrid search that combines semantic similarity with
        recency bias. It can use a pre-computed query vector or generate one from
        the query text if a model is available.

        Args:
            query: The search query text. Used to generate a query vector if
                query_vector is not provided.
            limit: Maximum number of results to return. Default is 10.
            filter_metadata: Optional dictionary of metadata for filtering.
                Only items with matching metadata values will be included.
            query_vector: Optional pre-computed query vector. If provided,
                skips the embedding generation step.
            recency_bias: Weight given to recency vs. semantic similarity (0.0-1.0).
                Higher values favor recent items, lower values favor semantic similarity.
                Default is 0.3, providing a balance that slightly favors similarity.
            namespace: Optional namespace filter. If provided, only items
                in this namespace will be considered for search.

        Returns:
            List of matched items sorted by the combined score of semantic
            similarity and recency. Each item includes the original text, metadata,
            and a score field indicating the match quality.
        """
        # Extract session_id from filter_metadata if not provided separately
        if session_id is None and filter_metadata and "session_id" in filter_metadata:
            session_id = filter_metadata["session_id"]
            # Create a copy of filter_metadata without session_id to avoid double filtering
            filter_metadata = {k: v for k, v in filter_metadata.items() if k != "session_id"}

        # Emit memory retrieval started event
        observability.observe(
            event_type=observability.ConversationEvents.MEMORY_WORKING_LOOKUP,
            level=observability.EventLevel.INFO,
            data={
                "query_length": len(query),
                "limit": limit,
                "has_filter": filter_metadata is not None,
                "has_query_vector": query_vector is not None,
                "recency_bias": recency_bias,
                "session_id": session_id,
                "session_bias": session_bias,
                "buffer_size": len(self.buffer),
                "has_vector_search": self.model is not None,
            },
            description="Working memory search started",
        )

        # If we don't have a model, return most recent messages
        if not self.model:
            # Fall back to recency search when no embedding model is available
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.INFO,
                data={
                    "search_type": "recency_fallback_no_model",
                    "query_length": len(query),
                    "buffer_size": len(self.buffer),
                },
                description="Working memory using recency search (no embedding model configured)",
            )
            recency_results = self._recency_search(
                limit,
                filter_metadata,
                use_entire_buffer=True,
                namespace=namespace,
                session_id=session_id,
            )

            # Emit memory retrieval completed event for recency-only search
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.INFO,
                data={
                    "results_count": len(recency_results),
                    "search_type": "recency_only",
                    "query_length": len(query),
                    "buffer_size": len(self.buffer),
                },
                description="Working memory search completed (recency-only)",
            )

            return recency_results

        # Rebuild index if needed
        if self.needs_rebuild:
            self._rebuild_index()

        # Generate a query vector if not provided
        if query_vector is None:
            try:
                query_embedding = await self.model.embed(query)

                # Handle different response types
                if hasattr(query_embedding, "embedding"):
                    query_vector = query_embedding.embedding
                elif hasattr(query_embedding, "data") and len(query_embedding.data) > 0:
                    query_vector = query_embedding.data[0].embedding
                elif isinstance(query_embedding, list):
                    query_vector = query_embedding
                else:
                    query_vector = list(query_embedding)

            except Exception as e:
                # Log embedding generation failure and fallback
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "operation": "query_embedding_generation",
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "query_length": len(query),
                    },
                    description="Failed to generate query embedding for working memory search",
                )
                # Fallback to recency search if embedding generation fails
                embedding_fallback_results = self._recency_search(
                    limit,
                    filter_metadata,
                    use_entire_buffer=True,
                    namespace=namespace,
                    session_id=session_id,
                )

                # Emit memory retrieval completed event for embedding failure fallback
                observability.observe(
                    event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                    level=observability.EventLevel.WARNING,
                    data={
                        "results_count": len(embedding_fallback_results),
                        "search_type": "embedding_failure_fallback",
                        "error": str(e),
                        "query_length": len(query),
                        "buffer_size": len(self.buffer),
                    },
                    description=(
                        "Working memory search completed " "(embedding failure fallback)"
                    ),
                )

                return embedding_fallback_results

        # If we have no embeddings in the index, use recency search
        if self.index_count == 0:
            return self._recency_search(
                limit,
                filter_metadata,
                use_entire_buffer=True,
                namespace=namespace,
                session_id=session_id,
            )

        # If query vector is empty (e.g., from empty query string), use recency search
        if not query_vector or len(query_vector) == 0:
            return self._recency_search(
                limit,
                filter_metadata,
                use_entire_buffer=True,
                namespace=namespace,
                session_id=session_id,
            )

        try:
            # Convert query vector to numpy array and normalize
            query_np = np.array([query_vector], dtype=np.float32)
            norm = np.linalg.norm(query_np[0])
            if norm > 0:
                query_np = query_np / norm

            # Search the FAISS index for similar vectors
            k = min(limit * 2, self.index_count)  # Get more results to allow for filtering
            distances, indices = self.index.search(query_np, k)

            # Map FAISS indices back to buffer indices
            buffer_indices = []
            for faiss_idx in indices[0]:
                # Find the buffer index for this FAISS index
                for buffer_idx, mapped_faiss_idx in self.index_mapping.items():
                    if mapped_faiss_idx == faiss_idx:
                        buffer_indices.append(buffer_idx)
                        break

            # Combine semantic score with recency score
            results = []
            for i, buffer_idx in enumerate(buffer_indices):
                # Make sure buffer_idx is in range
                if buffer_idx >= len(self.buffer):
                    continue

                item = self.buffer[buffer_idx].copy()

                # Apply namespace filter if provided
                if namespace and item.get("namespace") != namespace:
                    continue

                # Check formation_id match (always filter by formation)
                if item.get("metadata", {}).get("formation_id") != self.formation_id:
                    continue

                # Apply session_id filter as a hard filter if provided
                if session_id and item.get("metadata", {}).get("session_id") != session_id:
                    continue

                # Apply metadata filters if provided
                if filter_metadata and not all(
                    key in item["metadata"] and item["metadata"][key] == value
                    for key, value in filter_metadata.items()
                ):
                    continue

                # Calculate combined score without session weighting
                # (session_id is now a hard filter applied above)
                semantic_score = 1.0 / (1.0 + float(distances[0][i]))
                recency_score = 1.0 - (buffer_idx / len(self.buffer))

                # Use original recency bias formula
                # This preserves perfect scores for exact matches
                combined_score = (1 - recency_bias) * semantic_score + recency_bias * recency_score

                # Add score to the item
                item["score"] = combined_score
                results.append(item)

                # Stop if we have enough results
                if len(results) >= limit:
                    break

            # If we don't have enough results, try recency search
            if not results:
                return self._recency_search(
                    limit,
                    filter_metadata,
                    use_entire_buffer=True,
                    namespace=namespace,
                    session_id=session_id,
                )

            # Sort by combined score (descending)
            results.sort(key=lambda x: x["score"], reverse=True)
            final_results = results[:limit]

            # Emit memory retrieval completed event
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.INFO,
                description=f"Working memory vector search completed: {len(final_results)} results",
                data={
                    "results_count": len(final_results),
                    "search_type": "vector_hybrid",
                    "query_length": len(query),
                    "buffer_size": len(self.buffer),
                    "session_id": session_id,
                    "session_matches": (
                        sum(
                            1
                            for r in final_results
                            if r.get("metadata", {}).get("session_id") == session_id
                        )
                        if session_id
                        else 0
                    ),
                },
            )

            return final_results

        except Exception as e:
            # Handle FAISS search errors gracefully
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "vector_search",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "buffer_size": len(self.buffer),
                },
                description="Vector search failed in working memory, falling back to recency search",
            )
            fallback_results = self._recency_search(
                limit, filter_metadata, use_entire_buffer=True, namespace=namespace
            )

            # Emit memory retrieval completed event for fallback
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.WARNING,
                data={
                    "results_count": len(fallback_results),
                    "search_type": "recency_fallback",
                    "error": str(e),
                    "query_length": len(query),
                    "buffer_size": len(self.buffer),
                },
                description="Working memory search completed with fallback",
            )

            return fallback_results

    def get_recent_items(
        self, limit: int = 10, filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent items from the buffer.

        This method retrieves the most recent items from the buffer,
        optionally filtered by metadata. It uses pure recency ordering
        without any semantic search.

        Args:
            limit: Maximum number of items to return. Default is 10.
            filter_metadata: Optional dictionary of metadata for filtering.
                Only items with matching metadata values will be included.

        Returns:
            List of the most recent items matching the filter criteria.
        """
        return self._recency_search(limit, filter_metadata, use_entire_buffer=False)

    def get_items_by_namespace(
        self, namespace: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get items from the buffer filtered by namespace.

        Args:
            namespace: The namespace to filter by (e.g., "buffer", "doc").
            limit: Optional maximum number of items to return.

        Returns:
            List of buffer items matching the namespace, ordered by recency.
        """
        items = []
        for item in reversed(self.buffer):  # Most recent first
            if (
                item.get("namespace") == namespace
                and item.get("metadata", {}).get("formation_id") == self.formation_id
            ):
                items.append(item.copy())
                if limit and len(items) >= limit:
                    break
        return items

    def remove_by_metadata(self, metadata_filter: Dict[str, Any], namespace: str = None) -> int:
        """
        Remove items matching metadata filter and optional namespace.

        Args:
            metadata_filter: Dictionary of metadata key-value pairs to match.
                Only items with matching metadata values will be removed.
            namespace: Optional namespace filter. If provided, only items
                in this namespace will be considered for removal.

        Returns:
            Number of items removed from the buffer.
        """
        removed_count = 0
        items_to_remove = []

        for i, item in enumerate(self.buffer):
            # Check namespace filter
            if namespace and item.get("namespace") != namespace:
                continue

            # Check formation_id match
            if item.get("metadata", {}).get("formation_id") != self.formation_id:
                continue

            # Check metadata filter
            if all(item["metadata"].get(k) == v for k, v in metadata_filter.items()):
                items_to_remove.append(i)

        # Remove items in reverse order to maintain indices
        for i in reversed(items_to_remove):
            del self.buffer[i]
            removed_count += 1

        # Mark index for rebuild if we removed items
        if removed_count > 0:
            self.needs_rebuild = True

        return removed_count

    def get_items_by_metadata(
        self, metadata_filter: Dict[str, Any], namespace: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get items matching metadata filter and optional namespace.

        Args:
            metadata_filter: Dictionary of metadata key-value pairs to match.
                Only items with matching metadata values will be returned.
            namespace: Optional namespace filter. If provided, only items
                in this namespace will be considered.

        Returns:
            List of buffer items matching the filter criteria.
        """
        results = []
        for item in self.buffer:
            # Check namespace filter
            if namespace and item.get("namespace") != namespace:
                continue

            # Check formation_id match
            if item.get("metadata", {}).get("formation_id") != self.formation_id:
                continue

            # Check metadata filter
            if all(item["metadata"].get(k) == v for k, v in metadata_filter.items()):
                results.append(item.copy())

        return results

    async def add_with_embedding(
        self,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None,
        namespace: str = "buffer",
    ) -> None:
        """
        Add item with pre-computed embedding (for documents).

        This method allows adding items with pre-computed embeddings, which is
        useful
        for documents that have already been processed through an embedding model.
        It bypasses the model.embed() call and directly adds the embedding to the FAISS index.

        Args:
            text: The text content to add to the buffer.
            embedding: Pre-computed embedding vector for the text.
            metadata: Optional dictionary of metadata associated with this text.
            namespace: Namespace for organizing items (e.g., "buffer", "documents").
        """
        if metadata is None:
            metadata = {}

        # Automatically add formation_id to metadata
        metadata["formation_id"] = self.formation_id

        # Create item
        item = {
            "text": text,
            "metadata": metadata,
            "timestamp": time.time(),
            "namespace": namespace,
            "embedding": embedding,  # Store pre-computed embedding
        }

        # Add to buffer
        self.buffer.append(item)

        # Add to FAISS index directly if vector search is enabled
        if self.has_vector_search:
            try:
                if isinstance(embedding, list):
                    embedding_np = np.array([embedding], dtype=np.float32)
                else:
                    embedding_np = embedding.reshape(1, -1)

                # Normalize embedding for better cosine similarity in FAISS
                norm = np.linalg.norm(embedding_np[0])
                if norm > 0:
                    embedding_np = embedding_np / norm

                self.index.add(embedding_np)

                # Update mapping
                buffer_idx = len(self.buffer) - 1
                self.index_mapping[buffer_idx] = self.index_count
                self.index_count += 1

            except Exception as e:
                # If FAISS fails, keep the item in buffer but disable vector search for this item
                observability.observe(
                    event_type=observability.ErrorEvents.INTERNAL_ERROR,
                    level=observability.EventLevel.WARNING,
                    description="Failed to add pre-computed embedding to FAISS index",
                    data={
                        "error": str(e),
                        "text_length": len(text),
                        "embedding_dimension": len(embedding),
                        "namespace": namespace,
                    },
                )

    def clear(self) -> None:
        """
        Clear the buffer memory.

        This method removes all items from the buffer and resets the FAISS index
        if vector search is enabled. It effectively resets the memory to an empty state.
        """
        # Clear the buffer
        self.buffer.clear()

        # Reset FAISS index if enabled
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index_mapping = {}
        self.index_count = 0
        self.needs_rebuild = False

        # Clear key-value store
        self.kv_store.clear()
        self.kv_expiry.clear()

    async def restore_session(
        self,
        user_id: str,
        session_id: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """
        Restore a session by clearing existing messages and loading new ones.

        This enables developers to implement persistent chat history in their own
        database while using MUXI's ephemeral buffer for active conversations.

        Args:
            user_id: User ID to restore messages for
            session_id: Session ID to restore
            messages: List of messages to load, each with:
                - role: "user", "assistant", or "system"
                - content: Message content
                - timestamp: ISO 8601 timestamp string
                - agent_id: Optional agent ID (for assistant messages)
                - metadata: Optional additional metadata

        Returns:
            Dict with:
                - messages_loaded: Number of messages successfully loaded
                - messages_dropped: Number of messages dropped due to buffer limits
        """
        from datetime import datetime

        # First, remove existing messages for this user+session
        items_to_keep = []
        for item in self.buffer:
            metadata = item.get("metadata", {})
            if metadata.get("user_id") == user_id and metadata.get("session_id") == session_id:
                continue  # Skip - will be replaced
            items_to_keep.append(item)

        # Clear and rebuild buffer with remaining items
        self.buffer.clear()
        for item in items_to_keep:
            self.buffer.append(item)

        # Sort incoming messages by timestamp
        def parse_timestamp(msg):
            ts = msg.get("timestamp", "")
            if isinstance(ts, str):
                try:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except ValueError:
                    return 0.0
            return float(ts) if ts else 0.0

        sorted_messages = sorted(messages, key=parse_timestamp)

        # Calculate how many we can load
        available_space = self.buffer_size - len(self.buffer)
        messages_to_load = sorted_messages[-available_space:] if len(sorted_messages) > available_space else sorted_messages
        messages_dropped = len(sorted_messages) - len(messages_to_load)

        # Add messages to buffer
        for msg in messages_to_load:
            timestamp = parse_timestamp(msg)
            metadata = {
                "user_id": user_id,
                "session_id": session_id,
                "role": msg.get("role", "user"),
                "timestamp": timestamp,
                "formation_id": self.formation_id,
            }
            if msg.get("agent_id"):
                metadata["agent_id"] = msg["agent_id"]
            if msg.get("metadata"):
                metadata.update(msg["metadata"])

            # Add without embedding for now (restored messages don't need vector search)
            item = {
                "text": msg.get("content", ""),
                "metadata": metadata,
                "timestamp": timestamp,
                "namespace": "buffer",
                "embedding": None,
            }
            self.buffer.append(item)

        # Mark index for rebuild if we have vector search
        if self.model and messages_to_load:
            self.needs_rebuild = True

        return {
            "messages_loaded": len(messages_to_load),
            "messages_dropped": messages_dropped,
        }

    async def kv_set(self, key: str, value: dict, ttl: int = 300, namespace: str = None) -> None:
        """
        Store key-value data with TTL and optional namespace.

        Args:
            key: The key to store the value under
            value: The dictionary value to store
            ttl: Time to live in seconds (default: 5 minutes, None for no expiry)
            namespace: Optional namespace for key isolation (e.g., "clarification", "workflow")
        """
        full_key = f"{namespace}:{key}" if namespace else key
        self.kv_store[full_key] = value
        # Only set expiry if ttl is provided (not None)
        if ttl is not None:
            self.kv_expiry[full_key] = time.time() + ttl
        elif full_key in self.kv_expiry:
            # Remove expiry if ttl is None
            del self.kv_expiry[full_key]

    async def kv_get(self, key: str, namespace: str = None) -> Optional[dict]:
        """
        Get by exact key, respecting TTL and optional namespace.

        Args:
            key: The key to retrieve
            namespace: Optional namespace for key isolation

        Returns:
            The stored dictionary value or None if not found/expired
        """
        full_key = f"{namespace}:{key}" if namespace else key

        # Check if key exists and is not expired
        if full_key in self.kv_expiry and time.time() > self.kv_expiry[full_key]:
            await self.kv_delete(key, namespace)
            return None
        return self.kv_store.get(full_key)

    async def kv_delete(self, key: str, namespace: str = None) -> None:
        """
        Delete by exact key with optional namespace.

        Args:
            key: The key to delete
            namespace: Optional namespace for key isolation
        """
        full_key = f"{namespace}:{key}" if namespace else key
        self.kv_store.pop(full_key, None)
        self.kv_expiry.pop(full_key, None)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the buffer memory.

        This method returns information about the current state of the buffer
        memory, including size information, vector search availability, and
        other relevant metrics.

        Returns:
            Dictionary with statistics about the buffer memory:
            - buffer_length: Current number of items in the buffer
            - buffer_capacity: Maximum number of items the buffer can hold
            - context_window_size: Size of the context window (max_size)
            - has_vector_search: Whether vector search is available
            - vector_index_size: Number of vectors in the FAISS index
            - model_available: Whether a model is available for embedding generation
        """
        stats = {
            "buffer_length": len(self.buffer),
            "buffer_capacity": self.buffer_size,
            "context_window_size": self.max_size,
            "has_vector_search": self.has_vector_search,
            "model_available": self.model is not None,
        }

        if self.has_vector_search:
            stats["vector_index_size"] = self.index_count

        return stats

    def __len__(self) -> int:
        """Return the current length of the buffer."""
        return len(self.buffer)


@multitasking.task
def fifo_cleanup_task(buffer_memory: "WorkingMemory") -> None:
    """
    Background task for periodic FIFO memory cleanup.

    This function runs continuously in a daemon thread to periodically
    call the check_memory_usage_and_cleanup method on the buffer.

    Args:
        buffer_memory: The WorkingMemory instance to clean up
    """
    import time

    #     f"Starting FIFO cleanup task with {buffer_memory.fifo_interval_min} minute interval"
    # )

    while True:
        try:
            # Perform cleanup first (free cleanup on startup!)
            buffer_memory.check_memory_usage_and_cleanup()

            # Then wait for the configured interval (convert minutes to seconds)
            time.sleep(buffer_memory.fifo_interval_min * 60)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "buffer_memory_cleanup",
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                description="Failed to run buffer memory cleanup task",
            )
            time.sleep(60)  # Wait a minute before retrying
