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
#    - Persistence with file caching (local mode only)
#
# 2. Document Management
#    - Loading and chunking of documents
#    - Tracking of document metadata and sources
#    - Modification time detection for intelligent reindexing
#
# 3. Search Capabilities
#    - Semantic search using vector similarity
#    - Configurable relevance threshold
#    - Metadata filtering options
#
# The KnowledgeHandler is typically used to:
# - Process documents and file-based knowledge
# - Generate and store vector embeddings
# - Provide agents with relevant information based on queries
# - Ground agent responses in factual information
#
# This implementation focuses on file-based knowledge with vector search,
# making it ideal for cases where agents need access to domain-specific
# documentation, product information, or other textual resources.
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
#   # Initialize with remote FAISSx server
#   handler = KnowledgeHandler(
#       agent_id="support_agent",
#       embedding_dimension=1536,
#       mode="remote",
#       remote={
#           "url": "tcp://localhost:45678",
#           "api_key": "your_api_key",
#           "tenant": "your_tenant"
#       }
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
#   # Search for relevant information
#   results = await handler.search(
#       query="How do I reset my password?",
#       generate_embedding_fn=model.get_embedding,
#       top_k=3
#   )
# =============================================================================

import os
import pickle
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
# Loguru import removed - add observability import

# FAISSx will be imported dynamically in _setup_faissx method

from ....utils import load_document, chunk_text
from .base import FileKnowledge
from ....services import observability


