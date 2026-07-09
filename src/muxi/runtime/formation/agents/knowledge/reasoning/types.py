# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Reasoning RAG Types - Tree Index Data Structures
# Description:  Shared datatypes for reasoning-based (tree) knowledge retrieval
# Role:         Defines the tree index schema, retrieval result contract, and
#               configuration defaults used by the reasoning retrieval modes
# Usage:        Consumed by TreeBuilder, TreeCache, TreeSearchA, and the
#               KnowledgeHandler integration points
# Author:       Muxi Framework Team
#
# This module defines the data structures for MUXI's reasoning-based RAG
# (see engineering/prds/knowledge-reasoning-rag.md):
#
# - TreeNode / TreeIndex: the hierarchical tree index built per document at
#   ingestion time. The tree itself stays compact (titles, summaries, IDs,
#   index ranges only) so it fits into a single LLM call; raw node content
#   lives in a separate KV mapping and is fetched only for selected nodes.
# - RetrievalResult: the unified retrieval result schema shared across
#   retrieval modes (vector, tree, and - in later phases - agent_tree, kg,
#   captains_log, artifact). Committed contract with memory-revamp.md.
# - Config defaults for the ``knowledge.reasoning_threshold`` and
#   ``knowledge.tree.*`` settings.
#
# Phase 1 implements Method A (pure LLM tree search) only. Method B
# (value-based scoring), hybrid mode, and per-agent formation-level trees
# are later phases; the ``scope`` field and the mode vocabulary below leave
# the seams they need.
# =============================================================================

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

# Current tree JSON schema version. Bump when the on-disk layout changes.
TREE_SCHEMA_VERSION = 1

# Default token threshold above which a knowledge file is tree-indexed
# instead of vector-indexed. ``0`` disables reasoning-based indexing.
DEFAULT_REASONING_THRESHOLD = 40000

# Defaults for the ``knowledge.tree`` settings block (PRD "Configuration").
DEFAULT_TREE_SETTINGS: Dict[str, Any] = {
    "model": None,  # null = use the agent's text model
    "max_depth": 3,
    "max_pages_per_node": 10,
    "max_tokens_per_node": 20000,
    "max_document_tokens": 500000,  # above this: fall back to vector
}

# Retrieval modes recognized by the per-source ``retrieval:`` field.
# Phase 1 supports "vector" and "tree"; "tree-vector" (Method B) and
# "hybrid" (A+B+terminator) are reserved for later phases and rejected
# by config validation until they ship.
SUPPORTED_RETRIEVAL_MODES = ("vector", "tree")
RESERVED_RETRIEVAL_MODES = ("tree-vector", "hybrid")


class TreeBuildError(Exception):
    """Raised when tree index construction fails (LLM error, bad output)."""


class TreeNavigationError(Exception):
    """Raised when Method A tree navigation fails at query time."""


@dataclass
class RetrievalResult:
    """
    Unified retrieval result schema (cross-PRD contract with memory-revamp).

    ``source_type`` is one of "vector", "tree", "agent_tree", "kg",
    "captains_log", or "artifact". Phase 1 emits "tree" results; the
    KnowledgeHandler converts them to its legacy dict shape via
    :meth:`to_dict` so downstream consumers (``search_unified``,
    ``_inject_knowledge_into_memory``) stay unchanged.
    """

    source_type: str
    content: str
    relevance: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    node_path: Optional[List[str]] = None  # tree breadcrumb (root -> node)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to the KnowledgeHandler legacy result dict shape."""
        metadata = {**self.metadata, "source_type": self.source_type}
        if self.node_path is not None:
            metadata["node_path"] = self.node_path
        return {
            "content": self.content,
            "relevance": self.relevance,
            "metadata": metadata,
        }


@dataclass
class TreeNode:
    """A single node in a document tree index (compact: no raw content)."""

    node_id: str
    title: str
    summary: str = ""
    start_index: int = 0  # char offset for unpaginated text, page for paginated
    end_index: int = 0
    sub_nodes: List["TreeNode"] = field(default_factory=list)

    def to_json_dict(self) -> Dict[str, Any]:
        """Serialize to the PRD tree JSON layout."""
        data: Dict[str, Any] = {
            "node_id": self.node_id,
            "title": self.title,
            "summary": self.summary,
            "start_index": self.start_index,
            "end_index": self.end_index,
        }
        if self.sub_nodes:
            data["sub_nodes"] = [child.to_json_dict() for child in self.sub_nodes]
        return data

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> "TreeNode":
        """Deserialize from the PRD tree JSON layout."""
        return cls(
            node_id=str(data["node_id"]),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            start_index=int(data.get("start_index", 0)),
            end_index=int(data.get("end_index", 0)),
            sub_nodes=[cls.from_json_dict(child) for child in data.get("sub_nodes", [])],
        )


