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
# Cache key: ``(file_path, file_md5)`` -> two files in the knowledge cache
# directory (the same directory as the vector embedding caches):
#
#   <path_hash>_<file_md5>.tree.json     - tree JSON (PRD layout, compact)
#   <path_hash>_<file_md5>.tree.kv.jsonl - line-delimited {node_id, raw}
#
# The KV store is a separate file so the tree JSON can be loaded into LLM
# context without dragging raw content along. Stale entries for the same
# path hash (older MD5s) are removed on save. Corrupt cache files are
# removed and treated as a miss - the cache never raises into the caller.
#
# Later phases reuse this module with a different cache resolver for
# per-agent (formation-level) trees; per-document keying stays as-is.
# =============================================================================

import glob
import hashlib
import os
from typing import Dict, Optional

from .....utils.fastjson import json
from .types import TREE_SCHEMA_VERSION, TreeIndex

_TREE_SUFFIX = ".tree.json"
_KV_SUFFIX = ".tree.kv.jsonl"


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
            return TreeIndex.from_json_dict(tree_data, kv=kv)
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
        except OSError:
            # Cache write failure must not fail ingestion; drop partials.
            self._remove_pair(base)

    def invalidate(self, file_path: str) -> int:
        """Remove all cached tree entries for ``file_path`` (any MD5)."""
        pattern = os.path.join(self.cache_dir, f"{self._path_hash(file_path)}_*")
        removed = 0
        for stale in glob.glob(pattern + _TREE_SUFFIX) + glob.glob(pattern + _KV_SUFFIX):
            try:
                os.remove(stale)
                removed += 1
            except OSError:
                pass
        return removed

    def _remove_pair(self, base: str) -> None:
        for path in (base + _TREE_SUFFIX, base + _KV_SUFFIX):
            try:
                os.remove(path)
            except OSError:
                pass
