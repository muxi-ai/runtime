"""
Knowledge Graph memory layer (Memory Revamp Phase 1).

Structured entities and relationships extracted from conversations, stored
alongside the existing flat-fact collections. See the module frontmatter in
models.py / storage.py / algorithms.py / service.py for the architecture.
"""

from .algorithms import GraphAlgorithms, NetworkXAlgorithms, PgRoutingAlgorithms
from .extractor import KnowledgeGraphExtractor
from .models import ENTITY_TYPES, RELATIONSHIP_TYPES, KGEntity, KGRelationship
from .service import KnowledgeGraphService
from .storage import KnowledgeGraphStorage

__all__ = [
    "ENTITY_TYPES",
    "RELATIONSHIP_TYPES",
    "GraphAlgorithms",
    "KGEntity",
    "KGRelationship",
    "KnowledgeGraphExtractor",
    "KnowledgeGraphService",
    "KnowledgeGraphStorage",
    "NetworkXAlgorithms",
    "PgRoutingAlgorithms",
]
