"""
Document Metadata Store Implementation

This module implements comprehensive document metadata tracking and management
for the document storage foundation layer.

Features:
- Document lifecycle tracking
- Metadata persistence and retrieval
- Document relationship management
- Query and filtering capabilities
"""

import time
import json
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path

from ....services import observability


@dataclass
class DocumentMetadata:
    """Document metadata structure"""

    document_id: str
    filename: str
    original_path: Optional[str]
    file_size: int
    mime_type: Optional[str]
    upload_timestamp: float
    processing_timestamp: Optional[float]
    chunk_count: int
    total_word_count: int
    chunk_strategy: str
    user_id: Optional[int]
    tags: List[str]
    custom_metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentMetadata":
        """Create metadata from dictionary"""
        return cls(**data)


class DocumentMetadataStore:
    """
    Document metadata tracking and management system.

    Provides comprehensive metadata storage with persistence, querying,
    and relationship management for documents in the overlord system.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the document metadata store.

        Args:
            storage_path: Optional path for metadata persistence file
        """
        self.storage_path = storage_path or ".muxi/document_metadata.json"
        self._metadata_cache: Dict[str, DocumentMetadata] = {}
        self._filename_index: Dict[str, List[str]] = {}  # filename -> [doc_ids]
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> {doc_ids}
        self._user_index: Dict[int, Set[str]] = {}  # user_id -> {doc_ids}

        # Ensure storage directory exists
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)

        # Load existing metadata
        self._load_metadata()

    async def store_document_metadata(
        self,
        document_id: str,
        filename: str,
        file_size: int,
        chunk_count: int,
        total_word_count: int,
        chunk_strategy: str,
        user_id: Optional[int] = None,
        original_path: Optional[str] = None,
        mime_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentMetadata:
        """
        Store document metadata.

        Args:
            document_id: Unique document identifier
            filename: Original filename
            file_size: File size in bytes
            chunk_count: Number of chunks created
            total_word_count: Total word count in document
            chunk_strategy: Chunking strategy used
            user_id: Optional user ID who uploaded the document
            original_path: Optional original file path
            mime_type: Optional MIME type
            tags: Optional list of tags
            custom_metadata: Optional custom metadata dictionary

        Returns:
            DocumentMetadata object
        """
        current_time = time.time()

        metadata = DocumentMetadata(
            document_id=document_id,
            filename=filename,
            original_path=original_path,
            file_size=file_size,
            mime_type=mime_type,
            upload_timestamp=current_time,
            processing_timestamp=current_time,
            chunk_count=chunk_count,
            total_word_count=total_word_count,
            chunk_strategy=chunk_strategy,
            user_id=user_id,
            tags=tags or [],
            custom_metadata=custom_metadata or {},
        )

        # Store in cache
        self._metadata_cache[document_id] = metadata

        # Update indexes
        self._update_indexes(metadata)

        # Persist to storage
        await self._persist_metadata()

        return metadata

    async def get_document_metadata(self, document_id: str) -> Optional[DocumentMetadata]:
        """
        Retrieve document metadata by ID.

        Args:
            document_id: Document identifier

        Returns:
            DocumentMetadata object or None if not found
        """
        return self._metadata_cache.get(document_id)

    async def get_documents_by_filename(self, filename: str) -> List[DocumentMetadata]:
        """
        Get all documents with the specified filename.

        Args:
            filename: Filename to search for

        Returns:
            List of DocumentMetadata objects
        """
        doc_ids = self._filename_index.get(filename, [])
        return [
            self._metadata_cache[doc_id] for doc_id in doc_ids if doc_id in self._metadata_cache
        ]

    async def get_documents_by_user(self, user_id: int) -> List[DocumentMetadata]:
        """
        Get all documents uploaded by a specific user.

        Args:
            user_id: User identifier

        Returns:
            List of DocumentMetadata objects
        """
        doc_ids = self._user_index.get(user_id, set())
        return [
            self._metadata_cache[doc_id] for doc_id in doc_ids if doc_id in self._metadata_cache
        ]

    async def get_documents_by_tag(self, tag: str) -> List[DocumentMetadata]:
        """
        Get all documents with the specified tag.

        Args:
            tag: Tag to search for

        Returns:
            List of DocumentMetadata objects
        """
        doc_ids = self._tag_index.get(tag, set())
        return [
            self._metadata_cache[doc_id] for doc_id in doc_ids if doc_id in self._metadata_cache
        ]

    async def search_documents(
        self,
        filename_pattern: Optional[str] = None,
        user_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        mime_type: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        since_timestamp: Optional[float] = None,
        custom_filters: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentMetadata]:
        """
        Search documents by multiple criteria.

        Args:
            filename_pattern: Optional filename pattern (supports wildcards)
            user_id: Optional user ID filter
            tags: Optional list of tags (document must have all tags)
            mime_type: Optional MIME type filter
            min_size: Optional minimum file size
            max_size: Optional maximum file size
            since_timestamp: Optional timestamp filter (documents since this time)
            custom_filters: Optional custom metadata filters

        Returns:
            List of matching DocumentMetadata objects
        """
        results = []

        for metadata in self._metadata_cache.values():
            # Apply filters
            if filename_pattern and not self._match_pattern(metadata.filename, filename_pattern):
                continue

            if user_id is not None and metadata.user_id != user_id:
                continue

            if tags and not all(tag in metadata.tags for tag in tags):
                continue

            if mime_type and metadata.mime_type != mime_type:
                continue

            if min_size is not None and metadata.file_size < min_size:
                continue

            if max_size is not None and metadata.file_size > max_size:
                continue

            if since_timestamp and metadata.upload_timestamp < since_timestamp:
                continue

            if custom_filters:
                if not self._match_custom_filters(metadata.custom_metadata, custom_filters):
                    continue

            results.append(metadata)

        return results

    async def update_document_metadata(
        self,
        document_id: str,
        tags: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update document metadata.

        Args:
            document_id: Document identifier
            tags: Optional new tags list
            custom_metadata: Optional custom metadata to update

        Returns:
            True if update successful, False if document not found
        """
        metadata = self._metadata_cache.get(document_id)
        if not metadata:
            return False

        # Remove from old indexes
        self._remove_from_indexes(metadata)

        # Update metadata
        if tags is not None:
            metadata.tags = tags

        if custom_metadata is not None:
            metadata.custom_metadata.update(custom_metadata)

        # Update indexes
        self._update_indexes(metadata)

        # Persist changes
        await self._persist_metadata()

        return True

    async def delete_document_metadata(self, document_id: str) -> bool:
        """
        Delete document metadata.

        Args:
            document_id: Document identifier

        Returns:
            True if deletion successful, False if document not found
        """
        metadata = self._metadata_cache.get(document_id)
        if not metadata:
            return False

        # Remove from indexes
        self._remove_from_indexes(metadata)

        # Remove from cache
        del self._metadata_cache[document_id]

        # Persist changes
        await self._persist_metadata()

        return True

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage statistics
        """
        if not self._metadata_cache:
            return {"total_documents": 0, "total_size": 0, "total_chunks": 0, "total_words": 0}

        total_size = sum(meta.file_size for meta in self._metadata_cache.values())
        total_chunks = sum(meta.chunk_count for meta in self._metadata_cache.values())
        total_words = sum(meta.total_word_count for meta in self._metadata_cache.values())

        # Get user statistics
        user_counts = {}
        for metadata in self._metadata_cache.values():
            if metadata.user_id:
                user_counts[metadata.user_id] = user_counts.get(metadata.user_id, 0) + 1

        # Get tag statistics
        tag_counts = {}
        for metadata in self._metadata_cache.values():
            for tag in metadata.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Get strategy statistics
        strategy_counts = {}
        for metadata in self._metadata_cache.values():
            strategy = metadata.chunk_strategy
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        return {
            "total_documents": len(self._metadata_cache),
            "total_size": total_size,
            "total_chunks": total_chunks,
            "total_words": total_words,
            "avg_chunks_per_doc": total_chunks / len(self._metadata_cache),
            "avg_words_per_doc": total_words / len(self._metadata_cache),
            "users_with_documents": len(user_counts),
            "most_common_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            "strategy_distribution": strategy_counts,
        }

    def _update_indexes(self, metadata: DocumentMetadata) -> None:
        """Update all indexes with new metadata"""
        # Filename index
        if metadata.filename not in self._filename_index:
            self._filename_index[metadata.filename] = []
        if metadata.document_id not in self._filename_index[metadata.filename]:
            self._filename_index[metadata.filename].append(metadata.document_id)

        # Tag index
        for tag in metadata.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(metadata.document_id)

        # User index
        if metadata.user_id is not None:
            if metadata.user_id not in self._user_index:
                self._user_index[metadata.user_id] = set()
            self._user_index[metadata.user_id].add(metadata.document_id)

    def _remove_from_indexes(self, metadata: DocumentMetadata) -> None:
        """Remove metadata from all indexes"""
        # Filename index
        if metadata.filename in self._filename_index:
            if metadata.document_id in self._filename_index[metadata.filename]:
                self._filename_index[metadata.filename].remove(metadata.document_id)
            if not self._filename_index[metadata.filename]:
                del self._filename_index[metadata.filename]

        # Tag index
        for tag in metadata.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(metadata.document_id)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]

        # User index
        if metadata.user_id is not None and metadata.user_id in self._user_index:
            self._user_index[metadata.user_id].discard(metadata.document_id)
            if not self._user_index[metadata.user_id]:
                del self._user_index[metadata.user_id]

    def _match_pattern(self, text: str, pattern: str) -> bool:
        """Simple pattern matching with wildcards"""
        import fnmatch

        return fnmatch.fnmatch(text.lower(), pattern.lower())

    def _match_custom_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if metadata matches custom filters"""
        for key, value in filters.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True

    def _load_metadata(self) -> None:
        """Load metadata from storage file"""
        try:
            if Path(self.storage_path).exists():
                with open(self.storage_path, "r") as f:
                    data = json.load(f)

                # Load metadata objects
                for doc_id, meta_dict in data.get("metadata", {}).items():
                    metadata = DocumentMetadata.from_dict(meta_dict)
                    self._metadata_cache[doc_id] = metadata
                    self._update_indexes(metadata)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "persist_metadata_cache",
                },
                description="Failed to persist metadata cache",
            )

    async def _persist_metadata(self) -> None:
        """Persist metadata to storage file"""
        try:
            # Convert metadata to serializable format
            data = {
                "metadata": {
                    doc_id: metadata.to_dict() for doc_id, metadata in self._metadata_cache.items()
                },
                "indexes": {
                    "filename": dict(self._filename_index),
                    "tags": {tag: list(doc_ids) for tag, doc_ids in self._tag_index.items()},
                    "users": {
                        str(user_id): list(doc_ids) for user_id, doc_ids in self._user_index.items()
                    },
                },
            }

            # Write to temporary file first, then rename for atomic operation
            temp_path = f"{self.storage_path}.tmp"
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            Path(temp_path).rename(self.storage_path)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.METADATA_PERSISTENCE_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "operation": "persist_metadata",
                },
                description="Failed to persist metadata to storage",
            )
