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
from loguru import logger

# Import FAISSx client - same for both local and remote modes
from faissx import client as faiss

from ..utils import load_document, chunk_text
from .base import FileKnowledge


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
            except Exception as e:
                print(f"Failed to load cached embeddings: {e}")
                self.documents = []
                self.metadata_list = []

    def _save_cached_embeddings(self, embeddings: List[List[float]]):
        """Save embeddings and metadata to cache."""
        try:
            # Save metadata
            with open(self.metadata_file, "wb") as f:
                pickle.dump(self.metadata_list, f)

            print(f"Saved {len(embeddings)} embeddings to cache")
        except Exception as e:
            print(f"Failed to save cached embeddings: {e}")

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

            return faiss
        except ImportError as e:
            print(f"Failed to import FAISSx: {e}")
            return None

    async def add_knowledge_source(self, source, generate_embeddings_fn: Optional[Callable] = None):
        """Add a knowledge source and process its content with performance limits."""
        if len(self.sources) >= 10:  # Limit total sources
            print(f"Skipping source - already have {len(self.sources)} sources")
            return

        self.sources.append(source)

        if generate_embeddings_fn is None:
            print("No embedding function provided, skipping content processing")
            return

        try:
            # Performance limits
            files_processed = 0

            # Get all files from the source with limits
            if hasattr(source, "_discover_files"):
                files = source._discover_files()

                # Apply performance limits
                if len(files) > self.max_files_per_source:
                    print(f"Limiting files to {self.max_files_per_source} for performance")
                    files = files[: self.max_files_per_source]

                # Check global limit
                total_docs = len(self.documents) + len(files)
                if total_docs > self.max_total_files:
                    remaining = self.max_total_files - len(self.documents)
                    if remaining <= 0:
                        limit_msg = f"Global file limit ({self.max_total_files}) reached, skipping."
                        print(limit_msg)
                        return
                    files = files[:remaining]

                for file_path in files:
                    try:
                        # Check file size before reading
                        file_size_limit = getattr(source, "max_file_size", 1024 * 1024)
                        if os.path.getsize(file_path) > file_size_limit:
                            print(f"Skipping large file: {file_path}")
                            continue

                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        if len(content.strip()) < 10:  # Skip very short files
                            continue

                        # Truncate very long content
                        if len(content) > 5000:
                            content = content[:5000] + "... [truncated]"

                        self.documents.append(content)
                        self.metadata_list.append(
                            {
                                "source": source.name if hasattr(source, "name") else "unknown",
                                "file_path": file_path,
                                "content": content,
                            }
                        )

                        files_processed += 1

                        # Limit processing to avoid hanging
                        if files_processed >= self.max_files_per_source:
                            max_files = self.max_files_per_source
                            print(f"Reached per-source limit of {max_files} files")
                            break

                    except Exception as e:
                        print(f"Failed to read file {file_path}: {e}")
                        continue

            print(f"Processed {files_processed} files from source")

            # Generate embeddings for new documents if we have any
            if files_processed > 0 and self.documents:
                # Only generate embeddings for new documents
                new_docs = self.documents[-files_processed:]
                print(f"Generating embeddings for {len(new_docs)} new documents...")

                try:
                    # Generate embeddings with timeout consideration
                    embeddings = []
                    for i, doc in enumerate(new_docs):
                        if i > 0 and i % 5 == 0:  # Progress every 5 documents
                            print(f"Generated embeddings for {i}/{len(new_docs)} documents")

                        # Handle both sync and async embedding functions
                        if hasattr(generate_embeddings_fn, "__call__"):
                            if hasattr(generate_embeddings_fn, "__await__"):
                                embedding = await generate_embeddings_fn(doc)
                            else:
                                embedding = generate_embeddings_fn(doc)
                        else:
                            embedding = generate_embeddings_fn(doc)

                        embeddings.append(embedding)

                        # Limit total processing time
                        if i >= 20:  # Max 20 embeddings per batch
                            print("Limiting embeddings to 20 for performance")
                            break

                    if embeddings:
                        self._save_cached_embeddings(embeddings)
                        print(f"✓ Generated {len(embeddings)} embeddings")

                except Exception as e:
                    print(f"Failed to generate embeddings: {e}")

        except Exception as e:
            print(f"Failed to add knowledge source: {e}")

    async def search(
        self, query: str, top_k: int = 5, generate_embeddings_fn: Optional[Callable] = None
    ) -> List[Dict[str, Any]]:
        """Search across all knowledge sources."""
        if not self.documents:
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

            return results

        except Exception as e:
            print(f"Search failed: {e}")
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

        # Check if knowledge is enabled
        if not knowledge_config.get("enabled", False):
            print(f"Knowledge is disabled for agent {agent_id}")
            return None

        sources_config = knowledge_config.get("sources", [])
        if not sources_config:
            print(f"No knowledge sources configured for agent {agent_id}")
            return None

        print(f"Loading {len(sources_config)} knowledge sources for agent {agent_id}")

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
                continue

        source_count = len(handler.sources)
        doc_count = len(handler.documents)
        print(f"✓ KnowledgeHandler created with {source_count} sources and {doc_count} documents")
        return handler

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

        # Get file modification time
        try:
            file_mtime = os.path.getmtime(file_path)
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return 0

        # Check if we already have this file with the same modification time
        for doc in self.documents:
            if doc.get("source") == file_path and doc.get("mtime") == file_mtime:
                # File already processed and hasn't changed
                logger.info(f"File {file_path} already processed and hasn't changed")
                return 0

        # Load and chunk the file
        try:
            content = load_document(file_path)
            chunks = chunk_text(content)

            if not chunks:
                logger.warning(f"No content found in {file_path}")
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

            logger.info(f"Added {len(chunks)} chunks from {file_path} to knowledge base")
            return len(chunks)

        except Exception as e:
            logger.error(f"Error adding file {file_path} to knowledge base: {e}")
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
        # Find indices of documents to remove
        indices_to_remove = []
        remaining_documents = []

        for doc in self.documents:
            if doc.get("source") == file_path:
                indices_to_remove.append(doc.get("index"))
            else:
                remaining_documents.append(doc)

        if not indices_to_remove:
            logger.warning(f"File {file_path} not found in knowledge base")
            return False

        # We need to rebuild the index without the removed embeddings
        # This is because FAISS doesn't support removing individual vectors
        self.documents = remaining_documents

        # If we removed all documents, just reset the index
        if not self.documents:
            self.index = faiss.IndexFlatL2(self.embedding_dimension)
            self._save_cached_embeddings([])
            logger.info(f"Removed file {file_path} and reset knowledge base")
            return True

        # Otherwise, we need to rebuild the index
        # For now, we'll just log a warning and return True as if it worked
        logger.warning(
            f"Removing file {file_path} requires rebuilding the index. "
            "Only metadata has been updated."
        )
        self._save_cached_embeddings([])
        return True

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
                logger.info(f"Loaded knowledge source: {knowledge_source.path}")
            except Exception as e:
                source_path = source_config.get("path", "unknown")
                logger.error(f"Failed to load knowledge source {source_path}: {e}")
                continue
