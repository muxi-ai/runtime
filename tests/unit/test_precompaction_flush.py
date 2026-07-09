"""Unit tests for Memory Revamp Phase 3: pre-compaction flush.

Covers the WorkingMemory eviction listener hook (threshold trigger,
eviction-time safety net, no-double-flush marking, listener failure
isolation), the PreCompactionFlushService silent turn (grouping per user,
digest through the captain's log, model-less no-op), configuration gating
(flush_enabled: false stays fully inert -- the standing inertness pin), and
the end-to-end path: items evicted from the buffer survive in the captain's
log and knowledge graph.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.flush import (
    DEFAULT_FLUSH_THRESHOLD,
    PreCompactionFlushService,
    _group_items_by_user,
)
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.log.service import CaptainsLogService
from muxi.runtime.services.memory.working import WorkingMemory

FORMATION_ID = "flush-test-formation"

DIGEST_RESPONSE = (
    "{"
    '"summary": "The user shared launch details for the MUXI project.",'
    '"decisions": ["Launch next month"],'
    '"projects": ["MUXI"],'
    '"context": "Buffer flush test.",'
    '"lessons": [],'
    '"entities": [{"name": "MUXI", "type": "project", "confidence": 0.95}],'
    '"relationships": []'
    "}"
)


class FakeModel:
    def __init__(self, response=DIGEST_RESPONSE):
        self.response = response
        self.calls = 0

    async def generate_text(self, prompt, caching=True):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/flush.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def captains_log(db_manager):
    graph = KnowledgeGraphService(db_manager, FORMATION_ID)
    return CaptainsLogService(db_manager, FORMATION_ID, knowledge_graph=graph)


_ITEM_COUNTER = iter(range(1, 10_000))


def _buffer_item(text: str, role: str = "user", user_id: str = "u1", flushed: bool = False):
    metadata = {"role": role, "user_id": user_id, "formation_id": FORMATION_ID}
    if flushed:
        metadata["_memory_flushed"] = True
    return {
        "text": text,
        # Distinct timestamps: the buffer stamps each add() individually,
        # and the digest's source lineage is keyed by them.
        "timestamp": time.time() + next(_ITEM_COUNTER) * 1e-3,
        "metadata": metadata,
        "namespace": "buffer",
        "embedding": None,
    }


def _make_working_memory(max_memory_mb) -> WorkingMemory:
    return WorkingMemory(formation_id=FORMATION_ID, max_size=10, max_memory_mb=max_memory_mb)


class TestWorkingMemoryEvictionListener:
    def test_listener_unset_by_default(self):
        wm = _make_working_memory(max_memory_mb=1000)
        assert wm._eviction_listener is None
        # Cleanup with no listener behaves exactly as before (inert pin).
        wm.buffer.append(_buffer_item("hello"))
        wm.check_memory_usage_and_cleanup()
        assert len(wm.buffer) == 1

    def test_threshold_trigger_fires_before_eviction(self):
        # ~2000 bytes of buffer text; limit 0.004 MB, threshold 0.25
        # -> usage is above the flush threshold but below the eviction limit.
        wm = _make_working_memory(max_memory_mb=0.004)
        received = []
        wm.set_eviction_listener(received.extend, flush_threshold=0.25)
        for index in range(4):
            wm.buffer.append(_buffer_item("x" * 500 + f" {index}"))

        wm.check_memory_usage_and_cleanup()

        # Oldest ~25% handed over; nothing evicted.
        assert len(received) == 1
        assert received[0]["text"].endswith(" 0")
        assert len(wm.buffer) == 4

    def test_eviction_safety_net_hands_off_unflushed_items(self):
        wm = _make_working_memory(max_memory_mb=0.0001)  # force eviction
        received = []
        wm.set_eviction_listener(received.extend)  # no threshold: safety net only
        for index in range(4):
            wm.buffer.append(_buffer_item("y" * 500 + f" {index}"))

        wm.check_memory_usage_and_cleanup()

        # 25% of 4 items = the oldest one, snapshotted then evicted.
        assert len(received) == 1
        assert received[0]["text"].endswith(" 0")
        assert len(wm.buffer) == 3
        assert all(not item["text"].endswith(" 0") for item in wm.buffer)

    def test_items_never_flush_twice(self):
        wm = _make_working_memory(max_memory_mb=0.004)
        received = []
        wm.set_eviction_listener(received.extend, flush_threshold=0.25)
        for index in range(4):
            wm.buffer.append(_buffer_item("z" * 500 + f" {index}"))

        wm.check_memory_usage_and_cleanup()
        wm.check_memory_usage_and_cleanup()  # same threshold crossing again

        assert len(received) == 1  # marked _memory_flushed after the first pass

    def test_listener_failure_never_breaks_cleanup(self):
        wm = _make_working_memory(max_memory_mb=0.0001)

        def exploding_listener(items):
            raise RuntimeError("listener boom")

        wm.set_eviction_listener(exploding_listener, flush_threshold=0.5)
        for index in range(4):
            wm.buffer.append(_buffer_item("w" * 500 + f" {index}"))

        wm.check_memory_usage_and_cleanup()  # must not raise
        assert len(wm.buffer) == 3  # eviction still proceeded

    def test_non_buffer_namespaces_are_never_handed_over(self):
        wm = _make_working_memory(max_memory_mb=0.0001)
        received = []
        wm.set_eviction_listener(received.extend, flush_threshold=0.1)
        knowledge = _buffer_item("k" * 500)
        knowledge["namespace"] = "knowledge"
        wm.buffer.append(knowledge)
        wm.buffer.append(_buffer_item("b" * 2000))

        wm.check_memory_usage_and_cleanup()

        assert received
        assert all(item["text"].startswith("b") for item in received)


class TestGrouping:
    def test_groups_items_per_user_with_roles(self):
        items = [
            _buffer_item("hello", role="user", user_id="u1"),
            _buffer_item("hi there", role="assistant", user_id="u1"),
            _buffer_item("other user", role="user", user_id="u2"),
            _buffer_item("raw note", role=None, user_id="u2"),
            _buffer_item("   ", role="user", user_id="u3"),  # empty text skipped
        ]
        grouped = _group_items_by_user(items)

        assert set(grouped) == {"u1", "u2"}
        assert [text for _, text in grouped["u1"]] == ["User: hello", "Assistant: hi there"]
        assert [text for _, text in grouped["u2"]] == ["User: other user", "raw note"]
        # Timestamp keys are parseable epoch seconds (buffer_item lineage keys).
        for timestamp_key, _ in grouped["u1"]:
            float(timestamp_key)

    def test_missing_user_id_defaults_to_single_user_scope(self):
        item = _buffer_item("anonymous")
        del item["metadata"]["user_id"]
        grouped = _group_items_by_user([item])
        assert set(grouped) == {"0"}


class TestFlushService:
    def test_defaults_match_prd(self, captains_log):
        service = PreCompactionFlushService(captains_log)
        assert service.enabled is True
        assert service.flush_threshold == DEFAULT_FLUSH_THRESHOLD

    async def test_disabled_flush_stays_inert(self, captains_log):
        wm = _make_working_memory(max_memory_mb=1000)
        service = PreCompactionFlushService(captains_log, {"flush_enabled": False})
        service.attach(wm, lambda: FakeModel())
        assert service.enabled is False
        assert wm._eviction_listener is None

    async def test_attach_requires_both_sides(self, captains_log):
        wm = _make_working_memory(max_memory_mb=1000)
        service = PreCompactionFlushService(None)
        service.attach(wm, lambda: FakeModel())
        assert wm._eviction_listener is None

        attached = PreCompactionFlushService(captains_log)
        attached.attach(wm, lambda: FakeModel())
        assert wm._eviction_listener is not None

    async def test_flush_items_digests_through_captains_log(self, captains_log):
        service = PreCompactionFlushService(captains_log)
        model = FakeModel()
        service._model_getter = lambda: model

        totals = await service.flush_items(
            [
                _buffer_item("We are launching MUXI next month", role="user"),
                _buffer_item("Noted - exciting launch!", role="assistant"),
            ]
        )

        assert totals["entries"] == 1
        assert model.calls == 1
        entries = await captains_log.get_history("u1", include_sources=True)
        assert len(entries) == 1
        assert "MUXI" in entries[0]["summary"]
        # Source lineage carries the buffer timestamp keys.
        assert len(entries[0]["sources"]) == 2
        # The digest's graph facts landed in the knowledge graph too.
        entities = await captains_log.knowledge_graph.storage.list_entities("u1")
        assert any(entity["name"] == "MUXI" for entity in entities)

    async def test_flush_without_model_is_a_noop(self, captains_log):
        service = PreCompactionFlushService(captains_log)
        service._model_getter = lambda: None
        totals = await service.flush_items([_buffer_item("hello")])
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}
        assert await captains_log.get_history("u1") == []

    async def test_digest_failure_is_isolated_per_user(self, captains_log):
        service = PreCompactionFlushService(captains_log)
        model = FakeModel(response=RuntimeError("llm down"))
        service._model_getter = lambda: model

        totals = await service.flush_items([_buffer_item("hello")])  # must not raise
        assert totals["entries"] == 0

    async def test_end_to_end_flush_survives_eviction(self, captains_log):
        """Items evicted from the buffer live on in the captain's log."""
        wm = _make_working_memory(max_memory_mb=0.0001)  # force eviction
        model = FakeModel()
        service = PreCompactionFlushService(captains_log)
        service.attach(wm, lambda: model)

        fact = "We are launching MUXI next month. " + "pad " * 200
        wm.buffer.append(_buffer_item(fact, role="user"))
        wm.buffer.append(_buffer_item("Got it!", role="assistant"))

        wm.check_memory_usage_and_cleanup()  # evicts the oldest item
        await asyncio.sleep(0.2)  # let the scheduled silent turn run

        assert model.calls == 1
        entries = await captains_log.get_history("u1")
        assert len(entries) == 1
        assert "MUXI" in entries[0]["summary"]
        # And the evicted item really left the buffer.
        assert all(not item["text"].startswith("We are launching") for item in wm.buffer)


class TestCaptainsLogDigestTurns:
    async def test_digest_turns_requires_enabled_service_and_model(self, db_manager):
        service = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        totals = await service.digest_turns("u1", [("1.0", "User: hi")], FakeModel())
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}

    async def test_digest_turns_failure_returns_zero_counts(self, captains_log):
        totals = await captains_log.digest_turns(
            "u1", [("1.0", "User: hi")], FakeModel(response=RuntimeError("boom"))
        )
        assert totals == {"entries": 0, "sources": 0, "lessons": 0}
