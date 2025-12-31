"""
Document Chunking Pipeline Implementation

This module implements intelligent document chunking with multiple adaptive strategies
for optimal text processing and semantic search performance.

Supports:
- Adaptive chunking based on content analysis
- Semantic boundary-aware chunking
- Fixed-size chunking with overlap
- Paragraph-based chunking for articles
"""

import hashlib
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from ...config.document_processing import DocumentProcessingConfig
from ....services import observability

import nltk
from nltk.tokenize import sent_tokenize
import spacy


@dataclass
class DocumentChunk:
    """Represents a chunk of document content with metadata"""

    content: str
    chunk_id: str
    document_id: str
    start_pos: int
    end_pos: int
    metadata: Dict[str, Any]

    def __post_init__(self):
        """Validate chunk data after initialization"""
        if not self.content.strip():
            raise ValueError("Chunk content cannot be empty")
        if self.start_pos < 0 or self.end_pos <= self.start_pos:
            raise ValueError(f"Invalid chunk positions: start={self.start_pos}, end={self.end_pos}")


class DocumentChunkManager:
    """
    Intelligent document chunking for large files with adaptive strategies.

    Provides multiple chunking strategies optimized for different content types:
    - Adaptive: Intelligent strategy selection based on content analysis
    - Semantic: Boundary-aware chunking using NLP techniques
    - Fixed: Size-based chunking with configurable overlap
    - Paragraph: Article-style paragraph-based chunking
    """

    def __init__(
        self,
        document_config: Optional[DocumentProcessingConfig] = None,
    ):
        """
        Initialize the document chunk manager.

        Args:
            document_config: DocumentProcessingConfig object with chunking parameters
        """
        # Use document processing configuration if provided, otherwise use defaults
        if document_config is not None:
            self.document_config = document_config
        else:
            # Use default values
            self.document_config = DocumentProcessingConfig({})

        self.default_chunk_size = self.document_config.get_chunk_size()
        self.chunk_overlap = self.document_config.get_chunk_overlap()

        # Additional chunking parameters with sensible defaults
        self.max_chunk_size = self.default_chunk_size * 2
        self.min_chunk_size = max(100, self.default_chunk_size // 10)
        self.semantic_threshold = 0.8

        # Initialize NLP models if available
        self._nlp_model = None
        try:
            # Use configured spacy model if available
            model_name = (
                self.document_config.get_spacy_model() if self.document_config else "en_core_web_sm"
            )
            # Try to load spacy model with a timeout
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(spacy.load, model_name)
                try:
                    self._nlp_model = future.result(timeout=2.0)
                except concurrent.futures.TimeoutError:
                    observability.observe(
                        event_type=observability.ErrorEvents.WARNING,
                        level=observability.EventLevel.WARNING,
                        data={"model": model_name, "reason": "timeout"},
                        description=f"Timeout loading spacy model '{model_name}' - using basic processing",
                    )
                    self._nlp_model = None
        except (OSError, ImportError) as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={"model": model_name, "error": str(e)},
                description=f"spaCy model '{model_name}' not found - falling back to basic processing",
            )
            self._nlp_model = None

        # Ensure NLTK data is available
        try:
            nltk.data.find("tokenizers/punkt")
        except LookupError:
            nltk.download("punkt", quiet=True)

    async def chunk_document(
        self,
        content: str,
        filename: str,
        strategy: str = "adaptive",
        document_id: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """
        Chunk document using specified strategy.

        Args:
            content: Document content to chunk
            filename: Original filename for strategy determination
            strategy: Chunking strategy ("adaptive", "semantic", "fixed", "paragraph")
            document_id: Optional document ID for chunk references

        Returns:
            List of DocumentChunk objects
        """
        if not content.strip():
            raise ValueError("Cannot chunk empty content")

        # Generate document ID if not provided
        if document_id is None:
            document_id = self._generate_document_id(filename)

        # Select chunking strategy
        if strategy == "adaptive":
            strategy = self._determine_chunk_strategy(content, filename)

        # Execute chunking based on strategy
        if strategy == "semantic":
            chunks = await self._semantic_chunking(content)
        elif strategy == "paragraph":
            chunks = await self._paragraph_chunking(content)
        elif strategy == "fixed":
            chunks = await self._fixed_chunking(content)
        else:
            chunks = await self._adaptive_chunking(content)

        # Convert to DocumentChunk objects
        document_chunks = []
        current_pos = 0

        for i, chunk_content in enumerate(chunks):
            # For chunking methods that return modified content, we need to estimate positions
            # If we can't find the exact chunk in the original content, use sequential positions
            start_pos = content.find(chunk_content, current_pos)

            if start_pos == -1:
                # Chunk not found in original content (likely modified by chunking process)
                # Use estimated sequential positions instead
                start_pos = current_pos
                end_pos = min(start_pos + len(chunk_content), len(content))
            else:
                # Chunk found, use actual positions
                end_pos = start_pos + len(chunk_content)
                current_pos = end_pos

            chunk = DocumentChunk(
                content=chunk_content,
                chunk_id=f"{document_id}_chunk_{i:04d}",
                document_id=document_id,
                start_pos=start_pos,
                end_pos=end_pos,
                metadata={
                    "filename": filename,
                    "strategy": strategy,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "word_count": len(chunk_content.split()),
                    "char_count": len(chunk_content),
                },
            )
            document_chunks.append(chunk)

        return document_chunks

    def _determine_chunk_strategy(self, content: str, filename: str) -> str:
        """
        Determine optimal chunking strategy based on content analysis.

        Args:
            content: Document content to analyze
            filename: Filename for format hints

        Returns:
            Recommended chunking strategy
        """
        # File extension hints
        ext = filename.lower().split(".")[-1] if "." in filename else ""

        # Analyze content characteristics
        lines = content.split("\n")
        avg_line_length = sum(len(line) for line in lines) / max(len(lines), 1)
        paragraph_count = len([line for line in lines if line.strip() and not line.startswith(" ")])

        # Decision logic
        if ext in ["md", "txt", "rst"] and paragraph_count > 3:
            return "paragraph"
        elif avg_line_length > 100 and paragraph_count > 5:
            return "semantic"
        elif len(content) > 5000:
            return "semantic"
        else:
            return "fixed"

    async def _semantic_chunking(self, content: str) -> List[str]:
        """Use NLP libraries for intelligent sentence-aware chunking"""
        if self._nlp_model is not None:
            return await self._spacy_semantic_chunking(content)
        else:
            # Fallback to NLTK sentence tokenization
            return await self._nltk_semantic_chunking(content)

    async def _spacy_semantic_chunking(self, content: str) -> List[str]:
        """Use spaCy for advanced semantic chunking"""
        doc = self._nlp_model(content)
        sentences = [sent.text for sent in doc.sents]

        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence)

            if current_size + sentence_size > self.default_chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_size = sentence_size
            else:
                current_chunk.append(sentence)
                current_size += sentence_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    async def _nltk_semantic_chunking(self, content: str) -> List[str]:
        """Use NLTK for sentence-aware chunking"""
        sentences = sent_tokenize(content)

        chunks = []
        current_chunk = []
        current_size = 0

        for sentence in sentences:
            sentence_size = len(sentence)

            if current_size + sentence_size > self.default_chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_size = sentence_size
            else:
                current_chunk.append(sentence)
                current_size += sentence_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    async def _adaptive_chunking(self, content: str) -> List[str]:
        """
        Size-adaptive chunking with overlap for optimal context preservation.

        Args:
            content: Text content to chunk

        Returns:
            List of text chunks with adaptive sizing
        """
        chunks = []
        start = 0
        content_length = len(content)

        while start < content_length:
            # Calculate dynamic chunk size based on remaining content
            remaining = content_length - start
            chunk_size = min(self.default_chunk_size, remaining)

            # Adjust chunk size to avoid breaking words
            end = start + chunk_size
            if end < content_length and not content[end].isspace():
                # Find the nearest word boundary
                while end > start and not content[end].isspace():
                    end -= 1
                if end == start:  # No space found, use original boundary
                    end = start + chunk_size

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start position with overlap
            start = max(start + 1, end - self.chunk_overlap)

        return chunks if chunks else [content]

    async def _paragraph_chunking(self, content: str) -> List[str]:
        """
        Paragraph-based chunking for articles and structured documents.

        Args:
            content: Text content to chunk

        Returns:
            List of paragraph-based chunks
        """
        # Split by double newlines (paragraph breaks)
        paragraphs = re.split(r"\n\s*\n", content)
        chunks = []
        current_chunk = []
        current_size = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            paragraph_size = len(paragraph)

            # If paragraph itself is too large, split it
            if paragraph_size > self.max_chunk_size:
                # Add current chunk if exists
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0

                # Split large paragraph using adaptive chunking
                para_chunks = await self._adaptive_chunking(paragraph)
                chunks.extend(para_chunks)
                continue

            # Check if adding this paragraph exceeds chunk size
            if current_size + paragraph_size > self.default_chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [paragraph]
                current_size = paragraph_size
            else:
                current_chunk.append(paragraph)
                current_size += paragraph_size

        # Add final chunk
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks if chunks else [content]

    async def _fixed_chunking(self, content: str) -> List[str]:
        """
        Fixed-size chunking with configurable overlap.

        Args:
            content: Text content to chunk

        Returns:
            List of fixed-size text chunks
        """
        chunks = []
        start = 0
        content_length = len(content)

        while start < content_length:
            end = min(start + self.default_chunk_size, content_length)

            # Adjust to word boundaries if not at end
            if end < content_length and not content[end].isspace():
                while end > start and not content[end].isspace():
                    end -= 1
                if end == start:
                    end = start + self.default_chunk_size

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # If we've processed a chunk, move to next position
            if end >= content_length:
                break

            start = end - self.chunk_overlap
            if start <= 0 or start >= end:
                start = end

        return chunks if chunks else [content]

    def _generate_document_id(self, filename: str) -> str:
        """Generate a unique document ID from filename"""
        # Create unique ID from filename and timestamp
        timestamp = str(int(time.time() * 1000))
        content = f"{filename}_{timestamp}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def get_chunk_stats(self, chunks: List[DocumentChunk]) -> Dict[str, Any]:
        """
        Get statistics about a set of chunks.

        Args:
            chunks: List of DocumentChunk objects

        Returns:
            Dictionary with chunk statistics
        """
        if not chunks:
            return {"total_chunks": 0}

        chunk_sizes = [len(chunk.content) for chunk in chunks]
        word_counts = [chunk.metadata.get("word_count", 0) for chunk in chunks]

        return {
            "total_chunks": len(chunks),
            "avg_chunk_size": sum(chunk_sizes) / len(chunks),
            "min_chunk_size": min(chunk_sizes),
            "max_chunk_size": max(chunk_sizes),
            "total_words": sum(word_counts),
            "avg_words_per_chunk": sum(word_counts) / len(chunks),
            "strategies_used": list(set(chunk.metadata.get("strategy") for chunk in chunks)),
        }
