"""Unit tests for reasoning-based RAG (Phase 1: Method A tree retrieval).

Covers the conventions pinned by the knowledge-reasoning-rag PRD:

  * Threshold gating - files under ``reasoning_threshold`` flow through the
    vector pipeline unchanged; files above it get tree-indexed instead.
  * Tree build determinism/caching - the same ``(file_path, file_md5)``
    never rebuilds (cache hit issues zero LLM calls); a content change
    invalidates the cached tree.
  * Navigation happy path - Method A selects nodes via one structured LLM
    call and resolves raw content from the KV mapping.
  * Failure isolation - tree build failure at ingestion falls back to
    vector indexing; navigation failure at query time falls back to vector
    search results. Neither raises.
  * Inert when unconfigured - handlers without a tree model (or with
    ``reasoning_threshold: 0``) behave exactly like the pre-feature vector
    path: no LLM calls, no tree cache files, identical chunk writes.
"""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from muxi.runtime.formation.agents.knowledge.base import FileKnowledge
from muxi.runtime.formation.agents.knowledge.handler import KnowledgeHandler
from muxi.runtime.formation.agents.knowledge.reasoning import (
    TreeBuilder,
    TreeCache,
    TreeNavigationError,
    TreeSearchA,
    count_tokens,
)
from muxi.runtime.utils.fastjson import json

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# A structured markdown document. Distinctive markers let assertions prove
# which section's raw content was retrieved.
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


class FakeLLM:
    """Deterministic stand-in for the runtime LLM.

    Answers the tree-builder summary prompt with one summary per node_id
    found in the prompt, and the Method A navigation prompt with a fixed
    node selection. Counts calls so cache-hit tests can assert zero LLM
    traffic.
    """

    def __init__(self, node_list=None, fail=False):
        self.calls = 0
        self.node_list = node_list if node_list is not None else ["0003"]
        self.fail = fail

    async def chat(self, messages, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("simulated LLM outage")
        content = messages[-1]["content"]
        node_ids = re.findall(r"node_id: (\d{4})", content)
        if node_ids:  # summary pass
            return json.dumps({"summaries": {i: f"Covers topic {i}" for i in node_ids}})
        return json.dumps({"thinking": "picked", "node_list": self.node_list})


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
        embedding_dimension=8,
        cache_dir=str(tmp_path / "cache"),
        working_memory=make_working_memory_mock(),
        auto_inject_knowledge=False,
        reasoning_config=reasoning_config,
        tree_llm=tree_llm,
    )


async def fake_embeddings_fn(texts):
    return [[0.1] * 8 for _ in texts]


def write_doc(tmp_path, name="manual.md", content=STRUCTURED_DOC) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def tree_cache_files(tmp_path):
    cache_dir = tmp_path / "cache"
    if not cache_dir.exists():
        return []
    return sorted(p.name for p in cache_dir.iterdir() if ".tree." in p.name)


