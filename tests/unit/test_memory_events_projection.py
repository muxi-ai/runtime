"""Incremental projection tests for the Memory Event Substrate (Phase 2b).

Covers the per-(projection, user) cursor contract: ``project_pending``
applies only events past the cursor (idempotent re-projection), cursor
resume across passes, the event-first write posture (append + substrate
apply, no direct projection write), the cursor tail snapshot that guards
dual-written history, and the artifact-metadata projector's
wipe-and-replay.
"""

from __future__ import annotations

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.artifacts.models import Artifact  # noqa: F401 -- registers table
from muxi.runtime.services.memory.artifacts.storage import ArtifactMemoryStorage
from muxi.runtime.services.memory.events import (
    ArtifactMetadataProjector,
    FlatFactProjector,
    KnowledgeGraphProjector,
    MemoryEventService,
)
from muxi.runtime.services.memory.events.models import EVENT_FACT_EXTRACTED
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService

FORMATION_ID = "projection-test-formation"
USER = "u1"


class FakeLongTermMemory:
    """Vector-store double implementing the flat-fact projection contract."""

    def __init__(self):
        self.rows = {}
        self._counter = 0

    async def add(self, content, metadata=None, user_id=None, collection=None, scope=None):
        self._counter += 1
        memory_id = f"m{self._counter}"
        self.rows[memory_id] = {
            "content": content,
            "metadata": dict(metadata or {}),
            "user_id": str(user_id),
            "collection": collection,
            "scope": scope,
        }
        return memory_id

    async def delete_extracted_memories(self, user_id):
        doomed = [
            memory_id
            for memory_id, row in self.rows.items()
            if row["user_id"] == str(user_id)
            and (
                row["metadata"].get("source") == "extraction"
                or row["metadata"].get("derived_from_event_id") is not None
            )
        ]
        for memory_id in doomed:
            del self.rows[memory_id]
        return len(doomed)


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/projection.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


async def record_fact(events, memory, user_id=USER, **kwargs):
    return await events.record(
        user_id=user_id,
        event_type=EVENT_FACT_EXTRACTED,
        payload={
            "memory": memory,
            "collection": "preferences",
            "metadata": {"source": "extraction"},
        },
        source="interaction",
        **kwargs,
    )


