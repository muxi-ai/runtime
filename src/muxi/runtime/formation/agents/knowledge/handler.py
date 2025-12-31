# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Handler - External Knowledge Management
# Description:  Core system for managing and accessing agent knowledge sources
# Role:         Provides vector storage and retrieval of knowledge for agents
# Usage:        Used to augment agent responses with external information
# Author:       Muxi Framework Team
#
# The Knowledge Handler provides a comprehensive system for managing and accessing
# external knowledge sources for agents. It combines:
#
# 1. Vector Storage
#    - Efficient storage of document embeddings
#    - FAISSx index for fast similarity search
#    - Persistence through WorkingMemory
#
# 2. Document Management
#    - Loading and chunking of documents via DocumentChunkManager
#    - Tracking of document metadata and sources
#    - MD5-based content change detection for intelligent reindexing
#
# 3. Search Capabilities
#    - Semantic search using vector similarity
#    - Configurable relevance threshold
#    - Metadata filtering options
#    - Performance optimization with query caching
#
# 4. Performance Optimization
#    - Query result caching for frequently accessed knowledge
#    - Performance monitoring and metrics collection
#    - Optimized vector search parameters for agent use cases
#    - Batch processing for improved throughput
#
# 5. Memory Integration
#    - Automatic injection of knowledge into working memory
#    - Unified search across knowledge and memory
#    - Context-aware knowledge retrieval
#
# The KnowledgeHandler is typically used to:
# - Process documents and file-based knowledge
# - Generate and store vector embeddings
# - Provide agents with relevant information based on queries
# - Ground agent responses in factual information
# - Enhance agent memory with relevant knowledge
#
# This implementation uses the hybrid architecture with DocumentChunkManager
# and WorkingMemory for unified document processing and search.
#
# Supports both local and remote FAISSx modes:
# - Local mode: Uses local FAISSx client with file-based persistence
# - Remote mode: Connects to remote FAISSx server for distributed storage
#
# Example usage:
#
#   # Initialize with an agent ID (local mode)
#   handler = KnowledgeHandler(
#       agent_id="support_agent",
#       embedding_dimension=1536
#   )
#
#   # Initialize with remote FAISSx server and memory integration
#   handler = KnowledgeHandler(
#       agent_id="support_agent",
#       embedding_dimension=1536,
#       mode="remote",
#       remote={
#           "url": "tcp://localhost:45678",
#           "api_key": "your_api_key",
#           "tenant": "your_tenant"
#       },
#       working_memory=memory_instance,
#       auto_inject_knowledge=True
#   )
#
#   # Add documents to knowledge base
#   knowledge_source = FileKnowledge(
#       "product_docs",
#       "docs/product_manual.pdf",
#       "Product documentation"
#   )
#   await handler.add_file(knowledge_source, model.get_embedding)
#
#   # Search for relevant information (auto-injects into memory if enabled)
#   results = await handler.search(
#       query="How do I reset my password?",
#       generate_embedding_fn=model.get_embedding,
#       top_k=3
#   )
#
#   # Unified search across knowledge and memory
#   unified_results = await handler.search_unified(
#       query="Previous discussions about password reset",
#       generate_embedding_fn=model.get_embedding,
#       include_memory=True,
#       memory_weight=0.3
#   )
# =============================================================================

import os
import hashlib
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Union

import pickle

import numpy as np

# Hybrid architecture imports
from ...documents.storage.chunk_manager import DocumentChunkManager

from .base import FileKnowledge
from ....services import observability
from ....utils.user_dirs import get_knowledge_dir

# Working memory integration
from ....services.memory.working import WorkingMemory

# Document-specific namespace constants
DOCUMENT_NAMESPACE = "knowledge"  # Changed from "documents" for clarity
KNOWLEDGE_BUFFER_NAMESPACE = "knowledge_buffer"  # For injected knowledge into memory


