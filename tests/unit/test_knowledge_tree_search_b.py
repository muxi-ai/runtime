"""Unit tests for Method B value-based tree retrieval (reasoning-RAG Phase 2).

Pins the Phase 2 conventions:

  * Per-node chunk embeddings are built at ingestion (tree build or cache
    load) and persisted in the tree cache sidecar - query time issues NO
    LLM calls for ``retrieval: tree-vector`` sources.
  * Node selection follows the aggregated ``(1/sqrt(N+1)) * sum`` score;
    you retrieve nodes, not chunks.
  * An embedding-model change invalidates the sidecar (tree + KV survive).
  * Failure isolation: Method B failure at query time falls back to vector
    results; embedding failure at ingestion degrades the tree to Method A.
"""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.agents.knowledge.base import FileKnowledge
from muxi.runtime.formation.agents.knowledge.handler import KnowledgeHandler
from muxi.runtime.formation.agents.knowledge.reasoning import (
    ScoringService,
    TreeBuilder,
    TreeCache,
    TreeNavigationError,
    TreeSearchB,
    build_node_chunk_embeddings,
    count_tokens,
    split_text_for_scoring,
)
from muxi.runtime.utils.fastjson import json

# Distinct section markers so scoring assertions can prove which node won.
STRUCTURED_DOC = "\n".join(
    [
        "# Device Manual",
        "General overview of the device. " * 30,
        "## Installation",
        "To install, run the bootstrap installer. " * 30,
        "### Requirements",
        "Requires FIRMWARE-X9 and a powered hub. " * 30,
        "## Troubleshooting",
        "If the light blinks, apply RESET-CODE-77. " * 30,
    ]
)

# Keyword-axis embedder: deterministic, similarity == keyword overlap.
KEYWORDS = ("install", "firmware", "reset", "overview")


async def keyword_embeddings_fn(texts):
    vecs = []
    for text in texts:
        lowered = text.lower()
        vecs.append([float(lowered.count(k)) for k in KEYWORDS] + [0.001])
    return vecs


class FakeLLM:
    """Answers only tree-builder summary prompts; navigation is off-limits."""

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        content = messages[-1]["content"]
        node_ids = re.findall(r"node_id: (\d{4})", content)
        return json.dumps({"summaries": {i: f"Covers topic {i}" for i in node_ids}})


def build_tree(with_embeddings=True):
    llm = FakeLLM()
    builder = TreeBuilder(llm=llm, settings={"max_tokens_per_node": 2000})
    tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))
    if with_embeddings:
        scoring = ScoringService(keyword_embeddings_fn)
        asyncio.run(build_node_chunk_embeddings(tree, scoring))
    return tree


def make_working_memory_mock() -> MagicMock:
    wm = MagicMock()
    wm.add_with_embedding = AsyncMock()
    wm.add = AsyncMock()
    wm.search = AsyncMock(return_value=[])
    wm.get_items_by_metadata = MagicMock(return_value=[])
    wm.remove_by_metadata = MagicMock(return_value=0)
    return wm


def make_handler(tmp_path, tree_llm=None, reasoning_config=None) -> KnowledgeHandler:
    return KnowledgeHandler(
        agent_id_or_sources="test-agent",
        formation_id="test-formation",
        embedding_dimension=5,
        cache_dir=str(tmp_path / "cache"),
        working_memory=make_working_memory_mock(),
        auto_inject_knowledge=False,
        reasoning_config=reasoning_config,
        tree_llm=tree_llm,
    )


# ---------------------------------------------------------------------------
# Chunking fallback
# ---------------------------------------------------------------------------


class TestSplitTextForScoring:
    def test_empty_text_returns_no_chunks(self):
        assert split_text_for_scoring("") == []
        assert split_text_for_scoring("   \n\n  ") == []

    def test_paragraphs_pack_into_windows(self):
        text = "\n\n".join(f"Paragraph {i}. " * 5 for i in range(10))
        chunks = split_text_for_scoring(text, window_chars=200)
        assert len(chunks) > 1
        assert all(len(c) <= 200 for c in chunks)
        assert all(c.strip() for c in chunks)

    def test_oversized_paragraph_hard_splits(self):
        text = "x" * 2500
        chunks = split_text_for_scoring(text, window_chars=800)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_content_is_preserved(self):
        text = "First paragraph.\n\nSecond paragraph with RESET-CODE-77."
        chunks = split_text_for_scoring(text, window_chars=10000)
        assert "RESET-CODE-77" in " ".join(chunks)


