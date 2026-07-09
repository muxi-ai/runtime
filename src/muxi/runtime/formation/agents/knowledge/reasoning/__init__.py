# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Reasoning RAG Package - Tree-Based Knowledge Retrieval
# Description:  Hierarchical tree indexing + reasoning/scoring retrieval for
#               large knowledge documents (PRD: knowledge-reasoning-rag.md)
# Role:         Alternative retrieval path to vector similarity search,
#               gated per file by a configurable token threshold or opted
#               into per source (retrieval: tree | tree-vector | hybrid)
# Usage:        Consumed by KnowledgeHandler (ingestion + query dispatch)
# Author:       Muxi Framework Team
#
# Modules: tree_builder (LLM tree generation), tree_cache (per-document disk
# persistence), tree_search_a (Method A: pure LLM navigation), tree_search_b
# (Method B: value-based scoring over per-node chunk embeddings),
# tree_search_hybrid (parallel A+B + sufficiency evaluator), scoring_service
# (standalone scoring primitive shared with Memory Revamp Layer 3), and
# agent_trees (per-agent formation-directory persistent trees).
# =============================================================================

from .agent_trees import AgentTreeStore, compute_source_md5, source_id_for
from .scoring_service import EmbeddingVec, ScoringService
from .tree_builder import TreeBuilder, count_tokens, load_document_text
from .tree_cache import TreeCache
from .tree_search_a import TreeSearchA
from .tree_search_b import TreeSearchB, build_node_chunk_embeddings, split_text_for_scoring
from .tree_search_hybrid import SufficiencyEvaluator, SufficiencyVerdict, TreeSearchHybrid
from .types import (
    AGENT_TREE_REGENERATE_MODES,
    DEFAULT_REASONING_THRESHOLD,
    DEFAULT_TREE_SETTINGS,
    EMBEDDING_RETRIEVAL_MODES,
    RESERVED_RETRIEVAL_MODES,
    SUPPORTED_RETRIEVAL_MODES,
    TREE_RETRIEVAL_MODES,
    RetrievalResult,
    TreeBuildError,
    TreeIndex,
    TreeNavigationError,
    TreeNode,
)

__all__ = [
    "AGENT_TREE_REGENERATE_MODES",
    "AgentTreeStore",
    "DEFAULT_REASONING_THRESHOLD",
    "DEFAULT_TREE_SETTINGS",
    "EMBEDDING_RETRIEVAL_MODES",
    "EmbeddingVec",
    "RESERVED_RETRIEVAL_MODES",
    "RetrievalResult",
    "SUPPORTED_RETRIEVAL_MODES",
    "ScoringService",
    "SufficiencyEvaluator",
    "SufficiencyVerdict",
    "TREE_RETRIEVAL_MODES",
    "TreeBuildError",
    "TreeBuilder",
    "TreeCache",
    "TreeIndex",
    "TreeNavigationError",
    "TreeNode",
    "TreeSearchA",
    "TreeSearchB",
    "TreeSearchHybrid",
    "build_node_chunk_embeddings",
    "compute_source_md5",
    "count_tokens",
    "load_document_text",
    "source_id_for",
    "split_text_for_scoring",
]