DOC_TOKENS = count_tokens(STRUCTURED_DOC)
LOW_THRESHOLD = max(1, DOC_TOKENS // 2)  # doc qualifies
HIGH_THRESHOLD = DOC_TOKENS * 10  # doc does not qualify


# ---------------------------------------------------------------------------
# Threshold gating
# ---------------------------------------------------------------------------


class TestThresholdGating:
    def test_file_above_threshold_is_tree_indexed(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="manual")

        nodes = asyncio.run(handler.add_file(source, fake_embeddings_fn))

        assert nodes > 0, "tree ingestion should report node count"
        assert list(handler._tree_indexes), "tree registry should hold the document"
        # Tree-indexed files must NOT also be vector-embedded
        handler.working_memory.add_with_embedding.assert_not_awaited()
        assert tree_cache_files(tmp_path), "tree cache files should be written"

    def test_file_under_threshold_uses_vector_path(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": HIGH_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="manual")

        asyncio.run(handler.add_file(source, fake_embeddings_fn))

        assert not handler._tree_indexes
        assert llm.calls == 0, "under-threshold files must not touch the tree LLM"
        assert handler.working_memory.add_with_embedding.await_count > 0
        assert not tree_cache_files(tmp_path)

    def test_explicit_retrieval_tree_overrides_threshold(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": HIGH_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="manual", retrieval="tree")

        nodes = asyncio.run(handler.add_file(source, fake_embeddings_fn))

        assert nodes > 0
        assert list(handler._tree_indexes)
        handler.working_memory.add_with_embedding.assert_not_awaited()

    def test_explicit_retrieval_vector_overrides_threshold(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="manual", retrieval="vector")

        asyncio.run(handler.add_file(source, fake_embeddings_fn))

        assert not handler._tree_indexes
        assert llm.calls == 0
        assert handler.working_memory.add_with_embedding.await_count > 0


# ---------------------------------------------------------------------------
# Tree build caching / determinism
# ---------------------------------------------------------------------------


class TestTreeCaching:
    def test_same_content_never_rebuilds(self, tmp_path):
        doc = write_doc(tmp_path)
        reasoning = {"reasoning_threshold": LOW_THRESHOLD}

        llm_first = FakeLLM()
        first = make_handler(tmp_path, tree_llm=llm_first, reasoning_config=reasoning)
        asyncio.run(first.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn))
        assert llm_first.calls > 0

        # Fresh handler, same cache dir, same file content -> cache hit
        llm_second = FakeLLM()
        second = make_handler(tmp_path, tree_llm=llm_second, reasoning_config=reasoning)
        nodes = asyncio.run(
            second.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn)
        )

        assert nodes > 0
        assert llm_second.calls == 0, "cache hit must not issue LLM calls"
        assert list(second._tree_indexes)

    def test_cached_tree_roundtrip_is_lossless(self, tmp_path):
        llm = FakeLLM()
        builder = TreeBuilder(llm=llm, settings={"max_tokens_per_node": 2000})
        tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        cache = TreeCache(str(tmp_path / "cache"))
        cache.save(tree, "/tmp/manual.md", "md5one")
        loaded = cache.load("/tmp/manual.md", "md5one")

        assert loaded is not None
        assert loaded.to_json_dict() == tree.to_json_dict()
        assert loaded.kv == tree.kv

    def test_content_change_invalidates_cache(self, tmp_path):
        llm = FakeLLM()
        builder = TreeBuilder(llm=llm, settings={})
        tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        cache = TreeCache(str(tmp_path / "cache"))
        cache.save(tree, "/tmp/manual.md", "md5one")

        assert cache.load("/tmp/manual.md", "md5two") is None, "different MD5 must miss"
        cache.save(tree, "/tmp/manual.md", "md5two")
        assert cache.load("/tmp/manual.md", "md5one") is None, "stale entry must be evicted"


# ---------------------------------------------------------------------------
# Method A navigation
# ---------------------------------------------------------------------------


class TestNavigationHappyPath:
    def test_search_returns_selected_node_content(self, tmp_path):
        llm = FakeLLM(node_list=["0003"])
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        asyncio.run(handler.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn))

        results = asyncio.run(
            handler.search("what firmware is required?", generate_embeddings_fn=fake_embeddings_fn)
        )

        assert results, "tree navigation should return results"
        top = results[0]
        assert top["metadata"]["source_type"] == "tree"
        assert top["metadata"]["retrieval_method"] == "tree_a"
        assert top["metadata"]["node_id"] == "0003"
        assert isinstance(top["metadata"].get("node_path"), list)
        tree = next(iter(handler._tree_indexes.values()))
        assert top["content"] == tree.fetch_raw("0003")[: len(top["content"])]

    def test_tree_search_a_skips_hallucinated_node_ids(self, tmp_path):
        llm = FakeLLM(node_list=["9999", "0002"])
        builder = TreeBuilder(llm=FakeLLM(), settings={})
        tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        results = asyncio.run(TreeSearchA(llm).search("install steps", tree, max_nodes=3))

        assert [r.metadata["node_id"] for r in results] == ["0002"]

    def test_tree_search_a_raises_on_bad_output(self, tmp_path):
        class GarbageLLM:
            async def chat(self, messages, **kwargs):
                return "not json at all"

        builder = TreeBuilder(llm=FakeLLM(), settings={})
        tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        with pytest.raises(TreeNavigationError):
            asyncio.run(TreeSearchA(GarbageLLM()).search("q", tree))


# ---------------------------------------------------------------------------
# Failure isolation (both fallback paths)
# ---------------------------------------------------------------------------


