"""
Document Storage Foundation Layer for Enhanced Overlord Intelligence System

This module implements Subtask 3.7 of the Enhanced Overlord Intelligence System,
providing comprehensive document storage with temporal scope and semantic search
capabilities leveraging FAISS/FAISSx infrastructure.

Core Components:
- DocumentAwareBufferMemory: Extended buffer memory with document processing
- DocumentChunkManager: Intelligent document chunking with adaptive strategies
- DocumentMetadataStore: Document metadata tracking and management

- DocumentReferenceSystem: Cross-document reference management

Integration:
- Extends existing WorkingMemory for seamless integration
- Leverages FAISS/FAISSx for high-performance semantic search
- Maintains document lifecycle with FIFO eviction strategies
- Supports multiple chunking strategies (adaptive, semantic, fixed)
"""

from .buffer_memory import DocumentAwareBufferMemory
from .chunk_manager import DocumentChunkManager, DocumentChunk
from .metadata_store import DocumentMetadataStore

from .reference_system import DocumentReferenceSystem

__all__ = [
    "DocumentAwareBufferMemory",
    "DocumentChunkManager",
    "DocumentChunk",
    "DocumentMetadataStore",

    "DocumentReferenceSystem",
]
