"""Unit tests for per-agent (formation-level) trees (reasoning-RAG Phase 4).

Pins the Phase 4 conventions:

  * Storage layout: ``<formation_dir>/.knowledge-trees/<source_id>.json``
    + ``.kv.jsonl`` + ``.emb.jsonl`` + ``.meta.json`` (versioned).
  * Regeneration triggers: ``manual`` serves the persisted tree even when
    the source changed; ``on-source-change`` rebuilds on MD5 drift only;
    ``on-formation-load`` rebuilds every load.
  * The rebuild API (``KnowledgeHandler.rebuild_agent_trees``) force-
    rebuilds regardless of trigger - the runtime side of
    ``muxi knowledge rebuild``.
  * Agent trees serve retrieval with ``source_type: "agent_tree"`` and
    never write vector chunks; without a formation directory the source
    falls back to the standard pipeline.
"""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

from muxi.runtime.formation.agents.knowledge.base import FileKnowledge
from muxi.runtime.formation.agents.knowledge.handler import KnowledgeHandler
from muxi.runtime.formation.agents.knowledge.reasoning import (
    AgentTreeStore,
    TreeBuilder,
    compute_source_md5,
    source_id_for,
)
from muxi.runtime.formation.agents.knowledge.reasoning.types import TREE_SCHEMA_VERSION
from muxi.runtime.utils.fastjson import json

CORPUS_DOC = "\n".join(
    [
        "# Regulations",
        "General provisions of the code. " * 30,
        "## Filing Deadlines",
        "Annual reports are due within 90 days. " * 30,
        "## Penalties",
        "Late filing incurs FINE-CODE-501. " * 30,
    ]
)

KEYWORDS = ("filing", "penalties", "provisions")


async def keyword_embeddings_fn(texts):
    vecs = []
    for text in texts:
        lowered = text.lower()
        vecs.append([float(lowered.count(k)) for k in KEYWORDS] + [0.001])
    return vecs


