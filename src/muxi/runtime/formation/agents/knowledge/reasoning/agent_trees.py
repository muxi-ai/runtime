# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Agent Tree Store - Formation-Directory Persistent Trees
# Description:  Persistence + regeneration-trigger logic for per-agent
#               (formation-level) knowledge trees
# Role:         Storage-side component of reasoning-based RAG Phase 4
# Usage:        Used by KnowledgeHandler for sources declaring ``agent_tree:``
# Author:       Muxi Framework Team
#
# Per-agent trees are built once per SOURCE (not per file), persisted inside
# the formation directory, and reused across formation loads:
#
#   <formation_dir>/.knowledge-trees/
#   ├── <source_id>.json        - tree JSON (PRD layout, scope: "agent")
#   ├── <source_id>.kv.jsonl    - line-delimited {node_id, raw}
#   ├── <source_id>.emb.jsonl   - Method B per-node chunk embeddings
#   │                             (only for tree-vector / hybrid sources)
#   └── <source_id>.meta.json   - schema_version, source_md5,
#                                 build_timestamp, node_count,
#                                 embedding_model
#
# ``.knowledge-trees/`` is deterministic given the source content, so it can
# be committed to the formation repo - deployments then load in O(read)
# without rebuilding. (The PRD sketch named the embeddings file ``.bin``;
# JSONL is used instead to match the per-document cache layout - one
# serialization path, diff-able, and committed-to-git friendly.)
#
# Regeneration triggers (``agent_tree.regenerate``):
#   * manual            - only an explicit rebuild (admin endpoint /
#                         ``muxi knowledge rebuild`` in the CLI repo, or
#                         ``KnowledgeHandler.rebuild_agent_trees``) rebuilds;
#                         a persisted tree is served even if the source
#                         changed. Default - suits static corpora.
#   * on-source-change  - rebuild when the aggregate source MD5 differs
#                         from ``meta.json.source_md5``.
#   * on-formation-load - rebuild on every formation load.
#
# The cache key is ``(formation_id, source_id, source_md5)`` semantically;
# on disk the formation directory scopes the first component and
# ``meta.json.source_md5`` carries the last. Same TreeBuilder / searchers /
# ScoringService as per-document trees - only the resolver differs.
# =============================================================================

import hashlib
import os
import re
import time
from typing import Any, Dict, Optional

from .....utils.fastjson import json
from .tree_cache import read_embeddings_file, write_embeddings_file
from .types import TREE_SCHEMA_VERSION, TreeIndex

TREES_DIRNAME = ".knowledge-trees"

_TREE_SUFFIX = ".json"
_KV_SUFFIX = ".kv.jsonl"
_EMB_SUFFIX = ".emb.jsonl"
_META_SUFFIX = ".meta.json"


def _write_text(path: str, content: str) -> None:
    """Write ``content`` to ``path`` (staging helper for atomic saves)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_kv(path: str, kv: Dict[str, str]) -> None:
    """Write a node->raw KV mapping as line-delimited JSON."""
    with open(path, "w", encoding="utf-8") as f:
        for node_id, raw in kv.items():
            f.write(json.dumps({"node_id": node_id, "raw": raw}) + "\n")


def source_id_for(source_name: str) -> str:
    """Slugify a knowledge source name into a filesystem-safe source_id."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", source_name.strip()).strip("-.")
    return slug or "source"


def compute_source_md5(files: list, md5_fn, root: Optional[str] = None) -> str:
    """
    Aggregate MD5 over a source's files: ``md5(sorted relpath:file_md5)``.

    ``md5_fn(path) -> str`` computes one file's content hash (the handler's
    existing ``_calculate_file_md5``). Paths enter the digest relative to
    ``root`` (the source path) so the hash is stable when the formation
    directory moves between deployments.
    """
    digest = hashlib.md5()
    for path in sorted(os.path.abspath(p) for p in files):
        label = os.path.relpath(path, root) if root else os.path.basename(path)
        file_md5 = md5_fn(path) or ""
        digest.update(f"{label}:{file_md5}\n".encode("utf-8"))
    return digest.hexdigest()