class TestProjectPending:
    async def test_applies_pending_and_advances_cursor(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        first = await record_fact(events, "Likes tea")
        second = await record_fact(events, "Likes scones")

        report = await events.project_pending(USER)
        assert report["flat_facts"][USER] == {"events": 2, "applied": 2, "failed": 0}
        assert len(long_term.rows) == 2

        checkpoint = await events.storage.get_checkpoint("flat_facts", USER)
        assert checkpoint["last_event_id"] == second["id"]
        assert first["id"] < second["id"]

    async def test_second_pass_applies_nothing(self, events):
        """Idempotent re-projection: the cursor gates re-application."""
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        await record_fact(events, "Likes tea")

        await events.project_pending(USER)
        report = await events.project_pending(USER)
        assert report == {}  # nothing pending
        assert len(long_term.rows) == 1

    async def test_cursor_resume_applies_only_new_events(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        await record_fact(events, "Likes tea")
        await events.project_pending(USER)

        await record_fact(events, "Likes scones")
        report = await events.project_pending(USER)
        assert report["flat_facts"][USER]["events"] == 1
        assert len(long_term.rows) == 2

    async def test_discovers_users_without_explicit_id(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        await record_fact(events, "Likes tea", user_id="u1")
        await record_fact(events, "Likes coffee", user_id="u2")

        report = await events.project_pending()
        assert set(report["flat_facts"]) == {"u1", "u2"}

    async def test_poison_event_is_skipped_and_cursor_advances(self, events, monkeypatch):
        long_term = FakeLongTermMemory()
        projector = FlatFactProjector(long_term)
        events.register_projector(projector)
        poison = await record_fact(events, "poison")
        good = await record_fact(events, "good")

        original_apply = projector.apply

        async def flaky_apply(event):
            if event["id"] == poison["id"]:
                raise RuntimeError("projector exploded")
            return await original_apply(event)

        monkeypatch.setattr(projector, "apply", flaky_apply)
        report = await events.project_pending(USER)
        assert report["flat_facts"][USER] == {"events": 2, "applied": 1, "failed": 1}
        checkpoint = await events.storage.get_checkpoint("flat_facts", USER)
        assert checkpoint["last_event_id"] == good["id"]  # not wedged


class TestChunkedProjectPending:
    """Bounded lock holds: project_pending applies events in chunks of
    ``memory.projections.batch_size`` per lock acquisition, checkpointing
    every chunk. No event is skipped or duplicated across chunk
    boundaries, and a crash between chunks resumes from the last
    checkpointed boundary."""

    @pytest.fixture
    def chunked_events(self, db_manager):
        return MemoryEventService(db_manager, FORMATION_ID, projections_config={"batch_size": 2})

    async def test_all_events_applied_exactly_once_across_chunks(self, chunked_events):
        events = chunked_events
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        recorded = [await record_fact(events, f"Fact {index}") for index in range(5)]

        report = await events.project_pending(USER)
        assert report["flat_facts"][USER] == {"events": 5, "applied": 5, "failed": 0}
        # Exactly once each: 5 rows, 5 distinct contents.
        assert sorted(row["content"] for row in long_term.rows.values()) == [
            f"Fact {index}" for index in range(5)
        ]
        checkpoint = await events.storage.get_checkpoint("flat_facts", USER)
        assert checkpoint["last_event_id"] == recorded[-1]["id"]

        # Nothing pending on a second pass.
        assert await events.project_pending(USER) == {}

    async def test_crash_between_chunks_resumes_without_skip_or_duplicate(
        self, chunked_events, monkeypatch
    ):
        events = chunked_events
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        recorded = [await record_fact(events, f"Fact {index}") for index in range(5)]

        # Crash the pass at the second chunk's read -- AFTER chunk one
        # was applied and checkpointed, BEFORE chunk two touched anything.
        original_list_events = events.storage.list_events
        calls = {"count": 0}

        async def crashing_list_events(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("process died between chunks")
            return await original_list_events(*args, **kwargs)

        monkeypatch.setattr(events.storage, "list_events", crashing_list_events)
        with pytest.raises(RuntimeError, match="between chunks"):
            await events.project_pending(USER)

        # Chunk one landed and was checkpointed at the chunk boundary.
        assert len(long_term.rows) == 2
        checkpoint = await events.storage.get_checkpoint("flat_facts", USER)
        assert checkpoint["last_event_id"] == recorded[1]["id"]

        # Recovery pass: only the remaining events apply -- none skipped,
        # none re-applied.
        monkeypatch.undo()
        report = await events.project_pending(USER)
        assert report["flat_facts"][USER] == {"events": 3, "applied": 3, "failed": 0}
        assert sorted(row["content"] for row in long_term.rows.values()) == [
            f"Fact {index}" for index in range(5)
        ]

    async def test_lock_released_between_chunks(self, chunked_events):
        """The projection lock is free between chunks, so a concurrent
        writer acquires it mid-batch instead of waiting for the tail."""
        events = chunked_events
        long_term = FakeLongTermMemory()
        projector = FlatFactProjector(long_term)
        events.register_projector(projector)
        for index in range(6):
            await record_fact(events, f"Fact {index}")

        import asyncio

        rows_seen_under_lock = []

        async def contender():
            # Queued behind the running pass; asyncio.Lock is FIFO, so
            # this wakes at the first chunk boundary -- mid-batch --
            # rather than after the whole batch (the old monolithic hold).
            async with events._projection_lock:
                rows_seen_under_lock.append(len(long_term.rows))

        pending_task = asyncio.create_task(events.project_pending(USER))
        await asyncio.sleep(0)  # let the pass take the lock first
        contender_task = asyncio.create_task(contender())
        await asyncio.wait_for(asyncio.gather(pending_task, contender_task), timeout=5.0)

        assert len(long_term.rows) == 6
        # The contender got the lock while the batch was still running.
        assert 0 < rows_seen_under_lock[0] < 6

    async def test_batch_size_config_validation(self, db_manager):
        with pytest.raises(ValueError, match="memory.projections.batch_size"):
            MemoryEventService(db_manager, FORMATION_ID, projections_config={"batch_size": 0})
        with pytest.raises(ValueError, match="memory.projections.batch_size"):
            MemoryEventService(db_manager, FORMATION_ID, projections_config={"batch_size": "lots"})
        service = MemoryEventService(db_manager, FORMATION_ID)
        assert service.project_batch_size == 500  # documented default


class TestApplyEvent:
    async def test_apply_event_projects_and_checkpoints(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        event = await record_fact(events, "Likes tea")

        assert await events.apply_event(event)
        assert len(long_term.rows) == 1
        checkpoint = await events.storage.get_checkpoint("flat_facts", USER)
        assert checkpoint["last_event_id"] == event["id"]

    async def test_apply_event_is_idempotent_behind_cursor(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        event = await record_fact(events, "Likes tea")

        await events.apply_event(event)
        assert await events.apply_event(event) is True  # cursor skip
        assert len(long_term.rows) == 1

    async def test_apply_event_without_projector_is_noop(self, events):
        turn = await events.record(
            user_id=USER,
            event_type="interaction.turn",
            payload={"user_message": "hello"},
            source="interaction",
        )
        assert await events.apply_event(turn) is True

    async def test_apply_failure_leaves_cursor_for_retry(self, events, monkeypatch):
        long_term = FakeLongTermMemory()
        projector = FlatFactProjector(long_term)
        events.register_projector(projector)
        event = await record_fact(events, "Likes tea")

        async def broken_apply(_event):
            raise RuntimeError("down")

        monkeypatch.setattr(projector, "apply", broken_apply)
        assert await events.apply_event(event) is None
        assert await events.storage.get_checkpoint("flat_facts", USER) is None

        # The background applier's pass recovers the event.
        monkeypatch.undo()
        report = await events.project_pending(USER)
        assert report["flat_facts"][USER]["applied"] == 1


class TestCursorSnapshot:
    async def test_snapshot_guards_dual_written_history(self, events):
        """Dual-written events are never re-applied after a cutover."""
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        # Simulate dual-write history: events exist AND rows were written
        # directly (here: one row, one event, no cursor).
        await record_fact(events, "Likes tea")
        await long_term.add(
            content="Likes tea",
            metadata={"source": "extraction"},
            user_id=USER,
            collection="preferences",
        )

        await events.snapshot_cursors_to_tail()
        report = await events.project_pending(USER)
        assert report == {}  # history skipped, no duplicate row
        assert len(long_term.rows) == 1

    async def test_snapshot_leaves_existing_cursors(self, events):
        long_term = FakeLongTermMemory()
        events.register_projector(FlatFactProjector(long_term))
        first = await record_fact(events, "Likes tea")
        await events.storage.set_checkpoint("flat_facts", USER, last_event_id=first["id"])
        await record_fact(events, "Likes scones")

        await events.snapshot_cursors_to_tail()
        report = await events.project_pending(USER)
        # The pre-existing cursor still owns its position: only the second
        # event was pending and it gets applied, not skipped.
        assert report["flat_facts"][USER]["applied"] == 1


class TestEventFirstWrites:
    async def test_graph_event_first_skips_direct_write_but_projects(self, db_manager, tmp_path):
        events = MemoryEventService(db_manager, FORMATION_ID, config={"event_first": True})
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))

        stored = await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Acme", "type": "company", "confidence": 0.9}],
                "relationships": [],
            },
        )
        assert stored == {"entities": 1, "relationships": 0}
        # The projection was derived from the event (synchronous apply)...
        entity = await graph.storage.get_entity(USER, "company", "Acme")
        assert entity is not None
        assert entity["derived_from_event_ids"]  # provenance stamped
        # ...and the cursor advanced, so the applier will not re-apply.
        checkpoint = await events.storage.get_checkpoint("knowledge_graph", USER)
        graph_events = await events.list_events(USER)
        assert checkpoint["last_event_id"] == graph_events[-1]["id"]

    async def test_dual_write_default_unchanged(self, db_manager):
        events = MemoryEventService(db_manager, FORMATION_ID)
        assert events.event_first is False
        graph = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
        events.register_projector(KnowledgeGraphProjector(graph))
        await graph.store_extraction(
            USER,
            {
                "entities": [{"name": "Acme", "type": "company", "confidence": 0.9}],
                "relationships": [],
            },
        )
        # Direct write path: no cursor is created in dual-write mode.
        assert await events.storage.get_checkpoint("knowledge_graph", USER) is None
        assert await graph.storage.get_entity(USER, "company", "Acme") is not None


class TestArtifactMetadataProjector:
    class FakeArtifactService:
        def __init__(self, db_manager):
            self.storage = ArtifactMemoryStorage(db_manager, FORMATION_ID)

        @staticmethod
        def _build_summary(name, content_type, size_bytes, agent_id):
            producer = agent_id or "overlord"
            return f"{name} ({content_type}, {size_bytes} bytes) produced by {producer}."

        def _compute_expiry(self):
            return None

    async def seed(self, events, service):
        """Two versions of one artifact, captured through save + v2 events."""
        for version, checksum in ((1, "a" * 64), (2, "b" * 64)):
            row = await service.storage.save_artifact(
                user_id=USER,
                public_id=f"art_v{version}",
                name="report.pdf",
                content_type="application/pdf",
                summary=f"v{version} summary",
                storage_ref=f"u1/ab/blob{version}.bin",
                size_bytes=1000 + version,
                compressed_bytes=500 + version,
                checksum_sha256=checksum,
            )
            event = await events.record(
                user_id=USER,
                event_type="artifact.saved",
                event_version=2,
                payload={
                    "artifact_id": row["public_id"],
                    "name": row["name"],
                    "version": row["version"],
                    "content_type": row["content_type"],
                    "category": row["category"],
                    "size_bytes": row["size_bytes"],
                    "checksum_sha256": row["checksum_sha256"],
                    "storage_ref": row["storage_ref"],
                    "tags": row["tags"],
                    "summary": row["summary"],
                    "compressed_bytes": row["compressed_bytes"],
                },
                source="artifact_memory",
                source_id=f"artifact/{row['public_id']}",
            )
            await service.storage.set_derived_event(row["id"], event["id"])

    @staticmethod
    def snapshot(rows):
        return sorted(
            (
                r["public_id"],
                r["name"],
                r["version"],
                r["is_latest"],
                r["content_type"],
                r["storage_ref"],
                r["size_bytes"],
                r["compressed_bytes"],
                r["checksum_sha256"],
                r["summary"],
            )
            for r in rows
        )

    async def test_wipe_and_replay_reproduces_metadata(self, db_manager, events):
        service = self.FakeArtifactService(db_manager)
        projector = ArtifactMetadataProjector(service)
        events.register_projector(projector)
        await self.seed(events, service)

        before = self.snapshot(await service.storage.list_artifacts(USER, latest_only=False))
        assert len(before) == 2

        report = await events.rebuild(USER, projection="artifact_metadata")
        assert report["artifact_metadata"] == {"events": 2, "applied": 2, "failed": 0}

        after = self.snapshot(await service.storage.list_artifacts(USER, latest_only=False))
        assert after == before
        # Version chain reconstructed: exactly one latest head.
        latest = await service.storage.list_artifacts(USER, latest_only=True)
        assert len(latest) == 1 and latest[0]["version"] == 2

    async def test_reset_spares_pre_substrate_rows(self, db_manager, events):
        service = self.FakeArtifactService(db_manager)
        projector = ArtifactMetadataProjector(service)
        events.register_projector(projector)
        # A pre-substrate row: no derived_from_event_id.
        await service.storage.save_artifact(
            user_id=USER,
            public_id="art_legacy",
            name="legacy.txt",
            content_type="text/plain",
            summary="legacy",
            storage_ref="u1/aa/legacy.bin",
            size_bytes=10,
            compressed_bytes=5,
            checksum_sha256="c" * 64,
        )
        assert await projector.reset(USER) == 0
        rows = await service.storage.list_artifacts(USER, latest_only=False)
        assert len(rows) == 1  # the legacy row survived

    async def test_v1_event_reconstructs_deterministically(self, db_manager, events):
        service = self.FakeArtifactService(db_manager)
        projector = ArtifactMetadataProjector(service)
        events.register_projector(projector)
        # A v1 event (no summary / compressed_bytes) with no matching row:
        # builders must handle every historical version.
        event = await events.record(
            user_id=USER,
            event_type="artifact.saved",
            payload={
                "artifact_id": "art_old",
                "name": "old.csv",
                "version": 1,
                "content_type": "text/csv",
                "size_bytes": 64,
                "storage_ref": "u1/cc/old.bin",
            },
            source="artifact_memory",
            source_id="artifact/art_old",
        )
        await projector.apply(event)
        row = await service.storage.get_by_public_id(USER, "art_old")
        assert row is not None
        assert row["compressed_bytes"] == 64  # size fallback
        assert "old.csv" in row["summary"]  # deterministic reconstruction
        assert row["derived_from_event_id"] == event["id"]
