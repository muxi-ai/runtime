"""
Document-Aware Buffer Memory Implementation

This module extends WorkingMemory with document processing capabilities,
providing temporal scope and lifecycle management for document content.

Features:
- Document-aware content buffering
- Document lifecycle management in FIFO eviction
- Document chunk integration with semantic search
- Cross-document reference tracking
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .chunk_manager import DocumentChunkManager
from .metadata_store import DocumentMetadata, DocumentMetadataStore


@dataclass
class DocumentBufferEntry:
    """Represents a document entry in the buffer memory"""

    document_id: str
    filename: str
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    timestamp: float
    document_metadata: DocumentMetadata

    def to_memory_item(self) -> Dict[str, Any]:
        """Convert to standard memory item format"""
        return {
            "content": self.content,
            "metadata": {
                **self.metadata,
                "document_id": self.document_id,
                "filename": self.filename,
                "chunk_id": self.chunk_id,
                "timestamp": self.timestamp,
                "is_document": True,
            },
        }


class DocumentAwareBufferMemory:
    """
    Extended buffer memory with document processing capabilities.

    Provides document-aware content buffering with lifecycle management,
    semantic search across document chunks, and integration with the
    document storage foundation layer.

    This class dynamically inherits from WorkingMemory to avoid circular imports.
    """

    def __init__(
        self,
        formation_id: str,
        max_size: int = 10,
        buffer_multiplier: int = 10,
        model=None,
        vector_dimension: int = 1536,
        recency_bias: float = 0.3,
        mode: str = "local",
        remote: Optional[Dict[str, Any]] = None,
        max_memory_mb: int = 1000,
        fifo_interval_min: float = 5,
        metadata_storage_path: Optional[str] = None,
    ):
        """
        Initialize document-aware buffer memory.

        Args:
            formation_id: The formation ID for scoping data
            max_size: Context window size (number of recent messages)
            buffer_multiplier: Total capacity multiplier
            model: Model for generating embeddings
            vector_dimension: Dimension for embedding vectors
            recency_bias: Balance between semantic relevance and recency
            mode: Vector search mode ("local" or "remote")
            remote: Remote configuration for FAISSx
            max_memory_mb: Maximum memory usage in MB
            fifo_interval_min: FIFO cleanup interval in minutes
            chunk_config: Configuration for document chunking
            metadata_storage_path: Path for document metadata storage
        """
        # Initialize the underlying working memory
        from ....services.memory.working import WorkingMemory

        self._working_memory = WorkingMemory(
            formation_id=formation_id,
            max_size=max_size,
            buffer_multiplier=buffer_multiplier,
            model=model,
            dimension=vector_dimension,
            recency_bias=recency_bias,
            mode=mode,
            remote=remote,
            max_memory_mb=max_memory_mb,
            fifo_interval_min=fifo_interval_min,
        )

        # Copy important private attributes
        for attr in [
            "buffer",
            "max_size",
            "buffer_multiplier",
            "model",
            "vector_dimension",
            "recency_bias",
            "mode",
            "remote",
            "max_memory_mb",
            "fifo_interval_min",
            "has_vector_search",
        ]:
            if hasattr(self._working_memory, attr):
                setattr(self, attr, getattr(self._working_memory, attr))

        # Document-specific components
        from ...config.document_processing import DocumentProcessingConfig

        # Create proper DocumentProcessingConfig from chunk_config
        document_config = DocumentProcessingConfig({})

        self.chunk_manager = DocumentChunkManager(document_config=document_config)
        self.metadata_store = DocumentMetadataStore(metadata_storage_path)

        # Document tracking
        self._document_entries: Dict[str, List[DocumentBufferEntry]] = {}
        self._chunk_to_document: Dict[str, str] = {}  # chunk_id -> document_id
        self._document_timestamps: Dict[str, float] = {}  # document_id -> upload_time

    async def add_document(
        self,
        content: str,
        filename: str,
        user_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
        chunking_strategy: str = "adaptive",
    ) -> str:
        """
        Add a complete document to buffer memory with chunking.

        Args:
            content: Document content
            filename: Original filename
            user_id: Optional user ID
            tags: Optional tags for the document
            custom_metadata: Optional custom metadata
            chunking_strategy: Chunking strategy to use

        Returns:
            Document ID
        """

        # Chunk the document
        chunks = await self.chunk_manager.chunk_document(
            content=content, filename=filename, strategy=chunking_strategy
        )

        if not chunks:
            raise ValueError(f"Failed to chunk document {filename}")

        document_id = chunks[0].document_id
        current_time = time.time()

        # Store document metadata
        file_size = len(content.encode("utf-8"))
        total_words = sum(chunk.metadata.get("word_count", 0) for chunk in chunks)

        document_metadata = await self.metadata_store.store_document_metadata(
            document_id=document_id,
            filename=filename,
            file_size=file_size,
            chunk_count=len(chunks),
            total_word_count=total_words,
            chunk_strategy=chunking_strategy,
            user_id=user_id,
            tags=tags,
            custom_metadata=custom_metadata,
        )

        # Create buffer entries for each chunk
        buffer_entries = []
        for chunk in chunks:
            entry = DocumentBufferEntry(
                document_id=document_id,
                filename=filename,
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                metadata=chunk.metadata,
                timestamp=current_time,
                document_metadata=document_metadata,
            )
            buffer_entries.append(entry)

            # Track chunk-to-document mapping
            self._chunk_to_document[chunk.chunk_id] = document_id

            # Add to buffer memory
            await self.add(entry.content, metadata=entry.to_memory_item()["metadata"])

        # Track document entries
        self._document_entries[document_id] = buffer_entries
        self._document_timestamps[document_id] = current_time

        return document_id

    async def search_documents(
        self,
        query: str,
        limit: int = 10,
        document_ids: Optional[List[str]] = None,
        filename_pattern: Optional[str] = None,
        tags: Optional[List[str]] = None,
        user_id: Optional[int] = None,
        recency_bias: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search specifically within document content.

        Args:
            query: Search query
            limit: Maximum number of results
            document_ids: Optional specific document IDs to search
            filename_pattern: Optional filename pattern filter
            tags: Optional tags filter
            user_id: Optional user ID filter
            recency_bias: Optional recency bias override

        Returns:
            List of search results with document context
        """
        # Build metadata filter for document content
        filter_metadata = {"is_document": True}

        if user_id is not None:
            filter_metadata["user_id"] = user_id

        # Perform search using parent class method
        results = await self.search(
            query=query,
            limit=limit * 3,  # Get more results for filtering
            filter_metadata=filter_metadata,
            recency_bias=recency_bias or self.recency_bias,
        )

        # Filter and enhance results
        filtered_results = []
        seen_documents = set()

        for result in results:
            metadata = result.get("metadata", {})
            document_id = metadata.get("document_id")

            if not document_id:
                continue

            # Apply document-specific filters
            if document_ids and document_id not in document_ids:
                continue

            # Get document metadata for additional filtering
            doc_metadata = await self.metadata_store.get_document_metadata(document_id)
            if not doc_metadata:
                continue

            # Apply filename filter
            if filename_pattern:
                import fnmatch

                if not fnmatch.fnmatch(doc_metadata.filename.lower(), filename_pattern.lower()):
                    continue

            # Apply tags filter
            if tags and not all(tag in doc_metadata.tags for tag in tags):
                continue

            # Enhance result with document context
            enhanced_result = {
                **result,
                "document_context": {
                    "document_id": document_id,
                    "filename": doc_metadata.filename,
                    "chunk_id": metadata.get("chunk_id"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "total_chunks": doc_metadata.chunk_count,
                    "document_tags": doc_metadata.tags,
                    "upload_timestamp": doc_metadata.upload_timestamp,
                },
            }

            filtered_results.append(enhanced_result)
            seen_documents.add(document_id)

            if len(filtered_results) >= limit:
                break

        return filtered_results

    async def get_document_chunks(self, document_id: str) -> List[DocumentBufferEntry]:
        """
        Get all chunks for a specific document.

        Args:
            document_id: Document identifier

        Returns:
            List of document buffer entries
        """
        return self._document_entries.get(document_id, [])

    async def remove_document(self, document_id: str) -> bool:
        """
        Remove a complete document from buffer memory.

        Args:
            document_id: Document identifier

        Returns:
            True if document was removed, False if not found
        """
        if document_id not in self._document_entries:
            return False

        # Remove all chunks from buffer
        entries = self._document_entries[document_id]
        for entry in entries:
            # Find and remove from buffer
            for i, item in enumerate(self.buffer):
                if item.get("metadata", {}).get("chunk_id") == entry.chunk_id:
                    del self.buffer[i]
                    break

            # Remove from chunk mapping
            self._chunk_to_document.pop(entry.chunk_id, None)

        # Remove document tracking
        del self._document_entries[document_id]
        self._document_timestamps.pop(document_id, None)

        # Remove from metadata store
        await self.metadata_store.delete_document_metadata(document_id)

        # Rebuild vector index if needed
        if self.has_vector_search:
            await self._rebuild_vector_index()

        return True

    def get_document_stats(self) -> Dict[str, Any]:
        """
        Get statistics about documents in buffer memory.

        Returns:
            Dictionary with document statistics
        """
        if not self._document_entries:
            return {"total_documents": 0, "total_chunks": 0}

        total_chunks = sum(len(entries) for entries in self._document_entries.values())
        chunk_counts = [len(entries) for entries in self._document_entries.values()]

        # Get storage stats from metadata store
        storage_stats = self.metadata_store.get_storage_stats()

        return {
            "total_documents": len(self._document_entries),
            "total_chunks_in_buffer": total_chunks,
            "avg_chunks_per_document": sum(chunk_counts) / len(chunk_counts),
            "min_chunks_per_document": min(chunk_counts),
            "max_chunks_per_document": max(chunk_counts),
            "oldest_document_timestamp": min(self._document_timestamps.values()),
            "newest_document_timestamp": max(self._document_timestamps.values()),
            **storage_stats,
        }

    async def _enhanced_fifo_cleanup(self) -> None:
        """
        Enhanced FIFO cleanup that respects document boundaries.

        Removes oldest documents completely rather than individual chunks
        to maintain document integrity.
        """
        current_memory = self._estimate_memory_usage()
        if current_memory <= self.max_memory_mb:
            return

        #     f"Document-aware FIFO cleanup triggered: {current_memory}MB > {self.max_memory_mb}MB"
        # )

        # Sort documents by timestamp (oldest first)
        sorted_docs = sorted(self._document_timestamps.items(), key=lambda x: x[1])

        # Remove oldest documents until memory is acceptable
        removed_count = 0
        for document_id, timestamp in sorted_docs:
            if current_memory <= self.max_memory_mb * 0.8:  # Leave some headroom
                break

            # Remove the entire document
            await self.remove_document(document_id)
            removed_count += 1

            # Recalculate memory usage
            current_memory = self._estimate_memory_usage()

    async def _rebuild_vector_index(self) -> None:
        """Rebuild the vector index after document removal"""
        if not self.has_vector_search or not self.buffer:
            return

        # Get all current content for re-indexing
        contents = []
        for item in self.buffer:
            if isinstance(item, dict) and "content" in item:
                contents.append(item["content"])
            else:
                contents.append(str(item))

        # Regenerate embeddings
        if contents and self.model:
            try:
                embeddings = []
                for content in contents:
                    embedding = await self.model.embed(content)
                    embeddings.append(embedding)

                # Rebuild index
                await self._build_index(embeddings)

            except Exception as e:
                _ = e  # remove this after implementing observability
                self.has_vector_search = False