# ---------------------------------------------------------------------------
# Per-node chunk embedding build
# ---------------------------------------------------------------------------


class TestBuildNodeChunkEmbeddings:
    def test_fills_embeddings_for_content_nodes(self):
        tree = build_tree(with_embeddings=False)
        scoring = ScoringService(keyword_embeddings_fn)

        total = asyncio.run(build_node_chunk_embeddings(tree, scoring))

        assert total > 0
        content_nodes = [n.node_id for n in tree.walk() if tree.fetch_raw(n.node_id)]
        assert set(tree.chunk_embeddings) == set(content_nodes)
        for vectors in tree.chunk_embeddings.values():
            assert vectors and all(len(v) == len(KEYWORDS) + 1 for v in vectors)

    def test_failing_injected_chunker_falls_back_to_internal_splitter(self):
        tree = build_tree(with_embeddings=False)
        scoring = ScoringService(keyword_embeddings_fn)

        async def broken_chunker(text):
            raise RuntimeError("chunker down")

        total = asyncio.run(build_node_chunk_embeddings(tree, scoring, chunker=broken_chunker))
        assert total > 0 and tree.chunk_embeddings

    def test_records_embedding_model_slug(self):
        tree = build_tree(with_embeddings=False)
        tree.embedding_model = None
        scoring = ScoringService(keyword_embeddings_fn)
        asyncio.run(build_node_chunk_embeddings(tree, scoring))
        # Callable backend has no slug; slug backends record theirs.
        assert tree.embedding_model is None


# ---------------------------------------------------------------------------
# Method B search
# ---------------------------------------------------------------------------


class TestTreeSearchB:
    def test_selects_the_matching_section(self):
        tree = build_tree()
        searcher = TreeSearchB(ScoringService(keyword_embeddings_fn))

        results = asyncio.run(
            searcher.search("how do I reset the device when the light blinks", tree, max_nodes=2)
        )

        assert results, "Method B should select at least one node"
        top = results[0]
        assert "RESET-CODE-77" in top.content
        assert top.metadata["retrieval_method"] == "tree_b"
        assert top.metadata["node_score"] > 0
        assert 0.0 <= top.relevance <= 1.0
        assert isinstance(top.node_path, list) and top.node_path

    def test_returns_nodes_not_chunks(self):
        tree = build_tree()
        searcher = TreeSearchB(ScoringService(keyword_embeddings_fn))
        results = asyncio.run(searcher.search("install firmware", tree, max_nodes=3))
        node_ids = [r.metadata["node_id"] for r in results]
        assert len(node_ids) == len(set(node_ids)), "one result per node"
        for r in results:
            assert tree.get_node(r.metadata["node_id"]) is not None

    def test_no_embeddings_raises_navigation_error(self):
        tree = build_tree(with_embeddings=False)
        searcher = TreeSearchB(ScoringService(keyword_embeddings_fn))
        with pytest.raises(TreeNavigationError):
            asyncio.run(searcher.search("reset", tree))

    def test_embedding_failure_raises_navigation_error(self):
        tree = build_tree()

        async def broken(texts):
            raise RuntimeError("embedding provider down")

        searcher = TreeSearchB(ScoringService(broken))
        with pytest.raises(TreeNavigationError):
            asyncio.run(searcher.search("reset", tree))

    def test_respects_max_nodes(self):
        tree = build_tree()
        searcher = TreeSearchB(ScoringService(keyword_embeddings_fn))
        results = asyncio.run(searcher.search("install firmware reset overview", tree, max_nodes=1))
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# Cache persistence of chunk embeddings
# ---------------------------------------------------------------------------


class TestEmbeddingPersistence:
    def test_cache_roundtrip_preserves_embeddings(self, tmp_path):
        tree = build_tree()
        tree.embedding_model = "test/model-v1"
        cache = TreeCache(str(tmp_path / "cache"))

        cache.save(tree, "/tmp/manual.md", "md5one")
        loaded = cache.load("/tmp/manual.md", "md5one")

        assert loaded is not None
        assert loaded.embedding_model == "test/model-v1"
        assert set(loaded.chunk_embeddings) == set(tree.chunk_embeddings)
        sample = next(iter(tree.chunk_embeddings))
        assert loaded.chunk_embeddings[sample] == tree.chunk_embeddings[sample]

    def test_tree_without_embeddings_loads_without_sidecar(self, tmp_path):
        tree = build_tree(with_embeddings=False)
        cache = TreeCache(str(tmp_path / "cache"))
        cache.save(tree, "/tmp/manual.md", "md5one")
        loaded = cache.load("/tmp/manual.md", "md5one")
        assert loaded is not None and not loaded.chunk_embeddings

    def test_invalidate_removes_embedding_sidecar(self, tmp_path):
        tree = build_tree()
        cache = TreeCache(str(tmp_path / "cache"))
        cache.save(tree, "/tmp/manual.md", "md5one")
        cache.invalidate("/tmp/manual.md")
        assert not list((tmp_path / "cache").glob("*.tree.emb.jsonl"))
        assert cache.load("/tmp/manual.md", "md5one") is None