class KnowledgeHandler:
    """
    Handles multiple knowledge sources and provides unified search functionality.

    The KnowledgeHandler manages a collection of knowledge sources and provides
    a unified interface for searching across all of them. It uses the hybrid
    architecture with DocumentChunkManager and WorkingMemory for
    document processing and FAISSx for vector-based similarity search.
    """

    def __init__(
        self,
        agent_id_or_sources: Union[str, List],
        formation_id: str = "default-formation",
        embedding_dimension: int = 1536,
        cache_dir: str = get_knowledge_dir(),
        mode: str = "local",
        remote: Optional[Dict[str, Any]] = None,
        max_files_per_source: int = 10,
        max_total_files: int = 50,
        formation_config: Optional[Dict[str, Any]] = None,
        # Working memory integration
        working_memory: Optional[WorkingMemory] = None,
        auto_inject_knowledge: bool = True,
    ):
        """
        Initialize the knowledge handler with hybrid architecture components and memory integration.
        """
        self.agent_id_or_sources = agent_id_or_sources
        self.formation_id = formation_id
        self.embedding_dimension = embedding_dimension
        self.cache_dir = cache_dir
        self.mode = mode
        self.remote = remote or {}
        self.max_files_per_source = max_files_per_source
        self.max_total_files = max_total_files
        self.formation_config = formation_config

        # Working memory integration
        self.working_memory = working_memory
        self.auto_inject_knowledge = auto_inject_knowledge
        self._knowledge_buffer_enabled = working_memory is not None and auto_inject_knowledge

        # Store embedding function for later use
        self._generate_embeddings_fn = None

        # Create cache directory if it doesn't exist
        os.makedirs(cache_dir, exist_ok=True)

        # Initialize document processing components with formation config
        self._init_document_components(formation_config)

        # Initialize knowledge sources
        if isinstance(agent_id_or_sources, list):
            self.sources = agent_id_or_sources
        else:
            self.sources = []

        # Log initialization
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description=(
                "KnowledgeHandler initialized with hybrid architecture and memory integration"
            ),
            data={
                "agent_id_or_sources": str(agent_id_or_sources),
                "embedding_dimension": embedding_dimension,
                "mode": mode,
                "cache_dir": cache_dir,
                "max_files_per_source": max_files_per_source,
                "max_total_files": max_total_files,
                "hybrid_components": True,
                "memory_integration": self._knowledge_buffer_enabled,
                "auto_inject_knowledge": auto_inject_knowledge,
            },
        )

    def _init_document_components(self, formation_config: Optional[Dict[str, Any]] = None):
        """Initialize document processing components using formation configuration."""
        # Import DocumentProcessingConfig for proper configuration
        from ...config.document_processing import DocumentProcessingConfig

        # Create proper DocumentProcessingConfig from formation config
        if formation_config:
            llm_config = formation_config.get("llm", {})
            document_config = DocumentProcessingConfig(llm_config)
        else:
            # Use default configuration if no formation config
            document_config = DocumentProcessingConfig({})

        # Keep DocumentChunkManager - it's essential!
        self.chunk_manager = DocumentChunkManager(document_config=document_config)

        # Now using WorkingMemory directly instead of DocumentSemanticIndex
        # Documents will use WorkingMemory with "documents" namespace

        # Ensure we have WorkingMemory for document storage
        if not self.working_memory:
            self.working_memory = WorkingMemory(
                formation_id=self.formation_id,
                max_size=2000,  # Large context window for documents
                buffer_multiplier=20,  # 40,000 total capacity for documents
                dimension=self.embedding_dimension,
                model=None,  # We provide embeddings directly via add_with_embedding
                mode=self.mode,
                remote=self.remote,
                max_memory_mb=5000,  # 5GB limit for document storage
                fifo_interval_min=30,  # Less frequent cleanup for documents
            )

    async def add_knowledge_source(self, source, generate_embeddings_fn: Optional[Callable] = None):
        """Add a knowledge source and process its content using hybrid architecture."""
        # Log knowledge source addition start
        observability.observe(
            event_type=observability.ConversationEvents.CONTENT_PROCESSED,
            level=observability.EventLevel.INFO,
            description="Starting knowledge source addition with hybrid architecture",
            data={
                "source_path": getattr(source, "path", str(source)),
                "source_type": type(source).__name__,
                "current_sources_count": len(self.sources),
                "has_embedding_function": generate_embeddings_fn is not None,
            },
        )

        if len(self.sources) >= 10:  # Limit total sources
            observability.observe(
                event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                level=observability.EventLevel.WARNING,
                description="Source limit reached, skipping additional source",
                data={"current_sources": len(self.sources), "max_sources": 10}
            )

            # Log source limit reached
            observability.observe(
                event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                level=observability.EventLevel.WARNING,
                description="Knowledge source limit reached",
                data={
                    "current_sources_count": len(self.sources),
                    "max_sources": 10,
                    "skipped_source": getattr(source, "path", str(source)),
                },
            )
            return

        # Only support FileKnowledge sources with hybrid architecture
        if not isinstance(source, FileKnowledge):
            # Log unsupported source type
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.ERROR,
                description="Unsupported knowledge source type",
                data={
                    "source_type": type(source).__name__,
                    "supported_types": ["FileKnowledge"],
                },
            )
            return

        self.sources.append(source)

        if generate_embeddings_fn is None:
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.WARNING,
                description="No embedding function provided, content processing skipped",
                data={"source_path": getattr(source, "path", str(source))}
            )

            # Log no embedding function
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.DEBUG,
                description="No embedding function provided for knowledge source",
                data={
                    "source_path": getattr(source, "path", str(source)),
                    "sources_count": len(self.sources),
                },
            )
            return

        try:
            source_path = getattr(source, "path", str(source))
            # Ensure absolute path for consistency
            source_path = os.path.abspath(source_path)

            # Step 1: Calculate hash for the source
            source_hash = self._calculate_file_md5(source_path)

            # Step 2: Check disk cache
            cached_data = self._load_cached_embeddings(source_path, source_hash)

            if cached_data:
                # Cache hit! Load embeddings from disk into WorkingMemory
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.DEBUG,
                    description="Loading embeddings from cache",
                    data={"source_name": source.name, "source_hash": source_hash[:8]}
                )
                chunks_added = 0

                for cached_item in cached_data:
                    try:
                        await self.working_memory.add_with_embedding(
                            text=cached_item["content"],
                            embedding=cached_item["embedding"],
                            metadata=cached_item["metadata"],
                            namespace=DOCUMENT_NAMESPACE,
                        )
                        chunks_added += 1
                    except Exception as e:
                        observability.observe(
                            event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                            level=observability.EventLevel.WARNING,
                            description="Failed to add cached chunk to memory",
                            data={"error": str(e), "error_type": type(e).__name__}
                        )
                        continue

                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.INFO,
                    description="Successfully loaded embeddings from cache",
                    data={"source_name": source.name, "chunks_loaded": chunks_added, "from_cache": True}
                )

            else:
                # Cache miss - need to generate embeddings
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.DEBUG,
                    description="Cache miss - generating new embeddings",
                    data={"source_name": source.name}
                )

                # Use FileKnowledge's hybrid architecture integration
                document_chunks = await source.process_with_chunk_manager(
                    chunk_manager=self.chunk_manager, file_limit=self.max_files_per_source
                )

                # Limit total chunks processed
                if len(document_chunks) > self.max_total_files:

                    document_chunks = document_chunks[:self.max_total_files]

                # Generate embeddings for all chunks
                if document_chunks:
                    chunk_contents = [chunk.content for chunk in document_chunks]
                    embeddings = await generate_embeddings_fn(chunk_contents)

                    if not embeddings:
                        observability.observe(
                            event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                            level=observability.EventLevel.ERROR,
                            description="Failed to generate embeddings",
                            data={"source_name": source.name, "chunks_count": len(chunk_contents)}
                        )
                        return

                    # Prepare cache data while adding to WorkingMemory
                    cache_data = []
                    chunks_added = 0

                    for chunk, embedding in zip(document_chunks, embeddings):
                        try:
                            # Skip if embedding generation failed
                            if embedding is None:
                                observability.observe(
                                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                                    level=observability.EventLevel.WARNING,
                                    description="Skipping chunk due to missing embedding",
                                    data={
                                        "chunk_id": chunk.chunk_id,
                                        "source_name": source.name
                                    }
                                )
                                continue

                            metadata = {
                                "document_id": chunk.document_id,
                                "chunk_id": chunk.chunk_id,
                                "knowledge_source": source.name,
                                "description": source.description,
                                "source": source_path,  # Add source path for cache invalidation
                                "content_hash": source_hash,  # Add hash for validation
                                **chunk.metadata,
                            }

                            await self.working_memory.add_with_embedding(
                                text=chunk.content,
                                embedding=embedding,
                                metadata=metadata,
                                namespace=DOCUMENT_NAMESPACE,
                            )
                            chunks_added += 1

                            # Prepare for cache
                            cache_data.append({
                                "content": chunk.content,
                                "embedding": embedding,
                                "metadata": metadata,
                            })

                        except Exception as e:
                            observability.observe(
                                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                                level=observability.EventLevel.WARNING,
                                description="Failed to add chunk to memory",
                                data={
                                    "chunk_id": chunk.chunk_id,
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                    "traceback": traceback.format_exc()
                                }
                            )
                            continue
                    observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.INFO,
                        description="Successfully processed knowledge source",
                        data={
                            "source_name": source.name,
                            "chunks_added": chunks_added,
                            "from_cache": False
                        }
                    )

                    # Step 3: Save to disk cache
                    if cache_data:
                        self._save_cached_embeddings(source_path, source_hash, cache_data)

            # Log successful knowledge source addition
            chunks_added = locals().get("chunks_added", 0)
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.INFO,
                description="Knowledge source addition completed with hybrid architecture",
                data={
                    "source_path": getattr(source, "path", str(source)),
                    "chunks_processed": len(document_chunks) if 'document_chunks' in locals() else chunks_added,
                    "chunks_added": chunks_added,
                    "total_sources": len(self.sources),
                    "from_cache": cached_data is not None,
                },
            )

        except Exception as e:
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,
                level=observability.EventLevel.ERROR,
                description="Failed to add knowledge source",
                data={"source_path": source_path, "error": str(e), "error_type": type(e).__name__}
            )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        generate_embeddings_fn: Optional[Callable] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search across all knowledge sources with performance optimization."""
        search_start_time = time.time()

        # Log search start
        observability.observe(
            event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
            level=observability.EventLevel.INFO,
            description="Starting knowledge search with performance optimization",
            data={
                "query_length": len(query),
                "top_k": top_k,
                "has_embedding_function": generate_embeddings_fn is not None,
                "has_working_memory": self.working_memory is not None,
            },
        )

        # Use provided embedding function or stored one
        if generate_embeddings_fn is None:
            generate_embeddings_fn = self._generate_embeddings_fn

        # Require embedding function for semantic search
        if generate_embeddings_fn is None:
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                level=observability.EventLevel.WARNING,
                description="No embedding function provided for knowledge search",
                data={"query": query, "top_k": top_k},
            )
            return []

        try:
            # Generate query embedding
            # The embedding function expects a list, so wrap single query
            query_embeddings = await generate_embeddings_fn([query])
            if not query_embeddings or len(query_embeddings) == 0:
                raise ValueError("Failed to generate query embedding")
            query_embedding = query_embeddings[0]  # Get first (and only) embedding

            # Convert to numpy array if needed
            if isinstance(query_embedding, list):
                query_vector = np.array(query_embedding, dtype=np.float32)
            else:
                query_vector = query_embedding

            # Use standard search parameters
            search_k = top_k

            # Use WorkingMemory for document search with documents namespace
            memory_results = await self.working_memory.search(
                query="",  # Empty since we provide vector
                query_vector=query_vector.tolist(),
                limit=search_k * 2,  # Get more results for filtering
                recency_bias=0.05,  # Very low for documents - favor semantic similarity
                namespace=DOCUMENT_NAMESPACE,
                session_id=session_id,
            )

            # Convert to standard format
            results = []
            for item in memory_results:
                content = item["text"]
                if len(content) > 200:
                    content = content[:200] + "..."

                results.append(
                    {
                        "content": content,
                        "relevance": item.get("score", 0.0),
                        "metadata": {
                            **item["metadata"],
                            "document_id": item["metadata"].get("document_id", ""),
                            "chunk_id": item["metadata"].get("chunk_id", ""),
                        },
                    }
                )

                # Limit to requested top_k after filtering
                if len(results) >= top_k:
                    break

            # Inject knowledge results into working memory
            await self._inject_knowledge_into_memory(
                knowledge_results=results, query=query, agent_id=str(self.agent_id_or_sources)
            )

            # Calculate search time for logging
            search_time = time.time() - search_start_time

            # Log successful search
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="Knowledge semantic search completed",
                data={
                    "query": query,
                    "results_count": len(results),
                    "search_type": "semantic_search",
                    "top_k": top_k,
                    "search_time": search_time,
                },
            )

            return results

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SEARCH_FAILED,
                level=observability.EventLevel.ERROR,
                description="Knowledge search failed",
                data={"query": query[:100], "error": str(e), "error_type": type(e).__name__}
            )
            return []

    @classmethod
    async def from_agent_config(
        cls,
        agent_id: str,
        knowledge_config: Dict[str, Any],
        generate_embeddings_fn: Optional[Callable] = None,
        formation_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional["KnowledgeHandler"]:
        """Create KnowledgeHandler from agent configuration with performance optimizations."""
        # Log configuration loading start
        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Starting KnowledgeHandler creation from agent config",
            data={
                "agent_id": agent_id,
                "knowledge_enabled": knowledge_config.get("enabled", False),
                "sources_count": len(knowledge_config.get("sources", [])),
                "config_keys": list(knowledge_config.keys()),
            },
        )

        # Check if knowledge is enabled
        if not knowledge_config.get("enabled", False):
            observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.DEBUG,
                description="Knowledge disabled for agent",
                data={"agent_id": agent_id}
            )

            # Log knowledge disabled
            observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.DEBUG,
                description="Knowledge disabled for agent",
                data={"agent_id": agent_id},
            )
            return None

        sources_config = knowledge_config.get("sources", [])
        if not sources_config:
            observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.WARNING,
                description="No knowledge sources configured for agent",
                data={"agent_id": agent_id}
            )

            # Log no sources
            observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.WARNING,
                description="No knowledge sources configured for agent",
                data={"agent_id": agent_id},
            )
            return None

        observability.observe(
            event_type=observability.ConversationEvents.SESSION_CREATED,
            level=observability.EventLevel.INFO,
            description="Loading knowledge sources for agent",
            data={"agent_id": agent_id, "sources_count": len(sources_config)}
        )

        try:
            # Create handler with performance limits
            handler = cls(
                agent_id_or_sources=agent_id,
                formation_id=kwargs.get("formation_id", "default-formation"),  # Use passed formation_id
                embedding_dimension=kwargs.get("embedding_dimension", 1536),  # Match text-embedding-3-small
                cache_dir=kwargs.get("cache_dir", get_knowledge_dir()),
                mode=kwargs.get("mode", "local"),
                remote=kwargs.get("remote"),
                max_files_per_source=kwargs.get("max_files_per_source", 5),  # Very conservative
                max_total_files=kwargs.get("max_total_files", 10),  # Very conservative
                # Pass formation config for document processing
                formation_config=formation_config,
                # Working memory integration
                working_memory=kwargs.get("working_memory"),
                auto_inject_knowledge=kwargs.get("auto_inject_knowledge", True),
            )

            # Apply reasonable file size limits to prevent memory issues
            for source_config in sources_config:
                # Keep some reasonable limits per source to prevent OOM
                source_config["max_files"] = source_config.get("max_files", 100)  # Increased from 3
                max_size = source_config.get("max_file_size", 10 * 1024 * 1024)  # 10MB default
                source_config["max_file_size"] = min(max_size, 50 * 1024 * 1024)  # 50MB max

            # Store embedding function for later use
            handler._generate_embeddings_fn = generate_embeddings_fn

            # Load ALL sources with smart invalidation
            await handler.load_sources_from_config(sources_config, generate_embeddings_fn)

            source_count = len(handler.sources)
            # Get document count from WorkingMemory documents namespace
            doc_count = 0
            if handler.working_memory:
                all_docs = handler.working_memory.get_items_by_metadata(
                    metadata_filter={}, namespace=DOCUMENT_NAMESPACE
                )
                doc_count = len(all_docs)

            # Log successful handler creation
            observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.INFO,
                description="KnowledgeHandler created successfully from agent config",
                data={
                    "agent_id": agent_id,
                    "sources_count": source_count,
                    "documents_count": doc_count,
                    "embedding_dimension": kwargs.get("embedding_dimension", 128),
                },
            )

            return handler

        except Exception as e:
            # Log handler creation error
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                description="Failed to create KnowledgeHandler from agent config",
                data={"agent_id": agent_id, "error": str(e), "error_type": type(e).__name__},
            )
            raise

    async def add_file(self, knowledge_source: FileKnowledge, generate_embeddings_fn) -> int:
        """
        Add a file to the knowledge base using hybrid architecture.

        This method processes a file from a knowledge source, chunks its content using
        DocumentChunkManager, generates embeddings, and adds them to WorkingMemory
        for future retrieval.

        Args:
            knowledge_source: The knowledge source containing the file to process.
                This should be a FileKnowledge instance with path and description.
            generate_embeddings_fn: Function to generate embeddings for the text chunks.
                This should be a callable that takes a list of strings and returns
                a list of embedding vectors.

        Returns:
            int: Number of chunks added to the index. Zero indicates an error occurred.
        """
        file_path = knowledge_source.path
        description = knowledge_source.description

        # Log file addition start
        observability.observe(
            event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
            level=observability.EventLevel.INFO,
            description="Starting knowledge file addition with hybrid architecture",
            data={
                "file_path": file_path,
                "description": description,
            },
        )

        # For directories, skip MD5 calculation since we can't hash a directory
        # Individual files will have their own content hashes
        if os.path.isdir(file_path):
            file_md5 = None  # Will calculate MD5 for individual files later
        else:
            # Calculate MD5 hash for content-based caching
            file_md5 = self._calculate_file_md5(file_path)
            if not file_md5:
                # File not found or error reading file
                return 0

            # Check if document already exists in WorkingMemory with same content hash
            existing_docs = self.working_memory.get_items_by_metadata(
                metadata_filter={"source": file_path, "content_hash": file_md5},
                namespace=DOCUMENT_NAMESPACE,
            )

            if existing_docs:
                # File already processed and hasn't changed (same content hash)
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.DEBUG,
                    description="Knowledge file already processed and unchanged (same MD5 hash)",
                    data={"file_path": file_path, "content_hash": file_md5},
                )
                return 0

        # Load and process the file using hybrid architecture
        try:
            # Use the knowledge source's process method which supports markitdown
            # For directories, respect the max_files_per_source limit
            document_chunks = await knowledge_source.process_with_chunk_manager(
                chunk_manager=self.chunk_manager,
                file_limit=self.max_files_per_source  # Respect configured limit
            )

            if not document_chunks:
                observability.observe(
                    event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="No chunks generated from knowledge file",
                    data={
                        "file_path": file_path,
                        "chunks_count": 0,
                    },
                )
                return 0

            # Add content_hash to chunk metadata since process_with_chunk_manager doesn't include it
            # For directories, we'll calculate MD5 for each individual file
            if file_md5 is not None:
                for chunk in document_chunks:
                    chunk.metadata["content_hash"] = file_md5
            else:
                # For directories, calculate MD5 for each file
                for chunk in document_chunks:
                    chunk_file_path = chunk.metadata.get("file_path", "")
                    if chunk_file_path and os.path.isfile(chunk_file_path):
                        chunk_md5 = self._calculate_file_md5(chunk_file_path)
                        chunk.metadata["content_hash"] = chunk_md5

            # Generate embeddings for chunks
            chunk_contents = [chunk.content for chunk in document_chunks]
            embeddings = await generate_embeddings_fn(chunk_contents)

            if not embeddings:
                observability.observe(
                    event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to generate embeddings for file",
                    data={"file_path": file_path}
                )
                return 0

            # Add chunks and embeddings to WorkingMemory with documents namespace
            chunks_added = 0
            for chunk, embedding in zip(document_chunks, embeddings):
                # Skip if embedding generation failed
                if embedding is None:
                    observability.observe(
                        event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        description="Skipping chunk due to missing embedding",
                        data={
                            "chunk_id": chunk.chunk_id,
                            "file_path": file_path
                        }
                    )
                    continue

                metadata = {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "source": file_path,
                    "content_hash": file_md5,
                    "description": description,
                    **chunk.metadata,
                }

                await self.working_memory.add_with_embedding(
                    text=chunk.content,
                    embedding=embedding,
                    metadata=metadata,
                    namespace=DOCUMENT_NAMESPACE,
                )
                chunks_added += 1

            # Log successful file addition
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Knowledge file added successfully with hybrid architecture",
                data={
                    "file_path": file_path,
                    "chunks_added": chunks_added,
                    "embeddings_generated": len(embeddings),
                },
            )

            # Add the source to our sources list if not already there
            if knowledge_source not in self.sources:
                self.sources.append(knowledge_source)

            return chunks_added

        except Exception as e:
            # Log document processing failure
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                description="Failed to process knowledge file during addition",
                data={"file_path": file_path, "error": str(e), "error_type": type(e).__name__},
            )

            # Log file addition error
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,
                level=observability.EventLevel.ERROR,
                description="Failed to add knowledge file",
                data={"file_path": file_path, "error": str(e), "error_type": type(e).__name__},
            )
            return 0

    async def remove_file(self, file_path: str) -> bool:
        """
        Remove a file from the knowledge base using hybrid architecture.

        This method removes all chunks associated with a specific file from
        WorkingMemory.

        Args:
            file_path: Path to the file to remove from the knowledge base

        Returns:
            bool: True if the file was found and removed, False otherwise
        """
        # Log file removal start
        observability.observe(
            event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
            level=observability.EventLevel.INFO,
            description="Starting knowledge file removal with hybrid architecture",
            data={"file_path": file_path},
        )

        try:
            # Remove documents from WorkingMemory by source metadata
            removed_count = self.working_memory.remove_by_metadata(
                metadata_filter={"source": file_path}, namespace=DOCUMENT_NAMESPACE
            )

            if removed_count > 0:
                # Log successful file removal
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.INFO,
                    description="Knowledge file removed successfully with hybrid architecture",
                    data={
                        "file_path": file_path,
                        "documents_removed": removed_count,
                    },
                )

                return True
            else:
                # Log file not found for removal
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.WARNING,
                    description="Knowledge file not found for removal",
                    data={"file_path": file_path},
                )

                return False

        except Exception as e:
            # Log file removal error
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,
                level=observability.EventLevel.ERROR,
                description="Failed to remove knowledge file",
                data={"file_path": file_path, "error": str(e), "error_type": type(e).__name__},
            )
            return False

    async def get_sources(self) -> List[str]:
        """
        Get a list of all knowledge sources in the knowledge base using hybrid architecture.

        This method returns a list of unique file paths that have been added to
        the knowledge base, useful for managing and tracking knowledge sources.

        Returns:
            List[str]: List of file paths in the knowledge base
        """
        # Get unique source paths from WorkingMemory documents namespace
        all_documents = self.working_memory.get_items_by_metadata(
            metadata_filter={}, namespace=DOCUMENT_NAMESPACE  # Get all documents
        )
        sources = set()
        for doc in all_documents:
            if "source" in doc["metadata"]:
                sources.add(doc["metadata"]["source"])
        return list(sources)

    async def cleanup_deleted_sources(self, current_sources_config: List[Dict[str, Any]]) -> int:
        """
        Remove embeddings for files that no longer exist in config.

        Args:
            current_sources_config: List of current source configurations

        Returns:
            Number of sources cleaned up
        """
        if not self.working_memory:
            return 0

        # Get all currently loaded sources from memory
        loaded_sources = set()
        all_items = self.working_memory.get_items_by_metadata(
            metadata_filter={},
            namespace=DOCUMENT_NAMESPACE
        )

        for item in all_items:
            source_path = item.get("metadata", {}).get("source")
            if source_path:
                loaded_sources.add(source_path)

        # Get sources from current config
        config_sources = {
            os.path.abspath(config.get("path"))
            for config in current_sources_config
            if config.get("path")
        }

        # Find deleted sources
        deleted_sources = loaded_sources - config_sources
        cleanup_count = 0

        for deleted_source in deleted_sources:
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Removing deleted knowledge source",
                data={"source_path": deleted_source}
            )

            # 1. Remove from WorkingMemory/FAISS
            removed_count = self.working_memory.remove_by_metadata(
                metadata_filter={"source": deleted_source},
                namespace=DOCUMENT_NAMESPACE
            )

            # 2. Remove cache file
            cache_file = self._get_cache_file_path(deleted_source)
            if os.path.exists(cache_file):
                try:
                    os.remove(cache_file)
                    observability.observe(
                        event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                        level=observability.EventLevel.DEBUG,
                        description="Cache file removed",
                        data={"cache_file": os.path.basename(cache_file)}
                    )
                except Exception as e:
                    observability.observe(
                        event_type=observability.ErrorEvents.INTERNAL_ERROR,
                        level=observability.EventLevel.WARNING,
                        description="Failed to remove cache file",
                        data={"cache_file": cache_file, "error": str(e)}
                    )

            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.DEBUG,
                description="Embeddings removed from memory",
                data={"source_path": deleted_source, "embeddings_removed": removed_count}
            )
            cleanup_count += 1

            # Log cleanup
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Cleaned up deleted knowledge source",
                data={
                    "source_path": deleted_source,
                    "embeddings_removed": removed_count,
                    "cache_removed": os.path.exists(cache_file)
                },
            )

        return cleanup_count

    async def load_sources_from_config(
        self, knowledge_sources: List[Dict[str, Any]], generate_embeddings_fn
    ) -> None:
        """
        Load multiple knowledge sources from configuration with smart invalidation.

        Only regenerates embeddings for new or modified files, skips unchanged files.

        Args:
            knowledge_sources: List of source configurations
            generate_embeddings_fn: Function to generate embeddings
        """
        # First, clean up any deleted sources
        cleanup_count = await self.cleanup_deleted_sources(knowledge_sources)
        if cleanup_count > 0:
            observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Deleted sources cleanup completed",
                data={"sources_cleaned": cleanup_count}
            )

        # Process each source with smart loading
        skipped_count = 0
        processed_count = 0

        for source_config in knowledge_sources:
            try:
                source_path = source_config.get("path", "")
                if not source_path:
                    continue

                # Check if path exists (it should already be resolved by formation loader)
                if not os.path.exists(source_path):
                    # Check if this source is required (fail fast)
                    is_required = source_config.get('required', False)
                    if is_required:
                        from ...datatypes.observability import InitEventFormatter
                        print(InitEventFormatter.format_fail(
                            f"Required knowledge source not found: {source_path}",
                            f"Current directory: {os.getcwd()}"
                        ))
                        raise FileNotFoundError(f"Required knowledge source not found: {source_path}")
                    else:
                        # Optional source - log warning and continue
                        observability.observe(
                            event_type=observability.ErrorEvents.RESOURCE_NOT_FOUND,
                            level=observability.EventLevel.WARNING,
                            description="Optional knowledge source path not found - skipping",
                            data={
                                "source_path": source_path,
                                "cwd": os.getcwd()
                            }
                        )
                        continue

                # Make path absolute for consistency
                source_path = os.path.abspath(source_path)

                # Calculate current file hash
                current_hash = self._calculate_file_md5(source_path)

                # Check if file already loaded with same hash (only if memory exists)
                existing_items = []
                old_items = []

                if self.working_memory:
                    existing_items = self.working_memory.get_items_by_metadata(
                        metadata_filter={
                            "source": source_path,
                            "content_hash": current_hash
                        },
                        namespace=DOCUMENT_NAMESPACE
                    )

                    if existing_items:
                        # File unchanged - skip regeneration
                        observability.observe(
                            event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                            level=observability.EventLevel.DEBUG,
                            description="Knowledge source unchanged - using cache",
                            data={
                                "source_name": os.path.basename(source_path),
                                "content_hash": current_hash[:8],
                                "action": "skipped"
                            }
                        )
                        skipped_count += 1
                        # Still need to add to sources list for search functionality
                        knowledge_source = FileKnowledge.from_config(source_config)
                        self.sources.append(knowledge_source)
                        continue

                    # Check if this is an update (file exists with different hash)
                    old_items = self.working_memory.get_items_by_metadata(
                        metadata_filter={"source": source_path},
                        namespace=DOCUMENT_NAMESPACE
                    )

                if old_items:
                    observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.INFO,
                        description="Knowledge source changed - regenerating embeddings",
                        data={
                            "source_name": os.path.basename(source_path),
                            "action": "regenerate"
                        }
                    )
                    # Remove old embeddings
                    if self.working_memory:
                        self.working_memory.remove_by_metadata(
                            metadata_filter={"source": source_path},
                            namespace=DOCUMENT_NAMESPACE
                        )
                    # Remove old cache file
                    cache_file = self._get_cache_file_path(source_path)
                    if os.path.exists(cache_file):
                        try:
                            os.remove(cache_file)
                        except Exception:
                            pass
                else:
                    observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.INFO,
                        description="New knowledge source - generating embeddings",
                        data={
                            "source_name": os.path.basename(source_path),
                            "action": "new"
                        }
                    )

                # Generate embeddings only for this changed/new file
                knowledge_source = FileKnowledge.from_config(source_config)
                await self.add_file(knowledge_source, generate_embeddings_fn)
                processed_count += 1

            except Exception as e:
                source_path = source_config.get("path", "unknown")
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to load knowledge source from config",
                    data={
                        "source_path": source_path,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                continue

        # Init event - visible during startup (Linux init-style)
        if processed_count > 0 or skipped_count > 0:
            from ...datatypes.observability import InitEventFormatter
            total = processed_count + skipped_count
            details = f"{processed_count} processed, {skipped_count} cached"
            if cleanup_count > 0:
                details += f", {cleanup_count} removed"

            print(InitEventFormatter.format_ok(
                f"Knowledge sources: {total} loaded",
                details
            ))
        elif knowledge_sources:
            # Had sources configured but all failed
            from ...datatypes.observability import InitEventFormatter
            print(InitEventFormatter.format_fail(
                "Failed to load any knowledge sources",
                f"{len(knowledge_sources)} sources configured but all failed"
            ))
            # Fail fast - knowledge sources configured but broken
            raise RuntimeError(
                f"Knowledge source initialization failed: "
                f"{len(knowledge_sources)} sources configured but failed"
            )

    async def _inject_knowledge_into_memory(
        self,
        knowledge_results: List[Dict[str, Any]],
        query: str,
        agent_id: Optional[str] = None,
    ) -> None:
        """
        Inject knowledge search results into working memory for persistence.

        Automatically stores knowledge results
        in the formation's working memory system, enabling:
        - Knowledge context persistence across conversations
        - Unified search covering both knowledge and conversation content
        - Proper attribution and tagging of knowledge sources

        Args:
            knowledge_results: List of knowledge search results to inject
            query: The original query that generated these results
            agent_id: Optional agent ID for attribution
        """
        if not self._knowledge_buffer_enabled or not knowledge_results:
            return

        try:
            for result in knowledge_results:
                # Extract content and metadata from knowledge result
                content = result.get("content", "")
                if not content:
                    continue

                # Create knowledge-specific metadata for memory storage
                memory_metadata = {
                    "type": "knowledge",
                    "source": result.get("source", "unknown"),
                    "knowledge_source": result.get("metadata", {}).get(
                        "knowledge_source", "unknown"
                    ),
                    "query": query,
                    "score": result.get("score", 0.0),
                    "timestamp": result.get("metadata", {}).get("timestamp"),
                    "agent_id": agent_id or str(self.agent_id_or_sources),
                    "file_path": result.get("metadata", {}).get("file_path"),
                    "chunk_id": result.get("metadata", {}).get("chunk_id"),
                    "processing_method": result.get("metadata", {}).get("processing_method"),
                }

                # Remove None values from metadata
                memory_metadata = {k: v for k, v in memory_metadata.items() if v is not None}

                # Add to working memory with knowledge namespace
                await self.working_memory.add(
                    text=content, metadata=memory_metadata, namespace=KNOWLEDGE_BUFFER_NAMESPACE
                )

            # Log successful knowledge injection
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_UPDATED,
                level=observability.EventLevel.INFO,
                description="Knowledge results injected into working memory",
                data={
                    "results_count": len(knowledge_results),
                    "query": query[:100],
                    "agent_id": agent_id or str(self.agent_id_or_sources),
                    "memory_namespace": "knowledge",
                },
            )

        except Exception as e:
            # Log error but don't fail the knowledge search
            observability.observe(
                event_type=observability.ConversationEvents.MEMORY_WORKING_UPDATE_FAILED,
                level=observability.EventLevel.WARNING,
                description="Failed to inject knowledge into working memory",
                data={
                    "error": str(e),
                    "query": query[:100],
                    "results_count": len(knowledge_results),
                    "agent_id": agent_id or str(self.agent_id_or_sources),
                },
            )

    async def search_unified(
        self,
        query: str,
        top_k: int = 5,
        generate_embeddings_fn: Optional[Callable] = None,
        include_memory: bool = True,
        memory_weight: float = 0.3,
        session_id: Optional[str] = None,
        knowledge_limit: Optional[int] = None,
        memory_limit: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Unified search across both knowledge sources and working memory.

        Provides comprehensive search capability
        providing agents with both domain knowledge and conversational context
        in a single search operation.

        Args:
            query: The search query string
            top_k: Maximum number of results to return per source type
            generate_embeddings_fn: Function to generate embeddings for semantic search
            include_memory: Whether to include working memory in search
            memory_weight: Weight for memory results vs knowledge results (0.0-1.0)

        Returns:
            Dictionary with 'knowledge' and 'memory' keys containing respective results
        """
        results = {"knowledge": [], "memory": [], "unified": []}

        try:
            # Search knowledge sources (use stored embedding function if not provided)
            knowledge_results = await self.search(
                query=query,
                top_k=knowledge_limit or top_k,
                generate_embeddings_fn=generate_embeddings_fn or self._generate_embeddings_fn,
                session_id=session_id,
            )
            results["knowledge"] = knowledge_results

            # Search working memory if available and requested
            if include_memory and self.working_memory:
                try:
                    memory_results = await self.working_memory.search(
                        query=query,
                        limit=memory_limit or top_k,
                        filter_metadata=None,
                        session_id=session_id,
                    )

                    # Convert memory results to standard format
                    formatted_memory_results = []
                    for result in memory_results:
                        formatted_memory_results.append(
                            {
                                "content": result.get("content", result.get("text", "")),
                                "relevance": result.get("score", 0.0),
                                "source": "memory",
                                "metadata": {
                                    **result.get("metadata", {}),
                                    "source_type": "working_memory",
                                    "timestamp": result.get("metadata", {}).get("timestamp"),
                                },
                            }
                        )

                    results["memory"] = formatted_memory_results

                except Exception as e:
                    # Log memory search error but continue
                    observability.observe(
                        event_type=observability.ConversationEvents.MEMORY_WORKING_UPDATE_FAILED,
                        level=observability.EventLevel.WARNING,
                        description="Failed to search working memory in unified search",
                        data={
                            "error": str(e),
                            "query": query[:100],
                        },
                    )

            # Create unified ranking combining knowledge and memory results
            unified_results = []

            # Add knowledge results with original scores
            for result in knowledge_results:
                unified_result = result.copy()
                unified_result["source_type"] = "knowledge"
                unified_result["weighted_score"] = result.get("relevance", 0.0) * (
                    1.0 - memory_weight
                )
                unified_results.append(unified_result)

            # Add memory results with weighted scores
            for result in results["memory"]:
                unified_result = result.copy()
                unified_result["source_type"] = "memory"
                unified_result["weighted_score"] = result.get("relevance", 0.0) * memory_weight
                unified_results.append(unified_result)

            # Sort by weighted score and limit results
            unified_results.sort(key=lambda x: x.get("weighted_score", 0.0), reverse=True)
            results["unified"] = unified_results[:top_k]

            # Log unified search completion
            observability.observe(
                event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="Unified knowledge and memory search completed",
                data={
                    "query": query[:100],
                    "knowledge_results": len(results["knowledge"]),
                    "memory_results": len(results["memory"]),
                    "unified_results": len(results["unified"]),
                    "memory_weight": memory_weight,
                },
            )

            return results

        except Exception as e:
            # Log unified search error
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SEARCH_FAILED,
                level=observability.EventLevel.ERROR,
                description="Unified search operation failed",
                data={
                    "query": query[:100],
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return results

    def _calculate_file_md5(self, file_path: str) -> str:
        """
        Calculate MD5 hash of file content for cache enhancement.

        This method replaces modification time-based caching with content-based
        MD5 hashing for more reliable cache invalidation. Files are only reprocessed
        when their actual content changes, not when timestamps are modified.

        Args:
            file_path: Path to the file to calculate MD5 hash for

        Returns:
            str: MD5 hash of the file content, or empty string if file not found
        """
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except (FileNotFoundError, IOError, OSError):
            return ""

    def _get_cache_file_path(self, source_path: str) -> str:
        """
        Get the cache file path for a knowledge source.

        Args:
            source_path: Path to the knowledge source file

        Returns:
            str: Path to the cache file for this source
        """
        # Create a safe filename from the source path
        safe_filename = source_path.replace("/", "_").replace("\\", "_").replace(":", "_")
        cache_filename = f"{safe_filename}_{self.agent_id_or_sources}.cache"
        return os.path.join(self.cache_dir, cache_filename)

    def _load_cached_embeddings(
        self, source_path: str, current_hash: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Load cached embeddings for a knowledge source with hash validation.

        Implements hash-based cache validation to ensure
        cached embeddings are only used when the source content hasn't changed.

        Args:
            source_path: Path to the knowledge source file
            current_hash: Current MD5 hash of the source file

        Returns:
            Optional[List[Dict[str, Any]]]: Cached embeddings if valid, None otherwise
        """
        cache_file = self._get_cache_file_path(source_path)

        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, "rb") as f:
                cache_data = pickle.load(f)

            # Validate cache format
            if (
                not isinstance(cache_data, dict)
                or "hash" not in cache_data
                or "embeddings" not in cache_data
            ):
                # Invalid cache format, remove it
                os.remove(cache_file)
                return None

            # Check if hash matches (content unchanged)
            cached_hash = cache_data.get("hash", "")
            if cached_hash != current_hash:
                # Content changed, remove stale cache
                os.remove(cache_file)
                return None

            # Cache is valid, return embeddings
            return cache_data["embeddings"]

        except (pickle.PickleError, IOError, OSError):
            # Cache file corrupted or unreadable, remove it
            try:
                os.remove(cache_file)
            except OSError:
                pass
            return None

    def _save_cached_embeddings(
        self, source_path: str, source_hash: str, embeddings: List[Dict[str, Any]]
    ) -> None:
        """
        Save embeddings to cache with source hash for validation.

        Implements hash-based cache storage to enable
        reliable cache invalidation based on content changes.

        Args:
            source_path: Path to the knowledge source file
            source_hash: MD5 hash of the source file content
            embeddings: Embeddings to cache
        """
        cache_file = self._get_cache_file_path(source_path)

        # Ensure cache directory exists
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        cache_data = {
            "hash": source_hash,
            "embeddings": embeddings,
            "timestamp": time.time(),
            "source_path": source_path,
        }

        try:

            with open(cache_file, "wb") as f:
                pickle.dump(cache_data, f)
        except (pickle.PickleError, IOError, OSError):
            # Failed to save cache, but don't fail the operation
            pass

    def _cleanup_stale_cache_entries(self) -> int:
        """
        Clean up stale cache entries for non-existent or changed files.

        Implements cache cleanup functionality to remove
        cache entries for files that no longer exist or have been modified.

        Returns:
            int: Number of cache entries cleaned up
        """
        if not os.path.exists(self.cache_dir):
            return 0

        cleaned_count = 0

        try:
            for cache_file in os.listdir(self.cache_dir):
                if not cache_file.endswith(".cache"):
                    continue

                cache_path = os.path.join(self.cache_dir, cache_file)

                try:
                    with open(cache_path, "rb") as f:
                        cache_data = pickle.load(f)

                    if not isinstance(cache_data, dict) or "source_path" not in cache_data:
                        # Invalid cache format
                        os.remove(cache_path)
                        cleaned_count += 1
                        continue

                    source_path = cache_data["source_path"]
                    cached_hash = cache_data.get("hash", "")

                    # Check if source file still exists
                    if not os.path.exists(source_path):
                        os.remove(cache_path)
                        cleaned_count += 1
                        continue

                    # Check if content has changed
                    current_hash = self._calculate_file_md5(source_path)
                    if current_hash != cached_hash:
                        os.remove(cache_path)
                        cleaned_count += 1
                        continue

                except (pickle.PickleError, IOError, OSError):
                    # Corrupted or unreadable cache file
                    try:
                        os.remove(cache_path)
                        cleaned_count += 1
                    except OSError:
                        pass

        except OSError:
            # Can't read cache directory
            pass

        return cleaned_count

    def _update_cache_incrementally(self, modified_sources: List[str]) -> int:
        """
        Update cache incrementally for modified knowledge sources.

        Implements incremental cache updates to efficiently
        handle changes to knowledge sources without full reprocessing.

        Args:
            modified_sources: List of source paths that have been modified

        Returns:
            int: Number of sources updated in cache
        """
        updated_count = 0

        for source_path in modified_sources:
            if not os.path.exists(source_path):
                continue

            try:
                # Remove stale cache for this source
                cache_file = self._get_cache_file_path(source_path)
                if os.path.exists(cache_file):
                    os.remove(cache_file)

                # Trigger reprocessing by clearing from semantic index
                # This will cause the file to be reprocessed on next access
                updated_count += 1

            except OSError:
                # Failed to update this source, continue with others
                pass

        return updated_count

    async def cleanup_cache(self) -> Dict[str, int]:
        """
        Perform comprehensive cache cleanup and maintenance.

        Implements comprehensive cache management by
        cleaning up stale entries and providing cache statistics.

        Returns:
            Dict[str, int]: Statistics about cache cleanup operation
        """
        stats = {
            "stale_entries_removed": 0,
            "total_cache_files": 0,
            "valid_cache_files": 0,
            "errors_encountered": 0,
        }

        try:
            # Count total cache files
            if os.path.exists(self.cache_dir):
                all_files = os.listdir(self.cache_dir)
                stats["total_cache_files"] = len([f for f in all_files if f.endswith(".cache")])

            # Clean up stale entries
            stats["stale_entries_removed"] = self._cleanup_stale_cache_entries()

            # Calculate valid cache files remaining
            if os.path.exists(self.cache_dir):
                remaining_files = os.listdir(self.cache_dir)
                stats["valid_cache_files"] = len(
                    [f for f in remaining_files if f.endswith(".cache")]
                )

            # Log cache cleanup results
            observability.observe(
                event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                level=observability.EventLevel.INFO,
                description="Cache cleanup completed",
                data=stats,
            )

        except Exception as e:
            stats["errors_encountered"] = 1
            # Log cache cleanup error
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                description="Cache cleanup failed",
                data={"error": str(e), "error_type": type(e).__name__, **stats},
            )

        return stats