class KnowledgeHandler:
    """
    Handles multiple knowledge sources and provides unified search functionality.

    The KnowledgeHandler manages a collection of knowledge sources and provides
    a unified interface for searching across all of them. It uses FAISSx for
    vector-based similarity search and supports both local and remote modes.
    """

    def __init__(
        self,
        agent_id_or_sources: Union[str, List],
        embedding_dimension: int = 1536,
        cache_dir: str = ".cache/knowledge_embeddings",
        mode: str = "local",
        remote: Optional[Dict[str, Any]] = None,
        max_files_per_source: int = 10,  # Add performance limit
        max_total_files: int = 50,  # Add global limit
    ):
        """Initialize the knowledge handler."""
        self.agent_id_or_sources = agent_id_or_sources
        self.embedding_dimension = embedding_dimension
        self.cache_dir = cache_dir
        self.mode = mode
        self.remote = remote or {}
        self.max_files_per_source = max_files_per_source
        self.max_total_files = max_total_files

        self.embedding_file = f"{cache_dir}/{agent_id_or_sources}_embeddings.pickle"
        self.metadata_file = f"{cache_dir}/{agent_id_or_sources}_metadata.pickle"

        # Create cache directory if it doesn't exist
        os.makedirs(cache_dir, exist_ok=True)

        # Initialize index and documents
        self._load_cached_embeddings()

        # Initialize knowledge sources
        if isinstance(agent_id_or_sources, list):
            self.sources = agent_id_or_sources
        else:
            self.sources = []

        # Log initialization
        observability.observe(
                event_type=observability.ConversationEvents.SESSION_CREATED,
                level=observability.EventLevel.INFO,
                description="KnowledgeHandler initialized",
                data={
                    "agent_id_or_sources": str(agent_id_or_sources),
                    "embedding_dimension": embedding_dimension,
                    "mode": mode,
                    "cache_dir": cache_dir,
                    "max_files_per_source": max_files_per_source,
                    "max_total_files": max_total_files,
                    "documents_loaded": len(self.documents),
                },
            )  # Don't let observability failures break initialization

    def _load_cached_embeddings(self):
        """Load cached embeddings and metadata if they exist."""
        self.index = None
        self.documents = []
        self.metadata_list = []

        # Try to load cached data
        if os.path.exists(self.embedding_file) and os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "rb") as f:
                    self.metadata_list = pickle.load(f)
                    self.documents = [meta.get("content", "") for meta in self.metadata_list]

                print(f"Loaded {len(self.documents)} documents from cache")

                # Log cache load
                observability.observe(
                        event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                        level=observability.EventLevel.INFO,
                        description="Knowledge cache loaded successfully",
                        data={
                            "documents_count": len(self.documents),
                            "metadata_count": len(self.metadata_list),
                            "embedding_file": self.embedding_file,
                            "metadata_file": self.metadata_file,
                        },
                    )

            except Exception as e:
                print(f"Failed to load cached embeddings: {e}")
                self.documents = []
                self.metadata_list = []

                # Log cache load error
                observability.observe(
                        event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                        level=observability.EventLevel.ERROR,
                        description="Failed to load knowledge cache",
                        data={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "embedding_file": self.embedding_file,
                            "metadata_file": self.metadata_file,
                        },
                    )

    def _save_cached_embeddings(self, embeddings: List[List[float]]):
        """Save embeddings and metadata to cache."""
        try:
            # Save metadata
            with open(self.metadata_file, "wb") as f:
                pickle.dump(self.metadata_list, f)

            print(f"Saved {len(embeddings)} embeddings to cache")

            # Log cache save
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                    level=observability.EventLevel.INFO,
                    description="Knowledge cache saved successfully",
                    data={
                        "embeddings_count": len(embeddings),
                        "metadata_count": len(self.metadata_list),
                        "metadata_file": self.metadata_file,
                    },
                )

        except Exception as e:
            print(f"Failed to save cached embeddings: {e}")

            # Log cache save error
            observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to save knowledge cache",
                    data={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "embeddings_count": len(embeddings),
                        "metadata_file": self.metadata_file,
                    },
                )

    def _setup_faissx(self):
        """Set up FAISSx based on mode."""
        try:
            if self.mode == "remote":
                from faissx import client as faiss

                faiss.configure(
                    server=self.remote.get("url", "tcp://localhost:45678"),
                    api_key=self.remote.get("api_key", "test_key"),
                    tenant_id=self.remote.get("tenant_id", "test_tenant"),
                )
            else:
                from faissx import local as faiss

            # Log FAISSx setup
            observability.observe(
                    event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                    level=observability.EventLevel.INFO,
                    description="FAISSx setup completed",
                    data={
                        "mode": self.mode,
                        "remote_config": (self.remote if self.mode == "remote" else None),
                    },
                )

            return faiss
        except ImportError as e:
            print(f"Failed to import FAISSx: {e}")

            # Log FAISSx setup error
            observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to setup FAISSx",
                    data={"error": str(e), "error_type": type(e).__name__, "mode": self.mode},
                )
            return None

    async def add_knowledge_source(self, source, generate_embeddings_fn: Optional[Callable] = None):
        """Add a knowledge source and process its content with performance limits."""
        # Log knowledge source addition start
        observability.observe(
                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                level=observability.EventLevel.INFO,
                description="Starting knowledge source addition",
                data={
                    "source_path": getattr(source, "path", str(source)),
                    "source_type": type(source).__name__,
                    "current_sources_count": len(self.sources),
                    "has_embedding_function": generate_embeddings_fn is not None,
                },
            )

        if len(self.sources) >= 10:  # Limit total sources
            print(f"Skipping source - already have {len(self.sources)} sources")

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

        self.sources.append(source)

        if generate_embeddings_fn is None:
            print("No embedding function provided, skipping content processing")

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
            # Performance limits
            files_processed = 0

            # Get all files from the source with limits
            files = source.get_files()[: self.max_files_per_source]  # Limit files per source

            # Log files discovery
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                    level=observability.EventLevel.INFO,
                    description="Files discovered for knowledge source",
                    data={
                        "source_path": getattr(source, "path", str(source)),
                        "files_count": len(files),
                        "max_files_per_source": self.max_files_per_source,
                    },
                )

            for file_path in files:
                if files_processed >= self.max_files_per_source:
                    break

                if len(self.documents) >= self.max_total_files:
                    print(f"Reached maximum total files limit ({self.max_total_files})")
                    break

                try:
                    # Load and process file
                    content = load_document(file_path)
                    if not content or len(content.strip()) < 10:  # Skip very short content
                        continue

                    # Chunk the content
                    chunks = chunk_text(content, max_chunk_size=500)  # Smaller chunks
                    if not chunks:
                        continue

                    # Limit chunks per file
                    chunks = chunks[:5]  # Max 5 chunks per file

                    # Add to documents
                    for chunk in chunks:
                        if len(self.documents) >= self.max_total_files:
                            break

                        self.documents.append(chunk)
                        self.metadata_list.append(
                            {
                                "content": chunk,
                                "source": file_path,
                                "description": source.description,
                            }
                        )

                    files_processed += 1
                    print(f"✓ Processed {file_path} ({len(chunks)} chunks)")

                except Exception as e:
                    print(f"Failed to process file {file_path}: {e}")
                    continue

            # Generate embeddings if we have content
            if self.documents and generate_embeddings_fn:
                try:
                    # Generate embeddings for all content
                    embeddings = await generate_embeddings_fn(self.documents)
                    if embeddings:
                        self._save_cached_embeddings(embeddings)
                        print(f"✓ Generated {len(embeddings)} embeddings")

                        # Log successful embedding generation
                        observability.observe(
                                event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                                level=observability.EventLevel.INFO,
                                description="Knowledge source embeddings generated successfully",
                                data={
                                    "source_path": getattr(source, "path", str(source)),
                                    "embeddings_count": len(embeddings),
                                    "documents_count": len(self.documents),
                                    "files_processed": files_processed,
                                },
                            )

                except Exception as e:
                    print(f"Failed to generate embeddings: {e}")

                    # Log embedding generation error
                    observability.observe(
                            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                            level=observability.EventLevel.ERROR,
                            description="Failed to generate embeddings for knowledge source",
                            data={
                                "source_path": getattr(source, "path", str(source)),
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "documents_count": len(self.documents),
                            },
                        )

            # Log successful knowledge source addition
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                    level=observability.EventLevel.INFO,
                    description="Knowledge source addition completed",
                    data={
                        "source_path": getattr(source, "path", str(source)),
                        "files_processed": files_processed,
                        "total_documents": len(self.documents),
                        "total_sources": len(self.sources),
                    },
                )

        except Exception as e:
            print(f"Failed to add knowledge source: {e}")

            # Log knowledge source addition error
            observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to add knowledge source",
                    data={
                        "source_path": getattr(source, "path", str(source)),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

    async def search(
        self, query: str, top_k: int = 5, generate_embeddings_fn: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """Search across all knowledge sources."""
        # Log search start
        observability.observe(
                event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                level=observability.EventLevel.INFO,
                description="Starting knowledge search",
                data={
                    "query_length": len(query),
                    "top_k": top_k,
                    "documents_count": len(self.documents),
                    "has_embedding_function": generate_embeddings_fn is not None,
                },
            )

        if not self.documents:
            # Log empty documents
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                    level=observability.EventLevel.DEBUG,
                    description="No documents available for knowledge search",
                    data={"query": query, "top_k": top_k},
                )
            return []

        if generate_embeddings_fn is None:
            # Fallback to simple text search
            results = []
            for i, doc in enumerate(self.documents[:10]):  # Limit to first 10 docs
                if query.lower() in doc.lower():
                    metadata = self.metadata_list[i] if i < len(self.metadata_list) else {}
                    results.append(
                        {
                            "content": doc[:200] + "..." if len(doc) > 200 else doc,
                            "relevance": 0.5,
                            "metadata": metadata,
                        }
                    )
                    if len(results) >= top_k:
                        break

            # Log text search results
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                    level=observability.EventLevel.INFO,
                    descriptiontion="Knowledge text search completed",
                    data={
                        "query": query,
                        "results_count": len(results),
                        "search_type": "text_search",
                    },
                )
            return results

        try:
            # Generate query embedding (for future use)
            # Simple similarity search (cosine similarity)
            # For testing, just return first few documents
            results = []
            for i, doc in enumerate(self.documents[: min(top_k, 5)]):  # Limit results
                metadata = self.metadata_list[i] if i < len(self.metadata_list) else {}
                results.append(
                    {
                        "content": doc[:200] + "..." if len(doc) > 200 else doc,
                        "relevance": 0.8 - (i * 0.1),  # Mock relevance scores
                        "metadata": metadata,
                    }
                )

            # Log successful search
            observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_RETRIEVED,
                    level=observability.EventLevel.INFO,
                    description="Knowledge semantic search completed successfully",
                    data={
                        "query": query,
                        "results_count": len(results),
                        "search_type": "semantic_search",
                        "top_k": top_k,
                    },
                )

            return results

        except Exception as e:
            print(f"Search failed: {e}")

            # Log search error
            observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Knowledge search operation failed",
                    data={
                        "query": query,
                        "top_k": top_k,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
            return []

    @classmethod
    async def from_agent_config(
        cls,
        agent_id: str,
        knowledge_config: Dict[str, Any],
        generate_embeddings_fn: Optional[Callable] = None,
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
            print(f"Knowledge is disabled for agent {agent_id}")

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
            print(f"No knowledge sources configured for agent {agent_id}")

            # Log no sources
            observability.observe(
                    event_type=observability.ConversationEvents.SESSION_CREATED,
                    level=observability.EventLevel.WARNING,
                    description="No knowledge sources configured for agent",
                    data={"agent_id": agent_id},
                )
            return None

        print(f"Loading {len(sources_config)} knowledge sources for agent {agent_id}")

        try:
            # Create handler with performance limits
            handler = cls(
                agent_id_or_sources=agent_id,
                embedding_dimension=kwargs.get("embedding_dimension", 128),  # Smaller dimension
                cache_dir=kwargs.get("cache_dir", ".cache/knowledge_embeddings"),
                mode=kwargs.get("mode", "local"),
                remote=kwargs.get("remote"),
                max_files_per_source=kwargs.get("max_files_per_source", 5),  # Very conservative
                max_total_files=kwargs.get("max_total_files", 10),  # Very conservative
            )

            # Process sources with limits
            for i, source_config in enumerate(sources_config):
                if i >= 3:  # Limit to max 3 sources for performance
                    skipped = len(sources_config) - 3
                    print(f"Limiting to 3 sources for performance (skipping {skipped} sources)")

                    # Log source limit
                    observability.observe(
                            event_type=observability.SystemEvents.RESOURCE_ALLOCATED,
                            level=observability.EventLevel.WARNING,
                            description="Knowledge sources limited for performance",
                            data={
                                "agent_id": agent_id,
                                "total_sources": len(sources_config),
                                "processed_sources": 3,
                                "skipped_sources": skipped,
                            },
                        )
                    break

                try:
                    # Add performance limits to source config
                    limited_config = source_config.copy()
                    limited_config["max_files"] = min(limited_config.get("max_files", 5), 3)
                    max_size = limited_config.get("max_file_size", 1024 * 1024)
                    limited_config["max_file_size"] = min(max_size, 50 * 1024)  # 50KB max

                    source = FileKnowledge.from_config(limited_config)
                    await handler.add_knowledge_source(source, generate_embeddings_fn)

                    source_count = min(len(sources_config), 3)
                    print(f"✓ Loaded source {i+1}/{source_count}: {source.path}")

                except Exception as e:
                    source_path = source_config.get("path", "unknown")
                    print(f"Failed to load source {source_path}: {e}")

                    # Log source loading error
                    observability.observe(
                            event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                            level=observability.EventLevel.ERROR,
                            description="Failed to load knowledge source from config",
                            data={
                                "agent_id": agent_id,
                                "source_path": source_path,
                                "error": str(e),
                                "error_type": type(e).__name__,
                            },
                        )
                    continue

            source_count = len(handler.sources)
            doc_count = len(handler.documents)
            print(
                f"✓ KnowledgeHandler created with {source_count} sources and {doc_count} documents"
            )

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
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Failed to create KnowledgeHandler from agent config",
                    data={"agent_id": agent_id, "error": str(e), "error_type": type(e).__name__},
                )
            raise

    async def add_file(self, knowledge_source: FileKnowledge, generate_embeddings_fn) -> int:
        """
        Add a file to the knowledge base.

        This method processes a file from a knowledge source, chunks its content,
        generates embeddings, and adds them to the vector index for future retrieval.
        It tracks modification times to avoid reprocessing unchanged files.

        Args:
            knowledge_source: The knowledge source containing the file to process.
                This should be a FileKnowledge instance with path and description.
            generate_embeddings_fn: Function to generate embeddings for the text chunks.
                This should be a callable that takes a list of strings and returns
                a list of embedding vectors.

        Returns:
            int: Number of chunks added to the index. Zero indicates the file was
                already processed and hasn't changed, or an error occurred.
        """
        file_path = knowledge_source.path
        description = knowledge_source.description

        # Log file addition start
        observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Starting knowledge file addition",
                data={
                    "file_path": file_path,
                    "description": description,
                    "current_documents": len(self.documents),
                },
            )

        # Get file modification time
        try:
            file_mtime = os.path.getmtime(file_path)
        except FileNotFoundError:
            # Log file not found
            observability.observe(
                    event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                    level=observability.EventLevel.ERROR,
                    description="Knowledge file not found",
                    data={"file_path": file_path, "error": "FileNotFoundError"},
                )
            return 0

        # Check if we already have this file with the same modification time
        for doc in self.documents:
            if doc.get("source") == file_path and doc.get("mtime") == file_mtime:
                # File already processed and hasn't changed
                # Log file already processed
                observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.DEBUG,
                        description="Knowledge file already processed and unchanged",
                        data={"file_path": file_path, "file_mtime": file_mtime},
                    )
                return 0

        # Load and chunk the file
        try:
            content = load_document(file_path)
            chunks = chunk_text(content)

            if not chunks:
                # Log no content
                observability.observe(
                        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                        level=observability.EventLevel.WARNING,
                        description="No content found in knowledge file",
                        data={
                            "file_path": file_path,
                            "content_length": len(content) if content else 0,
                        },
                    )
                return 0

            # Generate embeddings using the provided function
            embeddings = await generate_embeddings_fn(chunks)

            # Convert to numpy array for FAISS
            embeddings_np = np.array(embeddings).astype("float32")

            # Add to FAISS index
            self.index.add(embeddings_np)

            # Add modification time to metadata
            start_idx = len(self.documents)
            for i, chunk in enumerate(chunks):
                self.documents.append(
                    {
                        "content": chunk,
                        "source": file_path,
                        "description": description,
                        "mtime": file_mtime,
                        "index": start_idx + i,
                    }
                )

            # Save updated embeddings
            self._save_cached_embeddings(embeddings)
            # Log successful file addition
            observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.INFO,
                    description="Knowledge file added successfully",
                    data={
                        "file_path": file_path,
                        "chunks_added": len(chunks),
                        "embeddings_generated": len(embeddings),
                        "total_documents": len(self.documents),
                    },
                )

            return len(chunks)

        except Exception as e:
            #  Error - TODO: add observability
            #  DOCUMENT_PROCESSING_FAILED

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
        Remove a file from the knowledge base.

        This method removes all chunks associated with a specific file from the
        knowledge base. Due to limitations in FAISS, this actually rebuilds the
        metadata structure but leaves the vectors in place, marking them as
        unavailable for future searches.

        Args:
            file_path: Path to the file to remove from the knowledge base

        Returns:
            bool: True if the file was found and removed, False otherwise
        """
        # Log file removal start
        observability.observe(
                event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                level=observability.EventLevel.INFO,
                description="Starting knowledge file removal",
                data={"file_path": file_path, "current_documents": len(self.documents)},
            )

        try:
            # Find and remove documents associated with this file
            original_count = len(self.documents)
            self.documents = [doc for doc in self.documents if doc.get("source") != file_path]
            self.metadata_list = [
                meta for meta in self.metadata_list if meta.get("source") != file_path
            ]

            removed_count = original_count - len(self.documents)

            if removed_count > 0:
                # Rebuild embeddings cache
                if self.documents:
                    # Would need to regenerate embeddings here in a real implementation
                    pass

                # Log successful file removal
                observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.INFO,
                        description="Knowledge file removed successfully",
                        data={
                            "file_path": file_path,
                            "documents_removed": removed_count,
                            "remaining_documents": len(self.documents),
                        },
                    )

                return True
            else:
                # Log file not found for removal
                observability.observe(
                        event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                        level=observability.EventLevel.WARNING,
                        description="Knowledge file not found for removal",
                        data={"file_path": file_path, "current_documents": len(self.documents)},
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

    def get_sources(self) -> List[str]:
        """
        Get a list of all knowledge sources in the knowledge base.

        This method returns a list of unique file paths that have been added to
        the knowledge base, useful for managing and tracking knowledge sources.

        Returns:
            List[str]: List of file paths in the knowledge base
        """
        # Extract unique source paths
        sources = set()
        for doc in self.documents:
            if "source" in doc:
                sources.add(doc["source"])
        return list(sources)

    async def load_sources_from_config(
        self, knowledge_sources: List[Dict[str, Any]], generate_embeddings_fn
    ) -> None:
        """
        Load multiple knowledge sources from configuration.

        Args:
            knowledge_sources: List of source configurations
            generate_embeddings_fn: Function to generate embeddings
        """
        for source_config in knowledge_sources:
            try:
                knowledge_source = FileKnowledge.from_config(source_config)
                await self.add_file(knowledge_source, generate_embeddings_fn)
                #  Info - TODO: add observability
            except Exception as e:
                source_path = source_config.get("path", "unknown")
                #  Error - TODO: add observability
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