@dataclass
class TreeIndex:
    """
    A hierarchical tree index for one document plus its node->raw KV mapping.

    The tree (titles + summaries only) is what gets injected into the
    Method A navigation prompt; ``kv`` holds each node's raw content and is
    only consulted for selected node_ids. On disk the two are separate files
    (``<key>.tree.json`` and ``<key>.tree.kv.jsonl``) so the tree JSON can be
    loaded into LLM context without dragging raw content along.
    """

    document: str
    root: TreeNode
    token_count: int = 0
    tree_token_count: int = 0
    scope: str = "document"  # "document" now; "agent" in a later phase
    schema_version: int = TREE_SCHEMA_VERSION
    kv: Dict[str, str] = field(default_factory=dict)
    # Lazy id->node and child_id->parent_id lookup maps so the query hot
    # path (get_node / node_path per selected node id) never re-traverses
    # the tree. Built once on first use; trees are immutable after
    # construction (the builder fills summaries in place on the same node
    # objects the maps reference, so mutation-by-summary is safe).
    _node_map: Optional[Dict[str, TreeNode]] = field(
        default=None, init=False, repr=False, compare=False
    )
    _parent_map: Optional[Dict[str, str]] = field(
        default=None, init=False, repr=False, compare=False
    )

    def walk(self) -> Iterator[TreeNode]:
        """Yield all nodes in pre-order (root first)."""
        stack = deque([self.root])
        while stack:
            node = stack.popleft()
            yield node
            # Prepend children (in order) so traversal stays depth-first
            # pre-order: extendleft reverses, hence the reversed() input.
            stack.extendleft(reversed(node.sub_nodes))

    def _ensure_maps(self) -> Dict[str, "TreeNode"]:
        if self._node_map is None:
            node_map: Dict[str, TreeNode] = {}
            parent_map: Dict[str, str] = {}
            for node in self.walk():
                node_map[node.node_id] = node
                for child in node.sub_nodes:
                    parent_map[child.node_id] = node.node_id
            self._node_map = node_map
            self._parent_map = parent_map
        return self._node_map

    @property
    def node_count(self) -> int:
        return len(self._ensure_maps())

    def get_node(self, node_id: str) -> Optional[TreeNode]:
        return self._ensure_maps().get(node_id)

    def node_path(self, node_id: str) -> List[str]:
        """Return the title breadcrumb from the root to ``node_id``."""
        node_map = self._ensure_maps()
        if node_id not in node_map:
            return []
        titles: List[str] = []
        current: Optional[str] = node_id
        while current is not None:
            titles.append(node_map[current].title)
            current = self._parent_map.get(current)
        return list(reversed(titles))

    def fetch_raw(self, node_id: str) -> str:
        """Fetch the raw content for a node from the KV mapping."""
        return self.kv.get(node_id, "")

    def compressed_json(self) -> str:
        """Compact JSON of the tree only (no raw content) for LLM prompts."""
        from .....utils.fastjson import json

        return json.dumps(self.to_json_dict(include_kv=False))

    def to_json_dict(self, include_kv: bool = False) -> Dict[str, Any]:
        """Serialize the index metadata + tree (PRD JSON layout)."""
        data: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "document": self.document,
            "token_count": self.token_count,
            "tree_token_count": self.tree_token_count,
            "tree": self.root.to_json_dict(),
        }
        if include_kv:
            data["kv"] = dict(self.kv)
        return data

    @classmethod
    def from_json_dict(
        cls, data: Dict[str, Any], kv: Optional[Dict[str, str]] = None
    ) -> "TreeIndex":
        """Deserialize from the PRD JSON layout (KV supplied separately)."""
        return cls(
            document=data.get("document", ""),
            root=TreeNode.from_json_dict(data["tree"]),
            token_count=int(data.get("token_count", 0)),
            tree_token_count=int(data.get("tree_token_count", 0)),
            scope=data.get("scope", "document"),
            schema_version=int(data.get("schema_version", TREE_SCHEMA_VERSION)),
            kv=kv or data.get("kv", {}) or {},
        )