class AgentTreeStore:
    """Formation-directory persistence for per-agent knowledge trees."""

    def __init__(self, formation_dir: str):
        self.trees_dir = os.path.join(formation_dir, TREES_DIRNAME)

    def _base(self, source_id: str) -> str:
        return os.path.join(self.trees_dir, source_id)

    def load_meta(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Load a source's meta.json, or None when absent/corrupt."""
        meta_path = self._base(source_id) + _META_SUFFIX
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.loads(f.read())
            return meta if isinstance(meta, dict) else None
        except Exception:
            return None

    def needs_rebuild(self, source_id: str, source_md5: str, regenerate: str) -> bool:
        """
        Decide whether a persisted tree must be rebuilt for this load.

        Missing/corrupt/older-schema trees always rebuild. Otherwise the
        ``regenerate`` trigger decides (see module frontmatter).
        """
        meta = self.load_meta(source_id)
        tree_path = self._base(source_id) + _TREE_SUFFIX
        kv_path = self._base(source_id) + _KV_SUFFIX
        if meta is None or not (os.path.exists(tree_path) and os.path.exists(kv_path)):
            return True
        if int(meta.get("schema_version", 0)) != TREE_SCHEMA_VERSION:
            return True
        if regenerate == "on-formation-load":
            return True
        if regenerate == "on-source-change":
            return meta.get("source_md5") != source_md5
        return False  # manual: serve the persisted tree as-is

    def load(self, source_id: str) -> Optional[TreeIndex]:
        """Load a persisted agent tree, or None when absent/corrupt."""
        base = self._base(source_id)
        tree_path = base + _TREE_SUFFIX
        kv_path = base + _KV_SUFFIX
        if not (os.path.exists(tree_path) and os.path.exists(kv_path)):
            return None
        try:
            with open(tree_path, "r", encoding="utf-8") as f:
                tree_data = json.loads(f.read())
            if int(tree_data.get("schema_version", 0)) != TREE_SCHEMA_VERSION:
                return None
            kv: Dict[str, str] = {}
            with open(kv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    kv[str(entry["node_id"])] = entry.get("raw", "")
            tree = TreeIndex.from_json_dict(tree_data, kv=kv)
            tree.scope = "agent"
            emb = read_embeddings_file(base + _EMB_SUFFIX)
            if emb is not None:
                tree.chunk_embeddings = emb["embeddings"]
                tree.embedding_model = emb["model"] or None
            return tree
        except Exception:
            return None

    def save(self, tree: TreeIndex, source_id: str, source_md5: str) -> None:
        """
        Persist ``tree`` + meta.json for ``source_id``; best-effort.

        Write-temp-then-replace per file (the remote-knowledge
        ``atomic_download`` pattern): every file is staged as a ``.tmp``
        sibling first and only swapped in once ALL stages succeeded. A
        failure at any point removes the temp files and leaves the
        previously persisted tree fully intact - a failed re-save must
        never destroy a good earlier save.
        """
        base = self._base(source_id)
        temp_suffix = ".tmp"
        staged: list = []  # (temp_path, final_path)
        try:
            os.makedirs(self.trees_dir, exist_ok=True)

            def _stage(suffix: str, writer) -> None:
                temp_path = base + suffix + temp_suffix
                writer(temp_path)
                staged.append((temp_path, base + suffix))

            _stage(
                _TREE_SUFFIX,
                lambda path: _write_text(path, json.dumps(tree.to_json_dict(include_kv=False))),
            )
            _stage(_KV_SUFFIX, lambda path: _write_kv(path, tree.kv))
            if tree.chunk_embeddings:
                _stage(_EMB_SUFFIX, lambda path: write_embeddings_file(path, tree))
            meta = {
                "schema_version": TREE_SCHEMA_VERSION,
                "source_id": source_id,
                "source_md5": source_md5,
                "build_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "node_count": tree.node_count,
                "token_count": tree.token_count,
                "tree_token_count": tree.tree_token_count,
                "embedding_model": tree.embedding_model or "",
            }
            _stage(_META_SUFFIX, lambda path: _write_text(path, json.dumps(meta)))

            # All stages written - swap them in. os.replace is atomic on
            # the same filesystem, so readers never observe a torn file.
            for temp_path, final_path in staged:
                os.replace(temp_path, final_path)
            staged = []
            if not tree.chunk_embeddings:
                # A tree that lost its embeddings (e.g. mode downgraded)
                # must not serve a stale sidecar.
                try:
                    os.remove(base + _EMB_SUFFIX)
                except OSError:
                    pass
        except OSError:
            # Never fail the caller and never touch the previously
            # persisted files - just drop the staged temp files.
            for temp_path, _ in staged:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def remove(self, source_id: str) -> None:
        """Remove all persisted files for ``source_id`` (best-effort)."""
        base = self._base(source_id)
        for path in (
            base + _TREE_SUFFIX,
            base + _KV_SUFFIX,
            base + _EMB_SUFFIX,
            base + _META_SUFFIX,
        ):
            try:
                os.remove(path)
            except OSError:
                pass
