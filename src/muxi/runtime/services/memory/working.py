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
#   buffer = WorkingMemory(
#       max_size=10,                # Context window size
#       buffer_multiplier=10,       # Total capacity = 10 x 10 = 100
#       embedding_model="openai/text-embedding-3-small",
#   )
#
#   # Create buffer memory with remote FAISS/FAISSx server
#   buffer = WorkingMemory(
#       max_size=10,
#       buffer_multiplier=10,
#       embedding_model="openai/text-embedding-3-small",
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

import asyncio
import collections
import threading
import time
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from faissx import client as faiss

from .. import observability
from .embedding import DEFAULT_EMBEDDING_MODEL, embed, probe_dimension
from .scopes import resolve_read_group_ids

# Structured partition-key scheme (memory namespaces). Vector partitions
# are keyed by scope:
#
#   "session:{id}"  transient per-session retrieval plumbing (from #200)
#   "user:{id}"     cross-session items owned by one user
#   "group:{id}"    group-shared items ("buffer" items carrying a
#                   group_id and no session_id)
#   "formation"     formation-global items (sops, knowledge, docs, and
#                   buffer items carrying neither session nor user)
#
# The item-kind tag (namespace: buffer / sops / knowledge / doc) stays
# orthogonal, exactly as before. Search fan-out (Phases 2+3,
# read-up-the-chain): a session-scoped search reads its session partition
# PLUS the requester's identity chain — the user's cross-session
# partition, each group partition the requester belongs to (per-request
# GBAC permissions), and the formation partition (restricted to "buffer"
# items so sops/knowledge/docs stay out of chat recall — #200's dilution
# fix holds). Namespaced (sops/knowledge) searches read the formation
# partition; unscoped searches merge all partitions, with group
# partitions gated by the requester's memberships.
SESSION_PARTITION_PREFIX = "session:"
USER_PARTITION_PREFIX = "user:"
GROUP_PARTITION_PREFIX = "group:"
FORMATION_PARTITION = "formation"


