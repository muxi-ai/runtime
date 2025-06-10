"""
Document Semantic Index Implementation

This module implements enhanced FAISS integration for document semantic search,
providing efficient vector similarity search across document collections.

Features:
- Document-specific vector indexing
- Multi-document semantic search
- Document metadata integration
- Index persistence and loading
"""

import numpy as np
import pickle
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

try:
    from faissx.client import FaissXClient
    FAISSX_AVAILABLE = True
except ImportError:
    FAISSX_AVAILABLE = False
    logger.warning("FAISSx not available - falling back to local FAISS")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available - vector search disabled")


@dataclass
class DocumentSearchResult:
    """Document search result with metadata"""
    document_id: str
    chunk_id: str
    content: str
    score: float
    distance: float
    metadata: Dict[str, Any]
    document_metadata: Optional[Dict[str, Any]] = None


class DocumentSemanticIndex:
    """
    Enhanced FAISS integration for document semantic search.

    Provides efficient vector similarity search across document collections
    with support for both local FAISS and remote FAISSx operations.
    """

    def __init__(
        self,
        vector_dimension: int = 1536,
        mode: str = "local",
        remote_config: Optional[Dict[str, Any]] = None,
        index_path: Optional[str] = None,
        persist_index: bool = True
    ):
        """
        Initialize the document semantic index.

        Args:
            vector_dimension: Dimension of embedding vectors
            mode: Index mode ("local" or "remote")
            remote_config: Configuration for remote FAISSx
            index_path: Optional path for index persistence
            persist_index: Whether to persist index to disk
        """
        self.vector_dimension = vector_dimension
        self.mode = mode
        self.persist_index = persist_index
        self.index_path = index_path or ".muxi/document_semantic_index"

        # Index components
        self._faiss_index = None
        self._faissx_client = None
        self._document_vectors: List[np.ndarray] = []
        self._document_metadata: List[Dict[str, Any]] = []
        self._id_to_index: Dict[str, int] = {}  # chunk_id -> index position
        self._index_to_id: Dict[int, str] = {}  # index position -> chunk_id

        # Remote configuration
        self.remote_config = remote_config or {}

        # Initialize index
        self._initialize_index()

        logger.info(f"Initialized DocumentSemanticIndex in {mode} mode")

    def _initialize_index(self) -> None:
        """Initialize the appropriate index type"""
        if self.mode == "remote" and FAISSX_AVAILABLE:
            self._initialize_remote_index()
        elif FAISS_AVAILABLE:
            self._initialize_local_index()
        else:
            logger.error("No vector indexing backend available")
            raise RuntimeError("Neither FAISS nor FAISSx is available")

        # Try to load existing index
        if self.persist_index:
            self._load_index()

    def _initialize_remote_index(self) -> None:
        """Initialize remote FAISSx client"""
        try:
            self._faissx_client = FaissXClient(
                url=self.remote_config.get("url", "tcp://localhost:45678"),
                api_key=self.remote_config.get("api_key"),
                tenant_id=self.remote_config.get("tenant_id")
            )
            logger.info("Initialized remote FAISSx client")
        except Exception as e:
            logger.error(f"Failed to initialize FAISSx client: {e}")
            # Fall back to local FAISS
            self.mode = "local"
            self._initialize_local_index()

    def _initialize_local_index(self) -> None:
        """Initialize local FAISS index"""
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS is not available for local indexing")

        # Create L2 distance index for semantic similarity
        self._faiss_index = faiss.IndexFlatL2(self.vector_dimension)
        logger.info(f"Initialized local FAISS index with dimension {self.vector_dimension}")

    async def add_document_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[np.ndarray],
        document_metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add document chunks with their embeddings to the index.

        Args:
            chunks: List of chunk dictionaries with content and metadata
            embeddings: List of embedding vectors for each chunk
            document_metadata: Optional document-level metadata
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")

        logger.info(f"Adding {len(chunks)} document chunks to semantic index")

        # Prepare vectors and metadata
        vectors = []
        metadata_list = []

        for chunk, embedding in zip(chunks, embeddings):
            # Ensure embedding is properly shaped
            if isinstance(embedding, list):
                embedding = np.array(embedding, dtype=np.float32)
            elif not isinstance(embedding, np.ndarray):
                embedding = np.array(embedding, dtype=np.float32)

            if embedding.shape[0] != self.vector_dimension:
                raise ValueError(
                    f"Embedding dimension {embedding.shape[0]} doesn't match "
                    f"index dimension {self.vector_dimension}"
                )

            vectors.append(embedding)

            # Combine chunk and document metadata
            combined_metadata = {
                **chunk.get("metadata", {}),
                "content": chunk.get("content", ""),
                "chunk_id": chunk.get("chunk_id", ""),
                "document_id": chunk.get("document_id", "")
            }

            if document_metadata:
                combined_metadata["document_metadata"] = document_metadata

            metadata_list.append(combined_metadata)

        # Add to index
        if self.mode == "remote" and self._faissx_client:
            await self._add_to_remote_index(vectors, metadata_list)
        else:
            await self._add_to_local_index(vectors, metadata_list)

        # Persist if enabled
        if self.persist_index:
            await self._save_index()

    async def _add_to_remote_index(
        self, vectors: List[np.ndarray], metadata_list: List[Dict[str, Any]]
    ) -> None:
        """Add vectors to remote FAISSx index"""
        try:
            # Add vectors with metadata
            for i, (vector, metadata) in enumerate(zip(vectors, metadata_list)):
                chunk_id = metadata.get("chunk_id", f"chunk_{int(time.time())}_{i}")

                await self._faissx_client.add_vector(
                    vector_id=chunk_id,
                    vector=vector,
                    metadata=metadata
                )

                # Track locally
                index_pos = len(self._document_vectors)
                self._document_vectors.append(vector)
                self._document_metadata.append(metadata)
                self._id_to_index[chunk_id] = index_pos
                self._index_to_id[index_pos] = chunk_id

            logger.info(f"Added {len(vectors)} vectors to remote FAISSx index")

        except Exception as e:
            logger.error(f"Failed to add vectors to remote index: {e}")
            # Fall back to local index
            await self._add_to_local_index(vectors, metadata_list)

    async def _add_to_local_index(
        self, vectors: List[np.ndarray], metadata_list: List[Dict[str, Any]]
    ) -> None:
        """Add vectors to local FAISS index"""
        # Prepare vector array
        vector_array = np.array(vectors, dtype=np.float32)

        # Add to FAISS index
        self._faiss_index.add(vector_array)

        # Track metadata
        start_index = len(self._document_vectors)
        for i, (vector, metadata) in enumerate(zip(vectors, metadata_list)):
            chunk_id = metadata.get("chunk_id", f"chunk_{int(time.time())}_{i}")
            index_pos = start_index + i

            self._document_vectors.append(vector)
            self._document_metadata.append(metadata)
            self._id_to_index[chunk_id] = index_pos
            self._index_to_id[index_pos] = chunk_id

        logger.info(f"Added {len(vectors)} vectors to local FAISS index")

    async def search_documents(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        document_ids: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[DocumentSearchResult]:
        """
        Search for similar document chunks.

        Args:
            query_vector: Query embedding vector
            k: Number of results to return
            document_ids: Optional filter by document IDs
            metadata_filter: Optional metadata filter

        Returns:
            List of DocumentSearchResult objects
        """
        return await self._search_local(query_vector, k, document_ids, metadata_filter)

    async def _search_local(
        self,
        query_vector: np.ndarray,
        k: int,
        document_ids: Optional[List[str]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[DocumentSearchResult]:
        """Search using local FAISS"""
        if not self._faiss_index or len(self._document_vectors) == 0:
            return []

        # Ensure query vector is properly shaped
        if isinstance(query_vector, list):
            query_vector = np.array(query_vector, dtype=np.float32)

        query_vector = query_vector.reshape(1, -1)

        # Search FAISS index
        search_k = min(k * 3, len(self._document_vectors))  # Get more for filtering
        distances, indices = self._faiss_index.search(query_vector, search_k)

        results = []
        seen_documents = set()

        for i, (distance, index) in enumerate(zip(distances[0], indices[0])):
            if index == -1:  # Invalid index
                continue

            if index >= len(self._document_metadata):
                continue

            metadata = self._document_metadata[index]
            document_id = metadata.get("document_id", "")

            # Apply document ID filter
            if document_ids and document_id not in document_ids:
                continue

            # Apply metadata filter
            if metadata_filter:
                if not self._matches_filter(metadata, metadata_filter):
                    continue

            # Calculate score (higher is better)
            score = 1.0 / (1.0 + float(distance))

            result = DocumentSearchResult(
                document_id=document_id,
                chunk_id=metadata.get("chunk_id", ""),
                content=metadata.get("content", ""),
                score=score,
                distance=float(distance),
                metadata=metadata,
                document_metadata=metadata.get("document_metadata")
            )

            results.append(result)
            seen_documents.add(document_id)

            if len(results) >= k:
                break

        return results

    def _matches_filter(self, metadata: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        """Check if metadata matches the filter criteria"""
        for key, value in filter_dict.items():
            if key not in metadata:
                return False
            if metadata[key] != value:
                return False
        return True

    async def remove_document(self, document_id: str) -> bool:
        """
        Remove all chunks for a document from the index.

        Args:
            document_id: Document identifier

        Returns:
            True if document was removed, False if not found
        """
        logger.info(f"Removing document {document_id} from semantic index")

        # Find all chunks for this document
        chunks_to_remove = []
        for i, metadata in enumerate(self._document_metadata):
            if metadata.get("document_id") == document_id:
                chunks_to_remove.append(i)

        if not chunks_to_remove:
            return False

        # For local FAISS, we need to rebuild the index
        if self.mode == "local":
            await self._rebuild_local_index_without_chunks(chunks_to_remove)
        elif self.mode == "remote" and self._faissx_client:
            await self._remove_from_remote_index(chunks_to_remove)

        logger.info(f"Removed document {document_id} with {len(chunks_to_remove)} chunks")
        return True

    async def _rebuild_local_index_without_chunks(self, indices_to_remove: List[int]) -> None:
        """Rebuild local index without specified chunks"""
        # Create new index
        new_index = faiss.IndexFlatL2(self.vector_dimension)
        new_vectors = []
        new_metadata = []
        new_id_to_index = {}
        new_index_to_id = {}

        # Copy data except for removed indices
        indices_to_remove_set = set(indices_to_remove)
        new_pos = 0

        for old_pos in range(len(self._document_vectors)):
            if old_pos not in indices_to_remove_set:
                vector = self._document_vectors[old_pos]
                metadata = self._document_metadata[old_pos]
                chunk_id = metadata.get("chunk_id", "")

                new_vectors.append(vector)
                new_metadata.append(metadata)
                new_id_to_index[chunk_id] = new_pos
                new_index_to_id[new_pos] = chunk_id
                new_pos += 1

        # Add vectors to new index
        if new_vectors:
            vector_array = np.array(new_vectors, dtype=np.float32)
            new_index.add(vector_array)

        # Replace old index
        self._faiss_index = new_index
        self._document_vectors = new_vectors
        self._document_metadata = new_metadata
        self._id_to_index = new_id_to_index
        self._index_to_id = new_index_to_id

    async def _remove_from_remote_index(self, indices_to_remove: List[int]) -> None:
        """Remove chunks from remote FAISSx index"""
        try:
            for index in indices_to_remove:
                chunk_id = self._index_to_id.get(index)
                if chunk_id:
                    await self._faissx_client.delete_vector(chunk_id)
        except Exception as e:
            logger.error(f"Failed to remove vectors from remote index: {e}")

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the semantic index"""
        total_vectors = len(self._document_vectors)

        if total_vectors == 0:
            return {"total_vectors": 0, "total_documents": 0}

        # Count unique documents
        document_ids = set()
        for metadata in self._document_metadata:
            doc_id = metadata.get("document_id")
            if doc_id:
                document_ids.add(doc_id)

        return {
            "total_vectors": total_vectors,
            "total_documents": len(document_ids),
            "avg_chunks_per_document": total_vectors / max(len(document_ids), 1),
            "vector_dimension": self.vector_dimension,
            "index_mode": self.mode,
            "index_size_mb": self._estimate_index_size()
        }

    def _estimate_index_size(self) -> float:
        """Estimate index size in MB"""
        vector_size = len(self._document_vectors) * self.vector_dimension * 4  # float32
        metadata_size = sum(
            len(str(metadata)) for metadata in self._document_metadata
        )
        return (vector_size + metadata_size) / (1024 * 1024)

    async def _save_index(self) -> None:
        """Save index to disk"""
        if not self.persist_index:
            return

        try:
            Path(self.index_path).parent.mkdir(parents=True, exist_ok=True)

            # Save index data
            index_data = {
                "vectors": self._document_vectors,
                "metadata": self._document_metadata,
                "id_to_index": self._id_to_index,
                "index_to_id": self._index_to_id,
                "vector_dimension": self.vector_dimension,
                "mode": self.mode
            }

            with open(f"{self.index_path}.pkl", "wb") as f:
                pickle.dump(index_data, f)

            # Save FAISS index if local
            if self.mode == "local" and self._faiss_index:
                faiss.write_index(self._faiss_index, f"{self.index_path}.faiss")

            logger.info(f"Saved semantic index to {self.index_path}")

        except Exception as e:
            logger.error(f"Failed to save semantic index: {e}")

    def _load_index(self) -> None:
        """Load index from disk"""
        try:
            pickle_path = f"{self.index_path}.pkl"
            faiss_path = f"{self.index_path}.faiss"

            if not Path(pickle_path).exists():
                return

            # Load index data
            with open(pickle_path, "rb") as f:
                index_data = pickle.load(f)

            self._document_vectors = index_data.get("vectors", [])
            self._document_metadata = index_data.get("metadata", [])
            self._id_to_index = index_data.get("id_to_index", {})
            self._index_to_id = index_data.get("index_to_id", {})

            # Load FAISS index if local mode and file exists
            if self.mode == "local" and Path(faiss_path).exists():
                self._faiss_index = faiss.read_index(faiss_path)

            logger.info(f"Loaded semantic index with {len(self._document_vectors)} vectors")

        except Exception as e:
            logger.error(f"Failed to load semantic index: {e}")
            # Continue with empty index