# ---------------------------------------------------------------------------
# Handler integration: retrieval: tree-vector
# ---------------------------------------------------------------------------


DOC_TOKENS = count_tokens(STRUCTURED_DOC)


class TestHandlerTreeVectorMode:
    def _ingest(self, tmp_path, retrieval="tree-vector"):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": DOC_TOKENS * 10}
        )
        doc = tmp_path / "manual.md"
        doc.write_text(STRUCTURED_DOC, encoding="utf-8")
        source = FileKnowledge(path=str(doc), description="manual", retrieval=retrieval)
        nodes = asyncio.run(handler.add_file(source, keyword_embeddings_fn))
        return handler, llm, nodes

    def test_tree_vector_source_gets_tree_and_embeddings(self, tmp_path):
        handler, llm, nodes = self._ingest(tmp_path)

        assert nodes > 0
        tree = next(iter(handler._tree_indexes.values()))
        assert tree.chunk_embeddings, "tree-vector ingestion must embed node chunks"
        assert next(iter(handler._tree_modes.values())) == "tree-vector"
        # No vector chunks for the tree-indexed file
        handler.working_memory.add_with_embedding.assert_not_awaited()
        # Embedding sidecar persisted
        assert list((tmp_path / "cache").glob("*.tree.emb.jsonl"))

    def test_query_time_uses_scoring_not_llm(self, tmp_path):
        handler, llm, _ = self._ingest(tmp_path)
        calls_after_ingest = llm.calls

        results = asyncio.run(handler.search("how do I reset the blinking light"))

        assert llm.calls == calls_after_ingest, "Method B must not touch the tree LLM"
        tree_results = [r for r in results if r["metadata"].get("retrieval_method") == "tree_b"]
        assert tree_results, "search should return Method B results"
        assert any("RESET-CODE-77" in r["content"] for r in tree_results)

    def test_cache_hit_reuses_embeddings_without_llm(self, tmp_path):
        self._ingest(tmp_path)

        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": DOC_TOKENS * 10}
        )
        doc = str(tmp_path / "manual.md")
        source = FileKnowledge(path=doc, description="manual", retrieval="tree-vector")
        nodes = asyncio.run(handler.add_file(source, keyword_embeddings_fn))

        assert nodes > 0
        assert llm.calls == 0, "cache hit must not issue LLM calls"
        tree = next(iter(handler._tree_indexes.values()))
        assert tree.chunk_embeddings, "embeddings must load from the sidecar"

    def test_mode_upgrade_from_tree_computes_embeddings_from_cache(self, tmp_path):
        """retrieval: tree -> tree-vector reuses the cached tree, adds vectors."""
        self._ingest(tmp_path, retrieval="tree")

        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": DOC_TOKENS * 10}
        )
        doc = str(tmp_path / "manual.md")
        source = FileKnowledge(path=doc, description="manual", retrieval="tree-vector")
        asyncio.run(handler.add_file(source, keyword_embeddings_fn))

        assert llm.calls == 0, "tree JSON survives the mode change - no rebuild"
        tree = next(iter(handler._tree_indexes.values()))
        assert tree.chunk_embeddings

    def test_embedding_failure_degrades_to_method_a(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": DOC_TOKENS * 10}
        )
        doc = tmp_path / "manual.md"
        doc.write_text(STRUCTURED_DOC, encoding="utf-8")

        async def broken(texts):
            raise RuntimeError("embedding provider down")

        source = FileKnowledge(path=str(doc), description="manual", retrieval="tree-vector")
        nodes = asyncio.run(handler.add_file(source, broken))

        assert nodes and nodes > 0, "tree ingestion still succeeds"
        tree = next(iter(handler._tree_indexes.values()))
        assert not tree.chunk_embeddings, "no embeddings recorded on failure"