class FakeLLM:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def chat(self, messages, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated LLM outage")
        content = messages[-1]["content"]
        node_ids = re.findall(r"node_id: (\d{4})", content)
        if node_ids:  # summary pass
            return json.dumps({"summaries": {i: f"Covers topic {i}" for i in node_ids}})
        # Navigation: select the Penalties section (0003 in the corpus tree:
        # 0000 root -> 0001 Regulations -> 0002 Filing Deadlines, 0003 Penalties)
        return json.dumps({"thinking": "picked", "node_list": ["0003"]})


def make_working_memory_mock() -> MagicMock:
    wm = MagicMock()
    wm.add_with_embedding = AsyncMock()
    wm.add = AsyncMock()
    wm.search = AsyncMock(return_value=[])
    wm.get_items_by_metadata = MagicMock(return_value=[])
    wm.remove_by_metadata = MagicMock(return_value=0)
    return wm


def make_handler(tmp_path, tree_llm=None, formation_path=None) -> KnowledgeHandler:
    return KnowledgeHandler(
        agent_id_or_sources="test-agent",
        formation_id="test-formation",
        embedding_dimension=4,
        cache_dir=str(tmp_path / "cache"),
        working_memory=make_working_memory_mock(),
        auto_inject_knowledge=False,
        reasoning_config={"reasoning_threshold": 10_000_000},  # never auto-gate
        tree_llm=tree_llm,
        formation_path=str(formation_path) if formation_path else None,
    )


def write_corpus(tmp_path, content=CORPUS_DOC):
    knowledge_dir = tmp_path / "formation" / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    doc = knowledge_dir / "regulations.md"
    doc.write_text(content, encoding="utf-8")
    return tmp_path / "formation", str(doc)


def make_source(doc, regenerate="manual", retrieval="tree"):
    return FileKnowledge(
        path=doc,
        description="regulations",
        retrieval=retrieval,
        agent_tree={"regenerate": regenerate},
    )


def ingest(handler, source):
    return asyncio.run(handler.add_file(source, keyword_embeddings_fn))


# ---------------------------------------------------------------------------
# Helpers: source ids and aggregate MD5
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_source_id_slugification(self):
        assert source_id_for("knowledge/regulations/") == "knowledge-regulations"
        assert source_id_for("My Docs (v2)") == "My-Docs-v2"
        assert source_id_for("   ") == "source"

    def test_source_md5_is_content_sensitive(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("alpha")
        b.write_text("beta")

        def md5_fn(path):
            import hashlib

            return hashlib.md5(open(path, "rb").read()).hexdigest()

        first = compute_source_md5([str(a), str(b)], md5_fn, root=str(tmp_path))
        a.write_text("alpha changed")
        second = compute_source_md5([str(a), str(b)], md5_fn, root=str(tmp_path))
        assert first != second

    def test_source_md5_is_order_independent(self, tmp_path):
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("alpha")
        b.write_text("beta")

        def md5_fn(path):
            import hashlib

            return hashlib.md5(open(path, "rb").read()).hexdigest()

        forward = compute_source_md5([str(a), str(b)], md5_fn, root=str(tmp_path))
        reverse = compute_source_md5([str(b), str(a)], md5_fn, root=str(tmp_path))
        assert forward == reverse


# ---------------------------------------------------------------------------
# Store roundtrip + meta versioning
# ---------------------------------------------------------------------------


class TestAgentTreeStore:
    def _build_tree(self):
        builder = TreeBuilder(llm=FakeLLM(), settings={"max_tokens_per_node": 2000})
        tree = asyncio.run(builder.build(text=CORPUS_DOC, document_name="regulations"))
        tree.scope = "agent"
        return tree

    def test_roundtrip_and_meta(self, tmp_path):
        store = AgentTreeStore(str(tmp_path))
        tree = self._build_tree()

        store.save(tree, "regulations", "md5-abc")
        loaded = store.load("regulations")
        meta = store.load_meta("regulations")

        assert loaded is not None
        assert loaded.scope == "agent"
        assert loaded.to_json_dict()["tree"] == tree.to_json_dict()["tree"]
        assert loaded.kv == tree.kv
        assert meta["schema_version"] == TREE_SCHEMA_VERSION
        assert meta["source_md5"] == "md5-abc"
        assert meta["node_count"] == tree.node_count
        assert meta["build_timestamp"]
        trees_dir = tmp_path / ".knowledge-trees"
        assert (trees_dir / "regulations.json").exists()
        assert (trees_dir / "regulations.kv.jsonl").exists()
        assert (trees_dir / "regulations.meta.json").exists()

    def test_needs_rebuild_matrix(self, tmp_path):
        store = AgentTreeStore(str(tmp_path))
        tree = self._build_tree()
        store.save(tree, "regs", "md5-one")

        # Missing tree always rebuilds
        assert store.needs_rebuild("absent", "md5-one", "manual") is True
        # manual: never rebuilds, even on content drift
        assert store.needs_rebuild("regs", "md5-one", "manual") is False
        assert store.needs_rebuild("regs", "md5-CHANGED", "manual") is False
        # on-source-change: rebuild only on drift
        assert store.needs_rebuild("regs", "md5-one", "on-source-change") is False
        assert store.needs_rebuild("regs", "md5-CHANGED", "on-source-change") is True
        # on-formation-load: always
        assert store.needs_rebuild("regs", "md5-one", "on-formation-load") is True

    def test_failed_resave_preserves_previous_files(self, tmp_path, monkeypatch):
        """OSError mid-save must leave the prior persisted tree intact.

        Greptile finding on PR #263: a failed second save used to remove
        ALL files for the source, silently losing persistence until the
        next restart. The atomic write-temp-then-replace save only swaps
        files in after every stage succeeded.
        """
        from muxi.runtime.formation.agents.knowledge.reasoning import agent_trees

        store = AgentTreeStore(str(tmp_path))
        tree_v1 = self._build_tree()
        tree_v1.chunk_embeddings = {"0001": [[0.1, 0.2]]}
        tree_v1.embedding_model = "test/model-v1"
        store.save(tree_v1, "regs", "md5-v1")
        assert store.load("regs") is not None

        # Second save fails mid-write (embeddings stage).
        def _boom(path, tree):
            raise OSError("disk full")

        monkeypatch.setattr(agent_trees, "write_embeddings_file", _boom)
        tree_v2 = self._build_tree()
        tree_v2.chunk_embeddings = {"0001": [[0.9, 0.9]]}
        store.save(tree_v2, "regs", "md5-v2")  # must not raise

        # v1 stays fully intact and loadable; no temp files linger.
        meta = store.load_meta("regs")
        assert meta is not None and meta["source_md5"] == "md5-v1"
        loaded = store.load("regs")
        assert loaded is not None
        assert loaded.chunk_embeddings == {"0001": [[0.1, 0.2]]}
        assert not list((tmp_path / ".knowledge-trees").glob("*.tmp"))

    def test_save_is_staged_before_replacing(self, tmp_path):
        """A successful save leaves no .tmp staging files behind."""
        store = AgentTreeStore(str(tmp_path))
        tree = self._build_tree()
        tree.chunk_embeddings = {"0001": [[0.5]]}
        store.save(tree, "regs", "md5-one")
        files = sorted(p.name for p in (tmp_path / ".knowledge-trees").iterdir())
        assert not any(name.endswith(".tmp") for name in files)
        assert store.load("regs") is not None

    def test_remove_drops_all_files(self, tmp_path):
        store = AgentTreeStore(str(tmp_path))
        tree = self._build_tree()
        store.save(tree, "regs", "md5-one")
        store.remove("regs")
        assert store.load("regs") is None
        assert store.load_meta("regs") is None
        assert not list((tmp_path / ".knowledge-trees").iterdir())


# ---------------------------------------------------------------------------
# Handler integration: triggers, retrieval, fallback
# ---------------------------------------------------------------------------


class TestHandlerAgentTrees:
    def test_initial_ingest_builds_and_persists(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        llm = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm, formation_path=formation_dir)

        nodes = ingest(handler, make_source(doc))

        assert nodes and nodes > 0
        assert llm.calls > 0
        tree = next(iter(handler._tree_indexes.values()))
        assert tree.scope == "agent"
        handler.working_memory.add_with_embedding.assert_not_awaited()
        assert (formation_dir / ".knowledge-trees" / "regulations.md.json").exists()

    def test_manual_trigger_serves_stale_tree_without_llm(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        first = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        ingest(first, make_source(doc, regenerate="manual"))

        # Change the source content; manual must still serve the old tree
        write_corpus(tmp_path, content=CORPUS_DOC + "\n## New Section\nAdded text.")
        llm = FakeLLM()
        second = make_handler(tmp_path, tree_llm=llm, formation_path=formation_dir)
        nodes = ingest(second, make_source(doc, regenerate="manual"))

        assert nodes and nodes > 0
        assert llm.calls == 0, "manual trigger must not rebuild on content change"

    def test_on_source_change_rebuilds_on_drift_only(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        ingest(
            make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir),
            make_source(doc, regenerate="on-source-change"),
        )

        # Same content -> no rebuild
        llm_same = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm_same, formation_path=formation_dir)
        ingest(handler, make_source(doc, regenerate="on-source-change"))
        assert llm_same.calls == 0

        # Changed content -> rebuild
        write_corpus(tmp_path, content=CORPUS_DOC + "\n## Amendments\nNew rules.")
        llm_changed = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm_changed, formation_path=formation_dir)
        ingest(handler, make_source(doc, regenerate="on-source-change"))
        assert llm_changed.calls > 0, "content drift must trigger a rebuild"

    def test_on_formation_load_always_rebuilds(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        ingest(
            make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir),
            make_source(doc, regenerate="on-formation-load"),
        )

        llm = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm, formation_path=formation_dir)
        ingest(handler, make_source(doc, regenerate="on-formation-load"))
        assert llm.calls > 0, "on-formation-load must rebuild every load"

    def test_ingest_persists_exactly_once(self, tmp_path, monkeypatch):
        """One store.save per build - the second unconditional save was the
        window where a transient failure could clobber a good write."""
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        store = handler._get_agent_tree_store()
        calls = []
        original_save = store.save

        def counting_save(tree, source_id, source_md5):
            calls.append(source_id)
            return original_save(tree, source_id, source_md5)

        monkeypatch.setattr(store, "save", counting_save)
        nodes = ingest(handler, make_source(doc, retrieval="hybrid"))

        assert nodes and nodes > 0
        assert len(calls) == 1, f"expected exactly one save, got {calls}"

    def test_search_returns_agent_tree_source_type(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        ingest(handler, make_source(doc))

        results = asyncio.run(handler.search("what is the late filing penalty"))

        agent_results = [r for r in results if r["metadata"].get("source_type") == "agent_tree"]
        assert agent_results, "agent tree should serve the query"
        assert any("FINE-CODE-501" in r["content"] for r in agent_results)

    def test_hybrid_agent_tree_gets_chunk_embeddings(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        ingest(handler, make_source(doc, retrieval="hybrid"))

        tree = next(iter(handler._tree_indexes.values()))
        assert tree.chunk_embeddings, "hybrid agent tree must embed node chunks"
        assert (formation_dir / ".knowledge-trees" / "regulations.md.emb.jsonl").exists()

    def test_no_formation_path_falls_back_to_standard_pipeline(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=None)

        nodes = ingest(handler, make_source(doc))

        # Falls through to the per-file gate: the explicit ``retrieval:
        # tree`` still tree-indexes the file, but as a per-DOCUMENT tree
        # with no formation-directory persistence.
        assert nodes and nodes > 0
        assert all(t.scope == "document" for t in handler._tree_indexes.values())
        assert not (formation_dir / ".knowledge-trees").exists()

    def test_build_failure_falls_back_without_raising(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(fail=True), formation_path=formation_dir)

        ingest(handler, make_source(doc))

        assert not handler._tree_indexes
        assert (
            handler.working_memory.add_with_embedding.await_count > 0
        ), "vector pipeline must serve the source after a build failure"


# ---------------------------------------------------------------------------
# Rebuild API (runtime side of `muxi knowledge rebuild`)
# ---------------------------------------------------------------------------


class TestRebuildAPI:
    def test_rebuild_forces_a_fresh_build(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        llm = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm, formation_path=formation_dir)
        ingest(handler, make_source(doc, regenerate="manual"))
        calls_after_ingest = llm.calls

        report = asyncio.run(handler.rebuild_agent_trees())

        assert llm.calls > calls_after_ingest, "rebuild must force a fresh LLM build"
        assert report["rebuilt"] and report["rebuilt"][0]["source_id"] == "regulations.md"
        assert not report["failed"]

    def test_rebuild_filters_by_source_id(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        ingest(handler, make_source(doc))

        report = asyncio.run(handler.rebuild_agent_trees(source_id="does-not-exist"))

        assert not report["rebuilt"]
        assert report["skipped"] == ["regulations.md"]

    def test_rebuild_updates_meta_md5(self, tmp_path):
        formation_dir, doc = write_corpus(tmp_path)
        handler = make_handler(tmp_path, tree_llm=FakeLLM(), formation_path=formation_dir)
        ingest(handler, make_source(doc, regenerate="manual"))

        # Content drifts; manual keeps the stale tree until rebuild is forced
        write_corpus(tmp_path, content=CORPUS_DOC + "\n## Appendix\nExtra.")
        stale_meta = handler._get_agent_tree_store().load_meta("regulations.md")
        asyncio.run(handler.rebuild_agent_trees())
        fresh_meta = handler._get_agent_tree_store().load_meta("regulations.md")

        assert stale_meta["source_md5"] != fresh_meta["source_md5"]