class TestFallbackPaths:
    def test_build_failure_falls_back_to_vector(self, tmp_path):
        llm = FakeLLM(fail=True)
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)

        chunks = asyncio.run(
            handler.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn)
        )

        assert not handler._tree_indexes, "failed build must not register a tree"
        assert chunks > 0, "vector fallback should still index the file"
        assert handler.working_memory.add_with_embedding.await_count > 0
        assert not tree_cache_files(tmp_path)

    def test_navigation_failure_falls_back_to_vector_results(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        asyncio.run(handler.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn))

        # LLM starts failing after ingestion (query-time outage)
        llm.fail = True
        handler.working_memory.search = AsyncMock(
            return_value=[
                {"text": "vector chunk content", "score": 0.9, "metadata": {"chunk_id": "c1"}}
            ]
        )

        results = asyncio.run(
            handler.search("what firmware is required?", generate_embeddings_fn=fake_embeddings_fn)
        )

        assert results, "vector results must still serve the turn"
        assert all(r["metadata"].get("source_type") != "tree" for r in results)

    def test_explicit_tree_without_model_falls_back(self, tmp_path):
        handler = make_handler(tmp_path, tree_llm=None)
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="m", retrieval="tree")

        chunks = asyncio.run(handler.add_file(source, fake_embeddings_fn))

        assert not handler._tree_indexes
        assert chunks > 0, "source must still load via the vector pipeline"


# ---------------------------------------------------------------------------
# Inert when unconfigured
# ---------------------------------------------------------------------------


