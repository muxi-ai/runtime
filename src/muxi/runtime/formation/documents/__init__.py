"""
Document processing components for MUXI formations.

This module provides document processing capabilities with clear separation between:
- Recommended components for agent knowledge systems (storage module)
- Deprecated workflow components (workflow module - use with caution)

For agent knowledge systems, use:
- DocumentChunkManager: Efficient document chunking and processing
- DocumentSemanticIndex: Vector-based semantic search and indexing
"""

from .experience import __all__ as experience_all
from .storage import __all__ as storage_all
from .storage import DocumentChunkManager, DocumentSemanticIndex

# Import deprecated workflow components (with warnings when used)
from .workflow import __all__ as workflow_all

# Recommended exports for agent knowledge systems
__agent_knowledge_exports__ = [
    "DocumentChunkManager",
    "DocumentSemanticIndex"
]

# All exports (including deprecated workflow components)
__all__ = __agent_knowledge_exports__ + experience_all + storage_all + workflow_all
