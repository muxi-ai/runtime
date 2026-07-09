# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Reasoning RAG Package - Tree-Based Knowledge Retrieval
# Description:  Hierarchical tree indexing + LLM tree-search retrieval for
#               large knowledge documents (PRD: knowledge-reasoning-rag.md)
# Role:         Alternative retrieval path to vector similarity search,
#               gated per file by a configurable token threshold
# Usage:        Consumed by KnowledgeHandler (ingestion + query dispatch)
# Author:       Muxi Framework Team
#
# Phase 1 ships Method A (pure LLM tree search). Later phases add, beside
# these modules: tree_search_b.py (value-based scoring), tree_search_hybrid.py
# (A+B + sufficiency evaluator), and scoring_service.py (shared with Memory
# Revamp Layer 3).
# =============================================================================

from .tree_builder import TreeBuilder, count_tokens, load_document_text
from .tree_cache import TreeCache
from .tree_search_a import TreeSearchA
from .types import (
    DEFAULT_REASONING_THRESHOLD,
    DEFAULT_TREE_SETTINGS,
    RESERVED_RETRIEVAL_MODES,
    SUPPORTED_RETRIEVAL_MODES,
    RetrievalResult,
    TreeBuildError,
    TreeIndex,
    TreeNavigationError,
    TreeNode,
)

__all__ = [
    "DEFAULT_REASONING_THRESHOLD",
    "DEFAULT_TREE_SETTINGS",
    "RESERVED_RETRIEVAL_MODES",
    "SUPPORTED_RETRIEVAL_MODES",
    "RetrievalResult",
    "TreeBuildError",
    "TreeBuilder",
    "TreeCache",
    "TreeIndex",
    "TreeNavigationError",
    "TreeNode",
    "TreeSearchA",
    "count_tokens",
    "load_document_text",
]