class _IndexPartition:
    """FAISS index state for a single working-memory partition.

    Each partition owns its own ``IndexFlatL2`` plus the forward and
    reverse mappings between global buffer indices and rows in that
    index. Partitioning vectors per session keeps session-scoped
    searches from scanning — and being crowded out of top-k by —
    vectors that belong to other sessions.
    """

    def __init__(self, dimension: int):
        self.index = faiss.IndexFlatL2(dimension)
        self.index_mapping = {}  # Maps buffer indices to FAISS rows
        self.reverse_index_mapping = {}  # Maps FAISS rows back to buffer indices
        self.index_count = 0  # Number of vectors in this partition


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

    When no embedding model is configured, automatically falls back to
    ``local/nomic-ai/nomic-embed-text-v1.5`` (768 dimensions, Apache-2.0).
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
        dimension: int = 768,
        mode: str = "local",
        remote: Optional[Dict[str, Any]] = None,
        max_memory_mb: int = 1000,
        fifo_interval_min: int = 5,
        api_key: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        """
        Initialize working memory with vector search capabilities.

        The embedding dimension is **probed lazily** on the first embed
        operation via
        :func:`services.memory.embedding.probe_dimension`; construction
        does NOT invoke OneLLM. ``dimension`` is retained as a
        provisional hint used to size the initial FAISS index — it is
        replaced on first ``_ensure_dim()`` call once the real dim is
        known.

        Args:
            formation_id: The formation ID for scoping data.
            max_size: The context window size - number of recent messages to include
                when retrieving by recency. Default is 10.
            buffer_multiplier: Multiplier to determine total buffer capacity.
                Total capacity = max_size × buffer_multiplier. Default is 10.
            dimension: Provisional FAISS index dimension hint. Replaced on
                first ``_ensure_dim()`` once the real dim is probed from
                the embedding provider. Default is 768 (Nomic v1.5).
            embedding_model: Provider-prefixed embedding model slug
                (e.g. ``"local/nomic-ai/nomic-embed-text-v1.5"``,
                ``"openai/text-embedding-3-small"``). When ``None``,
                defaults to
                :data:`~services.memory.embedding.DEFAULT_EMBEDDING_MODEL`.
            mode: FAISS mode - "local" for in-memory storage or "remote" for
                server-based storage. Default is "local".
            remote: Remote server configuration when mode is "remote". Should contain:
                - url: FAISS/FAISSx server URL (e.g., "tcp://localhost:45678")
                - api_key: Optional API key for authentication
                - tenant: Optional tenant ID for multi-tenancy
            max_memory_mb: Maximum memory usage in MB for FIFO cleanup. Default is 1000.
            fifo_interval_min: Minimum interval in minutes for FIFO cleanup. Default is 5.
            api_key: Retained for backwards compatibility with legacy
                callers that passed it alongside ``model``. The helper
                delegates authentication to OneLLM's own provider config
                — this kwarg is no longer consulted here.
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

        # ``api_key`` is preserved on the instance for backwards
        # compatibility with callers that reference it. The new embed
        # path routes through OneLLM which owns provider auth.
        self._model_api_key = api_key

        # Resolve the embedding model slug. The old dispatch that
        # accepted an LLM instance (or a local/API branch) is gone --
        # every caller passes a slug string, and embedding generation
        # flows through the shared :func:`embed` helper.
        if embedding_model is None:
            embedding_model = DEFAULT_EMBEDDING_MODEL
        if not isinstance(embedding_model, str):
            raise TypeError(
                "WorkingMemory(embedding_model=...) must be a "
                f"provider-prefixed slug string, got {type(embedding_model).__name__}"
            )
        self._embedding_model_name: str = embedding_model

        # Lazy-dim: populated on first ``_ensure_dim()`` call, never in
        # ctor. ``self.dimension`` keeps a provisional FAISS index dim so
        # the index can be constructed before the real dim is known; it
        # is replaced under the lock once ``probe_dimension`` resolves.
        self._dimension: Optional[int] = None
        self._dim_lock = asyncio.Lock()
        self.dimension = dimension

        # Configure FAISS for remote mode (FAISSx-specific)
        if mode == "remote" and self.remote:
            faiss.configure(
                server=self.remote.get("url"),
                api_key=self.remote.get("api_key"),
                tenant_id=self.remote.get("tenant"),
            )
        elif mode != "local" and mode != "remote":
            raise ValueError(f"Invalid mode: {mode}. Must be 'local' or 'remote'")

        # Initialize vector storage. Vectors are partitioned by scope
        # key: each "buffer"-namespace item carrying a session_id goes
        # to a per-session FAISS index; buffer items with only a
        # user_id go to that user's cross-session index; everything
        # else (sops, knowledge, docs, buffer items with neither)
        # shares the ``FORMATION_PARTITION`` index. Partitions are created lazily on
        # first write with the provisional dim and reset the first time
        # ``_ensure_dim`` resolves a different real dim; this is safe
        # because no vectors have been added yet.
        self.partitions: Dict[str, _IndexPartition] = {}
        self.needs_rebuild = False  # Flag to track if index needs rebuilding

        # Key-value store for exact lookups with TTL
        self.kv_store = {}
        self.kv_expiry = {}

        # Start the background FIFO cleanup task
        fifo_cleanup_task(self)

    async def _ensure_dim(self) -> int:
        """Probe the embedding dimension exactly once and memoize it.

        On first invocation this calls
        :func:`services.memory.embedding.probe_dimension` for the
        configured model slug, stores the result on ``self._dimension``,
        and — if the probed dim differs from the provisional hint used
        to build any early FAISS partitions — resets ``self.partitions``
        so they are recreated at the correct dimensionality. Resetting
        is safe here because ``_ensure_dim`` is always invoked before
        the first embed operation, so the partitions are guaranteed to
        be empty.

        Concurrent callers are serialized by ``self._dim_lock`` so only
        a single underlying ``probe_dimension`` call is issued even
        when multiple coroutines hit this method simultaneously on a
        fresh instance.
        """
        if self._dimension is not None:
            return self._dimension

        async with self._dim_lock:
            # Re-check under the lock — another coroutine may have
            # probed while we were queued on ``acquire``.
            if self._dimension is not None:
                return self._dimension

            probed = await probe_dimension(self._embedding_model_name)
            if probed != self.dimension:
                self.dimension = probed
                # Safe reset: no embedded items exist yet before the
                # first ``_ensure_dim`` call.
                self.partitions = {}
                self.needs_rebuild = False
            self._dimension = probed
            return probed

    def _partition_key(self, namespace: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Derive the structured scope partition key for an item.

        "buffer"-namespace items carrying a session_id are partitioned
        per session (``session:{id}``); sessionless buffer items carrying
        a group_id are group-shared (``group:{id}`` -- explicitly
        addressed to the group, so group outranks user when both are
        present); buffer items carrying only a user_id land in the user's
        cross-session partition (``user:{id}``); everything else (sops,
        knowledge, docs, and buffer items with none of these) is
        formation-global (``formation``).
        """
        if namespace == "buffer":
            md = metadata or {}
            session_id = md.get("session_id")
            if session_id:
                return f"{SESSION_PARTITION_PREFIX}{session_id}"
            group_id = md.get("group_id")
            if group_id:
                return f"{GROUP_PARTITION_PREFIX}{group_id}"
            user_id = md.get("user_id")
            if user_id:
                return f"{USER_PARTITION_PREFIX}{user_id}"
        return FORMATION_PARTITION

    def _fanout_partition_keys(
        self,
        requester_user_id: Optional[str] = None,
        group_ids: Sequence[str] = (),
    ) -> List[str]:
        """The identity-chain partitions a user-context search reads.

        Write-one-read-up (memory namespaces): the requester's own
        cross-session partition, one partition per group the requester
        belongs to, and the formation partition. ``group_ids`` is
        resolved by the caller through the same shared helper the
        long-term backends use (``scopes.resolve_read_group_ids``), so
        working memory and long-term memory can never disagree about a
        user's group set. Ordering is most-specific-first for
        readability; the merge is score-based.
        """
        keys: List[str] = []
        if requester_user_id:
            keys.append(f"{USER_PARTITION_PREFIX}{requester_user_id}")
        for group_id in group_ids:
            keys.append(f"{GROUP_PARTITION_PREFIX}{group_id}")
        keys.append(FORMATION_PARTITION)
        return keys

    def _get_partition(self, key: str, dimension: Optional[int] = None) -> _IndexPartition:
        """Return the partition for ``key``, creating it lazily.

        ``dimension`` overrides the memory-wide dim for the new partition.
        Pre-computed embeddings (``add_with_embedding``, e.g. knowledge
        chunks embedded with the formation's document model) may carry a
        different dimensionality than this memory's own embedding model;
        their partition must be created at the vectors' actual dim or
        every ``index.add`` fails with a shape mismatch.
        """
        partition = self.partitions.get(key)
        if partition is None:
            # Explicit None check (not truthiness): an explicit dimension
            # must always win; only an absent override falls back to the
            # memory-wide dim.
            partition = _IndexPartition(dimension if dimension is not None else self.dimension)
            self.partitions[key] = partition
        return partition

    @property
    def index_count(self) -> int:
        """Total number of vectors across all partitions."""
        return sum(partition.index_count for partition in self.partitions.values())

    @property
    def embedding_model_name(self) -> str:
        """Public accessor for the configured embedding model slug.

        Exposes the provider-prefixed slug string (e.g.
        ``"local/nomic-ai/nomic-embed-text-v1.5"``,
        ``"openai/text-embedding-3-small"``) used by this memory
        instance for embedding generation. External consumers
        (``sops.py``, ``persistent_manager.py``, etc.) should read this
        public property instead of reaching into the private
        ``_embedding_model_name`` attribute.
        """
        return self._embedding_model_name

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

        # Generate embedding if a model slug is configured and text is
        # not empty. Write paths use ``task="search_document"`` — the
        # Nomic-style prefix marks the input as a corpus document. The
        # helper strips the kwarg for cloud providers that don't honor
        # it, so this call site is provider-agnostic.
        if self._embedding_model_name and text and text.strip():
            try:
                await self._ensure_dim()
                vectors = await embed(
                    self._embedding_model_name,
                    text,
                    task="search_document",
                )
                embedding_vector = vectors[0]

                item["embedding"] = embedding_vector

                # Route the vector to its partition (per-session for
                # buffer items, shared otherwise) and record the
                # buffer-index-to-FAISS-row mapping.
                partition = self._get_partition(self._partition_key(namespace, metadata))
                buffer_idx = len(self.buffer)
                partition.index_mapping[buffer_idx] = partition.index_count
                partition.reverse_index_mapping[partition.index_count] = buffer_idx

                # Normalize embedding for better cosine similarity in FAISS
                embedding_array = np.array([embedding_vector], dtype=np.float32)
                norm = np.linalg.norm(embedding_array[0])
                if norm > 0:
                    embedding_array = embedding_array / norm

                # Add the normalized embedding to the partition's index
                partition.index.add(embedding_array)

                # Increment the partition's FAISS row counter
                partition.index_count += 1
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
        if len(self.buffer) == self.buffer_size and self._embedding_model_name:
            self.needs_rebuild = True

    def _rebuild_index(self) -> None:
        """
        Rebuild the FAISS partitions after buffer overflow.

        This internal method rebuilds every partition's FAISS index and mappings
        when the buffer is full and new items have displaced old ones. It ensures
        the vector search stays in sync with the actual buffer contents. Partitions
        that end up with no vectors (e.g. every item of a dead session was evicted)
        are dropped entirely.
        """
        if not self._embedding_model_name:
            return

        # Regroup embeddings from the current buffer into new partitions
        new_partitions: Dict[str, _IndexPartition] = {}
        embeddings_by_key: Dict[str, list] = {}

        for i, item in enumerate(self.buffer):
            if "embedding" in item and item["embedding"] is not None:
                embedding = item["embedding"]
                dim = len(embedding)
                key = self._partition_key(item.get("namespace", "buffer"), item.get("metadata"))
                partition = new_partitions.get(key)
                if partition is None:
                    # Partition dim follows the vectors it stores, NOT the
                    # memory-wide dim: pre-computed embeddings (knowledge
                    # chunks via add_with_embedding) may differ from this
                    # memory's own embedding model. Rebuilding them at
                    # self.dimension used to shape-crash the whole rebuild
                    # (and with it every subsequent vector search).
                    partition = _IndexPartition(dim)
                    new_partitions[key] = partition
                    embeddings_by_key[key] = []
                if dim != partition.index.d:
                    # Defensive: never mix dims within one partition; the
                    # mismatched item stays in the buffer (recency reach)
                    # but out of this partition's index.
                    continue
                embeddings_by_key[key].append(embedding)
                partition.index_mapping[i] = partition.index_count
                partition.reverse_index_mapping[partition.index_count] = i
                partition.index_count += 1

        # Add collected embeddings to each partition's index
        for key, embeddings in embeddings_by_key.items():
            embeddings_array = np.array(embeddings, dtype=np.float32)
            new_partitions[key].index.add(embeddings_array)

        # Replace the old partitions
        self.partitions = new_partitions
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
                if self._embedding_model_name:
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
            recent_items = list(self.buffer)[-self.max_size :]

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

        # Fast path: empty query means recency-only search -- skip embedding model
        # initialization entirely to avoid lazy-loading overhead on first call.
        if not query and query_vector is None:
            recency_results = self._recency_search(
                limit,
                filter_metadata,
                use_entire_buffer=True,
                namespace=namespace,
                session_id=session_id,
            )
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_RETRIEVED,
                level=observability.EventLevel.DEBUG,
                data={
                    "results_count": len(recency_results),
                    "search_type": "recency_fast_path",
                    "buffer_size": len(self.buffer),
                },
                description="Working memory empty-query fast path",
            )
            return recency_results

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
                "has_vector_search": self._embedding_model_name is not None,
            },
            description="Working memory search started",
        )

        # If we don't have a model, return most recent messages
        if not self._embedding_model_name:
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

        # Generate a query vector if not provided. Search paths use
        # ``task="search_query"`` — the Nomic-style prefix marks the
        # input as a retrieval query; the helper strips the kwarg for
        # cloud providers that don't honor it.
        if query_vector is None:
            try:
                await self._ensure_dim()
                vectors = await embed(
                    self._embedding_model_name,
                    query,
                    task="search_query",
                )
                query_vector = vectors[0]

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
                    description=("Working memory search completed " "(embedding failure fallback)"),
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

            # Select which partitions to search (memory namespaces
            # Phases 2+3, read-up-the-chain):
            #
            # * A session-scoped search reads its session partition PLUS
            #   the requester's identity chain -- user partition (from the
            #   user_id filter), each group partition the requester
            #   belongs to (per-request GBAC permissions), and the
            #   formation partition. Fan-out items are merged by score;
            #   the per-item filters below restrict fan-out partitions to
            #   "buffer" items so sops/knowledge/docs stay out of chat
            #   recall (#200's dilution fix holds).
            # * Namespaced searches without a session (sops / knowledge)
            #   only need the formation partition, where all non-"buffer"
            #   vectors live (unchanged).
            # * Unscoped searches merge all partitions, with group
            #   partitions gated by the requester's memberships.
            requester_user_id = (filter_metadata or {}).get("user_id")
            fanout_keys: set = set()
            if session_id:
                # Same membership resolution as the long-term backends:
                # the per-request permissions ContextVar set by the
                # request pipeline, or no group scopes.
                group_ids = await resolve_read_group_ids()
                partition_keys = [f"{SESSION_PARTITION_PREFIX}{session_id}"]
                fanout_keys = set(self._fanout_partition_keys(requester_user_id, group_ids))
                partition_keys.extend(key for key in fanout_keys if key in self.partitions)
            elif namespace and namespace != "buffer":
                partition_keys = [FORMATION_PARTITION]
            else:
                group_ids = await resolve_read_group_ids()
                allowed_groups = {f"{GROUP_PARTITION_PREFIX}{group_id}" for group_id in group_ids}
                partition_keys = [
                    key
                    for key in self.partitions
                    if not key.startswith(GROUP_PARTITION_PREFIX) or key in allowed_groups
                ]

            results = []
            for partition_key in partition_keys:
                partition = self.partitions.get(partition_key)
                if partition is None or partition.index_count == 0:
                    continue

                # Search the partition's FAISS index for similar vectors
                k = min(limit * 2, partition.index_count)  # Extra results allow for filtering
                distances, indices = partition.index.search(query_np, k)

                # Map FAISS rows back to buffer indices via the reverse
                # mapping (O(1) per result). FAISS pads with -1 when fewer
                # than k vectors exist; those have no mapping and are skipped.
                candidates = []
                for i, faiss_idx in enumerate(indices[0]):
                    buffer_idx = partition.reverse_index_mapping.get(int(faiss_idx))
                    if buffer_idx is not None:
                        candidates.append((buffer_idx, float(distances[0][i])))

                # Combine semantic score with recency score
                partition_results = []
                is_fanout_partition = partition_key in fanout_keys
                for buffer_idx, distance in candidates:
                    # Make sure buffer_idx is in range
                    if buffer_idx >= len(self.buffer):
                        continue

                    item = self.buffer[buffer_idx].copy()

                    # Apply namespace filter if provided
                    if namespace and item.get("namespace") != namespace:
                        continue

                    # Fan-out partitions contribute "buffer" items only:
                    # keeps the formation partition's sops/knowledge/docs
                    # out of session-scoped chat recall (#200's dilution
                    # fix must hold under the identity-chain fan-out).
                    if is_fanout_partition and item.get("namespace", "buffer") != "buffer":
                        continue

                    # Check formation_id match (always filter by formation)
                    if item.get("metadata", {}).get("formation_id") != self.formation_id:
                        continue

                    # Apply session_id filter as a hard filter if provided.
                    # Identity-chain (fan-out) items carry no session_id by
                    # construction; the session filter applies only to the
                    # session partition itself.
                    if (
                        session_id
                        and not is_fanout_partition
                        and item.get("metadata", {}).get("session_id") != session_id
                    ):
                        continue

                    # Apply metadata filters if provided. Fan-out items are
                    # exempt from the identity keys they cannot carry:
                    # session_id for the whole chain, and user_id for the
                    # shared (group / formation) partitions -- visibility
                    # for those is membership-based, enforced by the
                    # partition selection above, not by per-item metadata.
                    effective_filter = filter_metadata
                    if is_fanout_partition and filter_metadata:
                        exempt_keys = {"session_id"}
                        if partition_key == FORMATION_PARTITION or partition_key.startswith(
                            GROUP_PARTITION_PREFIX
                        ):
                            exempt_keys.add("user_id")
                        effective_filter = {
                            key: value
                            for key, value in filter_metadata.items()
                            if key not in exempt_keys
                        }
                    if effective_filter and not all(
                        key in item["metadata"] and item["metadata"][key] == value
                        for key, value in effective_filter.items()
                    ):
                        continue

                    # Calculate combined score without session weighting
                    # (session_id is now a hard filter applied above)
                    if namespace == "sops":
                        # SOPs are indexed once at startup; their position in the
                        # buffer is meaningless and the ``1 / (1 + L2²)`` transform
                        # used below compresses the high-similarity range that
                        # SOP-routing decisions live in. Return *true* cosine
                        # similarity instead so the threshold callers compare
                        # against (typically 0.7) means what operators expect.
                        #
                        # Vectors are unit-normalised (see the query
                        # normalization above), so for the FAISS
                        # ``IndexFlatL2`` distance ``d``:
                        #   d == ||a - b||² == 2 - 2·cos(a, b)
                        #   cos == 1 - d / 2
                        cos_sim = 1.0 - distance / 2.0
                        # Clamp into [0, 1] — numerical noise on ``d ≈ 0`` or
                        # ``d ≈ 2`` can drift fractionally outside the range.
                        combined_score = max(0.0, min(1.0, cos_sim))
                    else:
                        semantic_score = 1.0 / (1.0 + distance)
                        recency_score = 1.0 - (buffer_idx / len(self.buffer))

                        # Use original recency bias formula
                        # This preserves perfect scores for exact matches
                        combined_score = (
                            1 - recency_bias
                        ) * semantic_score + recency_bias * recency_score

                    # Add score to the item
                    item["score"] = combined_score
                    partition_results.append(item)

                    # Stop if we have enough results from this partition
                    if len(partition_results) >= limit:
                        break

                results.extend(partition_results)

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
            # Resolve the real embedding dim before the first FAISS
            # write. Without this, a WorkingMemory built with a
            # provisional hint (e.g. default 768) and a model whose
            # true dim differs (e.g. 1536 for text-embedding-3-small)
            # raises a shape mismatch on the partition's index.add(),
            # which the broad except below silently swallows — the
            # item lands in self.buffer but never in FAISS. A later
            # add() or search() triggers _ensure_dim and resets the
            # partitions at the correct dim, but these early items are
            # not re-indexed and their vector recall is permanently
            # degraded. Calling _ensure_dim first makes the
            # "safe reset: no embedded items exist yet" invariant
            # in _ensure_dim actually hold regardless of which
            # writer (add vs add_with_embedding) wins the race to
            # the first insert.
            await self._ensure_dim()
            try:
                if isinstance(embedding, list):
                    embedding_np = np.array([embedding], dtype=np.float32)
                else:
                    embedding_np = embedding.reshape(1, -1)

                # Normalize embedding for better cosine similarity in FAISS
                norm = np.linalg.norm(embedding_np[0])
                if norm > 0:
                    embedding_np = embedding_np / norm

                # Route the vector to its partition (per-session for
                # buffer items, shared otherwise) and update the mapping.
                # The partition is created at THIS embedding's dim: pre-
                # computed vectors routinely differ from the buffer's own
                # embedding model dim (e.g. 1536-dim knowledge chunks in
                # a 768-dim buffer memory).
                partition = self._get_partition(
                    self._partition_key(namespace, metadata),
                    dimension=int(embedding_np.shape[1]),
                )
                partition.index.add(embedding_np)

                buffer_idx = len(self.buffer) - 1
                partition.index_mapping[buffer_idx] = partition.index_count
                partition.reverse_index_mapping[partition.index_count] = buffer_idx
                partition.index_count += 1

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

        This method removes all items from the buffer and resets all FAISS
        partitions if vector search is enabled. It effectively resets the memory
        to an empty state.
        """
        # Clear the buffer
        self.buffer.clear()

        # Reset all FAISS partitions
        self.partitions = {}
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
        messages_to_load = (
            sorted_messages[-available_space:]
            if len(sorted_messages) > available_space
            else sorted_messages
        )
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
        if self._embedding_model_name and messages_to_load:
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
            "model_available": self._embedding_model_name is not None,
        }

        if self.has_vector_search:
            stats["vector_index_size"] = self.index_count

        return stats

    def __len__(self) -> int:
        """Return the current length of the buffer."""
        return len(self.buffer)


def fifo_cleanup_task(buffer_memory: "WorkingMemory") -> None:
    """
    Start the periodic FIFO memory cleanup for a buffer instance.

    Runs on a dedicated daemon thread rather than the shared
    multitasking pool: the pool is capped at cpu_count() concurrent
    slots and this loop never terminates, so running it there
    permanently consumed a slot per WorkingMemory instance and starved
    the observability emitters that share the pool.

    Args:
        buffer_memory: The WorkingMemory instance to clean up
    """

    def _cleanup_loop() -> None:
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

    # daemon=True so the never-ending loop cannot block interpreter
    # exit (unit tests, CLI scripts, graceful-shutdown paths). The
    # instance id in the name keeps thread dumps attributable when
    # several WorkingMemory instances are alive in one process.
    threading.Thread(
        target=_cleanup_loop,
        name=f"muxi-buffer-fifo-cleanup-{id(buffer_memory):x}",
        daemon=True,
    ).start()
