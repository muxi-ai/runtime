# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Tree Cache - Disk Persistence for Document Tree Indexes
# Description:  Stores per-document tree indexes and their node->raw KV files
# Role:         Ingestion-side cache so trees are only rebuilt when the
#               source file content changes (MD5-based invalidation)
# Usage:        Used by KnowledgeHandler around TreeBuilder invocations
# Author:       Muxi Framework Team
#
# Cache key: ``(file_path, file_md5)`` -> up to three files in the knowledge
# cache directory (the same directory as the vector embedding caches):
#
#   <path_hash>_<file_md5>.tree.json      - tree JSON (PRD layout, compact)
#   <path_hash>_<file_md5>.tree.kv.jsonl  - line-delimited {node_id, raw}
#   <path_hash>_<file_md5>.tree.emb.jsonl - Method B per-node chunk
#       embeddings: a meta header line {"embedding_model": ...} followed by
#       line-delimited {node_id, vectors}. Only written for sources whose
#       retrieval mode needs Method B (tree-vector / hybrid).
#
# The KV store and embeddings are separate files so the tree JSON can be
# loaded into LLM context without dragging raw content along. Stale entries
# for the same path hash (older MD5s) are removed on save. Corrupt cache
# files are removed and treated as a miss - the cache never raises into the
# caller. Embeddings are invalidated independently when the embedding model
# slug changes (tree + KV survive a model swap; only vectors recompute).
#
# Per-agent (formation-level) trees use the same on-disk layout with a
# different resolver - see agent_trees.py.
# =============================================================================

import glob
import hashlib
import os
from typing import Dict, List, Optional

from .....utils.fastjson import json
from .types import TREE_SCHEMA_VERSION, TreeIndex

_TREE_SUFFIX = ".tree.json"
_KV_SUFFIX = ".tree.kv.jsonl"
_EMB_SUFFIX = ".tree.emb.jsonl"


def write_embeddings_file(path: str, tree: TreeIndex) -> None:
    """Write a tree's chunk embeddings sidecar (meta header + one line/node)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"embedding_model": tree.embedding_model or ""}) + "\n")
        for node_id, vectors in tree.chunk_embeddings.items():
            f.write(json.dumps({"node_id": node_id, "vectors": vectors}) + "\n")


def read_embeddings_file(path: str) -> Optional[Dict[str, object]]:
    """
    Read an embeddings sidecar; returns ``{"model": str, "embeddings": {...}}``
    or None when the file is missing or unreadable (treated as a miss).
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            header = json.loads(f.readline())
            model = str(header.get("embedding_model", ""))
            embeddings: Dict[str, List[List[float]]] = {}
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                embeddings[str(entry["node_id"])] = entry.get("vectors") or []
        return {"model": model, "embeddings": embeddings}
    except Exception:
        return None


class TreeCache:
    """Disk persistence for per-document tree indexes."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path_hash(self, file_path: str) -> str:
        return hashlib.md5(os.path.abspath(file_path).encode("utf-8")).hexdigest()[:16]

    def _base_path(self, file_path: str, file_md5: str) -> str:
        return os.path.join(self.cache_dir, f"{self._path_hash(file_path)}_{file_md5}")

    def load(self, file_path: str, file_md5: str) -> Optional[TreeIndex]:
        """Load a cached tree for ``(file_path, file_md5)`` or return None."""
        base = self._base_path(file_path, file_md5)
        tree_file = base + _TREE_SUFFIX
        kv_file = base + _KV_SUFFIX
        if not (os.path.exists(tree_file) and os.path.exists(kv_file)):
            return None
        try:
            with open(tree_file, "r", encoding="utf-8") as f:
                tree_data = json.loads(f.read())
            if int(tree_data.get("schema_version", 0)) != TREE_SCHEMA_VERSION:
                self._remove_pair(base)
                return None
            kv: Dict[str, str] = {}
            with open(kv_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    kv[str(entry["node_id"])] = entry.get("raw", "")
            tree = TreeIndex.from_json_dict(tree_data, kv=kv)
            emb = read_embeddings_file(base + _EMB_SUFFIX)
            if emb is not None:
                tree.chunk_embeddings = emb["embeddings"]
                tree.embedding_model = emb["model"] or None
            return tree
        except Exception:
            # Corrupt or unreadable cache entry - remove and treat as miss.
            self._remove_pair(base)
            return None

    def save(self, tree: TreeIndex, file_path: str, file_md5: str) -> None:
        """Persist ``tree`` for ``(file_path, file_md5)``; best-effort."""
        self.invalidate(file_path)  # drop stale entries for older MD5s
        base = self._base_path(file_path, file_md5)
        try:
            with open(base + _TREE_SUFFIX, "w", encoding="utf-8") as f:
                f.write(json.dumps(tree.to_json_dict(include_kv=False)))
            with open(base + _KV_SUFFIX, "w", encoding="utf-8") as f:
                for node_id, raw in tree.kv.items():
                    f.write(json.dumps({"node_id": node_id, "raw": raw}) + "\n")
            if tree.chunk_embeddings:
                write_embeddings_file(base + _EMB_SUFFIX, tree)
        except OSError:
            # Cache write failure must not fail ingestion; drop partials.
            self._remove_pair(base)

    def save_embeddings(self, tree: TreeIndex, file_path: str, file_md5: str) -> None:
        """
        Persist only the embeddings sidecar for an already-cached tree.

        Used when Method B embeddings are computed for a tree that was
        loaded from the cache (e.g. the source's retrieval mode changed
        from ``tree`` to ``tree-vector``/``hybrid``, or the embedding model
        changed); best-effort like :meth:`save`.
        """
        base = self._base_path(file_path, file_md5)
        if not tree.chunk_embeddings:
            return
        try:
            write_embeddings_file(base + _EMB_SUFFIX, tree)
        except OSError:
            try:
                os.remove(base + _EMB_SUFFIX)
            except OSError:
                pass

    def invalidate(self, file_path: str) -> int:
        """Remove all cached tree entries for ``file_path`` (any MD5)."""
        pattern = os.path.join(self.cache_dir, f"{self._path_hash(file_path)}_*")
        removed = 0
        stale_files = (
            glob.glob(pattern + _TREE_SUFFIX)
            + glob.glob(pattern + _KV_SUFFIX)
            + glob.glob(pattern + _EMB_SUFFIX)
        )
        for stale in stale_files:
            try:
                os.remove(stale)
                removed += 1
            except OSError:
                pass
        return removed

    def _remove_pair(self, base: str) -> None:
        for path in (base + _TREE_SUFFIX, base + _KV_SUFFIX, base + _EMB_SUFFIX):
            try:
                os.remove(path)
            except OSError:
                pass