class TestInertWhenUnconfigured:
    def test_no_tree_llm_is_byte_identical_to_vector_path(self, tmp_path):
        doc = write_doc(tmp_path)

        # Control: handler constructed exactly as before this feature
        # (no reasoning kwargs). Candidate: reasoning config present but no
        # tree model (e.g. handler used outside an agent). Separate cache
        # dirs so the vector disk cache cannot short-circuit either run.
        control = make_handler(tmp_path / "a")
        candidate = make_handler(tmp_path / "b", reasoning_config={"reasoning_threshold": 1})

        asyncio.run(control.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn))
        asyncio.run(
            candidate.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn)
        )

        control_writes = [
            (c.kwargs["text"], c.kwargs["metadata"]["chunk_id"])
            for c in control.working_memory.add_with_embedding.await_args_list
        ]
        candidate_writes = [
            (c.kwargs["text"], c.kwargs["metadata"]["chunk_id"])
            for c in candidate.working_memory.add_with_embedding.await_args_list
        ]
        assert control_writes, "control run must have produced vector writes"
        assert (
            candidate_writes == control_writes
        ), "without a tree model the vector write sequence must be identical"
        assert not candidate._tree_indexes
        assert not tree_cache_files(tmp_path / "b")

    def test_threshold_zero_disables_tree_indexing(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": 0})
        doc = write_doc(tmp_path)

        asyncio.run(handler.add_file(FileKnowledge(path=doc, description="m"), fake_embeddings_fn))

        assert llm.calls == 0
        assert not handler._tree_indexes
        assert handler.working_memory.add_with_embedding.await_count > 0

    def test_search_without_trees_is_unchanged(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": 0})
        handler.working_memory.search = AsyncMock(
            return_value=[{"text": "chunk", "score": 0.5, "metadata": {}}]
        )

        results = asyncio.run(handler.search("q", generate_embeddings_fn=fake_embeddings_fn))

        assert llm.calls == 0, "no trees -> no tree navigation LLM calls"
        assert len(results) == 1
        assert results[0]["content"] == "chunk"


# ---------------------------------------------------------------------------
# Tree walk / lookup structure
# ---------------------------------------------------------------------------


class TestTreeWalkAndLookup:
    def test_walk_is_preorder_and_lookups_match(self):
        llm = FakeLLM()
        builder = TreeBuilder(llm=llm, settings={})
        tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        # The builder assigns node ids in pre-order, so a pre-order walk
        # must yield strictly increasing ids starting at the root.
        walked_ids = [n.node_id for n in tree.walk()]
        assert walked_ids == sorted(walked_ids)
        assert walked_ids[0] == "0000"

        # get_node / node_path use the lazy lookup maps, not traversal
        for node_id in walked_ids:
            node = tree.get_node(node_id)
            assert node is not None and node.node_id == node_id
            path = tree.node_path(node_id)
            assert path and path[0] == "manual.md" and path[-1] == node.title
        assert tree.get_node("9999") is None
        assert tree.node_path("9999") == []


# ---------------------------------------------------------------------------
# Directory sources (incl. remote-mirror shape) and repeat ingestion
# ---------------------------------------------------------------------------


class TestDirectoryGating:
    def _make_mixed_dir(self, tmp_path):
        """A directory source shaped like a remote-sync content mirror:
        recursive path dir containing one over-threshold file and one
        small file (remote sources are presented to the handler exactly
        like this, so this also pins that remote-synced files flow
        through the tree gate)."""
        content_dir = tmp_path / "mirror" / "content"
        content_dir.mkdir(parents=True)
        (content_dir / "big-manual.md").write_text(STRUCTURED_DOC, encoding="utf-8")
        (content_dir / "small-note.md").write_text("# Note\nA tiny note.", encoding="utf-8")
        return FileKnowledge(path=str(content_dir), description="synced mirror", recursive=True)

    def test_directory_gates_per_file(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        source = self._make_mixed_dir(tmp_path)

        asyncio.run(handler.add_file(source, fake_embeddings_fn))

        tree_paths = list(handler._tree_indexes)
        assert any("big-manual.md" in p for p in tree_paths), "large file should be tree-indexed"
        assert not any("small-note.md" in p for p in tree_paths)
        vector_texts = [
            c.kwargs["text"] for c in handler.working_memory.add_with_embedding.await_args_list
        ]
        assert any("tiny note" in t for t in vector_texts), "small file stays on the vector path"
        assert not any(
            "FIRMWARE-X9" in t for t in vector_texts
        ), "tree-indexed file must not be vector-chunked"

    def test_repeat_ingestion_of_same_source_object_keeps_tree_files_visible(self, tmp_path):
        llm = FakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        source = self._make_mixed_dir(tmp_path)
        all_files = list(source.get_files())

        asyncio.run(handler.add_file(source, fake_embeddings_fn))
        calls_after_first = llm.calls
        assert calls_after_first > 0

        # The source object must NOT have been narrowed to the non-tree
        # subset: a second pass over the same FileKnowledge instance still
        # sees (and re-evaluates) every file.
        assert list(source.get_files()) == all_files

        asyncio.run(handler.add_file(source, fake_embeddings_fn))
        assert list(source.get_files()) == all_files
        assert (
            llm.calls == calls_after_first
        ), "second pass re-evaluates tree files via the MD5 cache (no rebuild)"
        assert any("big-manual.md" in p for p in handler._tree_indexes)


# ---------------------------------------------------------------------------
# Concurrency: keyed check-and-build lock
# ---------------------------------------------------------------------------


class TestConcurrentBuildLock:
    def test_concurrent_ingest_builds_once(self, tmp_path):
        class SlowFakeLLM(FakeLLM):
            async def chat(self, messages, **kwargs):
                # Yield control mid-build so a concurrent ingest of the
                # same file gets a chance to race the check-and-build.
                await asyncio.sleep(0.01)
                return await super().chat(messages, **kwargs)

        llm = SlowFakeLLM()
        handler = make_handler(
            tmp_path, tree_llm=llm, reasoning_config={"reasoning_threshold": LOW_THRESHOLD}
        )
        doc = write_doc(tmp_path)
        source = FileKnowledge(path=doc, description="m")
        import hashlib as _hashlib

        md5 = _hashlib.md5(STRUCTURED_DOC.encode("utf-8")).hexdigest()

        async def _race():
            return await asyncio.gather(
                handler._maybe_ingest_as_tree(source, doc, md5),
                handler._maybe_ingest_as_tree(source, doc, md5),
            )

        first, second = asyncio.run(_race())

        assert first == second and first > 0
        assert llm.calls == 1, "second entrant must hit the cache under the lock, not rebuild"
        assert not handler._tree_build_locks, "lock map is pruned after the last waiter releases"


# ---------------------------------------------------------------------------
# Retry backoff in the summary pass
# ---------------------------------------------------------------------------


class TestSummaryRetryBackoff:
    def test_transient_failure_retries_after_backoff(self, tmp_path):
        class FlakyLLM(FakeLLM):
            async def chat(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("429 simulated rate limit")
                node_ids = re.findall(r"node_id: (\d{4})", messages[-1]["content"])
                return json.dumps({"summaries": {i: f"s{i}" for i in node_ids}})

        from unittest.mock import patch

        from muxi.runtime.formation.agents.knowledge.reasoning import tree_builder as tb

        llm = FlakyLLM()
        sleep_mock = AsyncMock()
        with patch.object(tb.asyncio, "sleep", sleep_mock):
            builder = TreeBuilder(llm=llm, settings={})
            tree = asyncio.run(builder.build(text=STRUCTURED_DOC, document_name="manual.md"))

        assert llm.calls == 2, "first attempt fails, retry succeeds"
        assert tree.node_count > 1
        sleep_mock.assert_awaited_once_with(2)  # 1 * (attempt + 1) for attempt=1
