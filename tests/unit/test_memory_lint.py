"""Unit tests for Memory Revamp Phase 5: MemoryLintService.

Covers config/cadence resolution, the background-loop lifecycle, every
audit check -- unresolved-conflict detection (entities and relationships,
produced through the real contradiction-detection write path), superseded
hard-deletion past the retention window, orphaned-relationship cleanup
(gated by orphan_cleanup), captain's log gap flagging, stale artifact
flagging, forced index regeneration -- the findings write-back into the
Phase 4 index, per-user failure isolation, and the inertness pin: no
``memory.lint`` block means no service is constructed at all.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.models import (
    STATUS_CONFLICTED,
    STATUS_SUPERSEDED,
    KGEntity,
    KGRelationship,
)
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.index import KnowledgeIndexService
from muxi.runtime.services.memory.lint import (
    DEFAULT_CONFLICT_RESOLUTION_DAYS,
    DEFAULT_STALE_ARTIFACT_DAYS,
    MemoryLintService,
    _schedule_to_seconds,
)
from muxi.runtime.services.memory.log.service import CaptainsLogService
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "lint-test-formation"
USER = "u1"


class FakeArtifactMemory:
    def __init__(self, artifacts=None):
        self.enabled = True
        self.artifacts = artifacts if artifacts is not None else []

    async def list_artifacts(self, user_id, **kwargs):
        return list(self.artifacts)


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/lint.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def graph(db_manager):
    return KnowledgeGraphService(db_manager, FORMATION_ID)


@pytest.fixture
def captains_log(db_manager, graph):
    return CaptainsLogService(db_manager, FORMATION_ID, knowledge_graph=graph)


def _lint(db_manager, config=None, **services) -> MemoryLintService:
    return MemoryLintService(db_manager, FORMATION_ID, config=config or {}, **services)


async def _backdate_graph_rows(db_manager, days: int) -> None:
    """Push every graph row's updated_at into the past."""
    stamp = utc_now_naive() - timedelta(days=days)
    async with db_manager.get_async_session() as session:
        await session.execute(update(KGEntity).values(updated_at=stamp))
        await session.execute(update(KGRelationship).values(updated_at=stamp))


async def _seed_conflicted_relationship(graph) -> None:
    """Create a real conflict through the contradiction-detection path."""
    person = await graph.storage.upsert_entity(
        user_id=USER, entity_type="person", name="Ran", confidence=0.9
    )
    london = await graph.storage.upsert_entity(
        user_id=USER, entity_type="location", name="London", confidence=0.9
    )
    berlin = await graph.storage.upsert_entity(
        user_id=USER, entity_type="location", name="Berlin", confidence=0.9
    )
    # lives_in is exclusive: a second object at similar confidence marks
    # both edges conflicted instead of silently overriding.
    await graph.storage.upsert_relationship(
        user_id=USER,
        from_entity_id=person["id"],
        to_entity_id=london["id"],
        rel_type="lives_in",
        confidence=0.9,
    )
    await graph.storage.upsert_relationship(
        user_id=USER,
        from_entity_id=person["id"],
        to_entity_id=berlin["id"],
        rel_type="lives_in",
        confidence=0.9,
    )


class TestConfig:
    def test_defaults_match_prd(self, db_manager):
        service = _lint(db_manager)
        assert service.enabled is True
        assert service.interval_seconds == 604800  # "weekly"
        assert service.conflict_resolution_days == DEFAULT_CONFLICT_RESOLUTION_DAYS
        assert service.orphan_cleanup is True
        assert service.stale_artifact_days == DEFAULT_STALE_ARTIFACT_DAYS

    def test_schedule_resolution(self):
        assert _schedule_to_seconds("daily") == 86400
        assert _schedule_to_seconds("weekly") == 604800
        assert _schedule_to_seconds(2) == 2.0
        assert _schedule_to_seconds("bogus") == 604800  # falls back to weekly

    def test_unconfigured_formation_gets_no_lint_service(self, db_manager):
        """Inertness pin: no memory.lint block -> no service constructed."""
        from muxi.runtime.formation.initialization import _initialize_memory_lint

        formation = SimpleNamespace(
            _db_manager=db_manager,
            _knowledge_graph=None,
            _captains_log=None,
            _artifact_memory=None,
            _memory_index=None,
            formation_id=FORMATION_ID,
        )
        _initialize_memory_lint(formation, None)  # memory.lint absent
        assert formation._memory_lint is None

        _initialize_memory_lint(formation, {"enabled": False})
        assert formation._memory_lint is None

        _initialize_memory_lint(formation, {"schedule": "daily"})
        assert formation._memory_lint is not None
        assert formation._memory_lint.interval_seconds == 86400


class TestLifecycle:
    async def test_loop_starts_and_stops(self, db_manager):
        service = _lint(db_manager, config={"schedule": 3600})
        service.start()
        assert service._task is not None and not service._task.done()
        service.start()  # idempotent
        await service.stop()
        assert service._task is None

    async def test_disabled_service_never_starts(self, db_manager):
        service = _lint(db_manager, config={"enabled": False})
        service.start()
        assert service._task is None

    async def test_loop_survives_run_failures(self, db_manager, monkeypatch):
        service = _lint(db_manager, config={"schedule": 0.01})

        calls = []

        async def failing_run(user_id=None):
            calls.append(1)
            raise RuntimeError("audit boom")

        monkeypatch.setattr(service, "run_lint", failing_run)
        service.start()
        await asyncio.sleep(0.08)
        await service.stop()
        assert len(calls) >= 2  # kept running after the failure


class TestConflictDetection:
    async def test_unresolved_conflicts_are_flagged_after_threshold(self, db_manager, graph):
        await _seed_conflicted_relationship(graph)
        await _backdate_graph_rows(db_manager, days=10)

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["unresolved_conflicts"] == 2  # both lives_in edges
        findings = report["findings"][USER]
        assert any("Ran -[lives_in]-> London" in finding for finding in findings)
        assert any("Ran -[lives_in]-> Berlin" in finding for finding in findings)

    async def test_fresh_conflicts_are_not_flagged_yet(self, db_manager, graph):
        await _seed_conflicted_relationship(graph)  # updated_at = now

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["unresolved_conflicts"] == 0

    async def test_conflicted_entities_are_flagged(self, db_manager, graph):
        await graph.storage.upsert_entity(
            user_id=USER, entity_type="location", name="Berlin office", confidence=0.9
        )
        async with db_manager.get_async_session() as session:
            await session.execute(
                update(KGEntity)
                .where(KGEntity.name == "Berlin office")
                .values(
                    status=STATUS_CONFLICTED,
                    updated_at=utc_now_naive() - timedelta(days=30),
                )
            )

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["unresolved_conflicts"] == 1
        assert "Berlin office" in report["findings"][USER][0]


class TestSupersededPurge:
    async def test_old_superseded_facts_are_hard_deleted(self, db_manager, graph):
        entity = await graph.storage.upsert_entity(
            user_id=USER, entity_type="location", name="Old Home", confidence=0.5
        )
        keeper = await graph.storage.upsert_entity(
            user_id=USER, entity_type="person", name="Ran", confidence=0.9
        )
        await graph.storage.upsert_relationship(
            user_id=USER,
            from_entity_id=keeper["id"],
            to_entity_id=entity["id"],
            rel_type="lives_in",
            confidence=0.5,
        )
        async with db_manager.get_async_session() as session:
            await session.execute(
                update(KGEntity)
                .where(KGEntity.id == entity["id"])
                .values(
                    status=STATUS_SUPERSEDED,
                    updated_at=utc_now_naive() - timedelta(days=60),
                )
            )

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["superseded_deleted"] == 1
        entities = await graph.storage.list_entities(USER, status=None)
        assert all(e["name"] != "Old Home" for e in entities)
        # The edge referencing the purged entity went with it.
        assert await graph.storage.list_relationships(USER) == []

    async def test_recent_superseded_facts_are_retained(self, db_manager, graph):
        entity = await graph.storage.upsert_entity(
            user_id=USER, entity_type="location", name="Recent Move", confidence=0.5
        )
        async with db_manager.get_async_session() as session:
            await session.execute(
                update(KGEntity)
                .where(KGEntity.id == entity["id"])
                .values(status=STATUS_SUPERSEDED)  # updated now
            )

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["superseded_deleted"] == 0
        entities = await graph.storage.list_entities(USER, status=None)
        assert any(e["name"] == "Recent Move" for e in entities)

    async def test_superseded_relationship_with_superseded_endpoint(self, db_manager, graph):
        """The overlap case: a superseded edge whose endpoint entity is also
        superseded must purge cleanly (the old ORM-delete loop double-deleted
        the edge and made the session flush raise StaleDataError)."""
        old_home = await graph.storage.upsert_entity(
            user_id=USER, entity_type="location", name="Old Home", confidence=0.5
        )
        person = await graph.storage.upsert_entity(
            user_id=USER, entity_type="person", name="Ran", confidence=0.9
        )
        relationship = await graph.storage.upsert_relationship(
            user_id=USER,
            from_entity_id=person["id"],
            to_entity_id=old_home["id"],
            rel_type="lives_in",
            confidence=0.5,
        )
        stamp = utc_now_naive() - timedelta(days=60)
        async with db_manager.get_async_session() as session:
            await session.execute(
                update(KGEntity)
                .where(KGEntity.id == old_home["id"])
                .values(status=STATUS_SUPERSEDED, updated_at=stamp)
            )
            await session.execute(
                update(KGRelationship)
                .where(KGRelationship.id == relationship["id"])
                .values(status=STATUS_SUPERSEDED, updated_at=stamp)
            )

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)  # must not raise

        # One superseded relationship + one superseded entity purged.
        assert report["superseded_deleted"] == 2
        entities = await graph.storage.list_entities(USER, status=None)
        assert all(e["name"] != "Old Home" for e in entities)
        assert await graph.storage.list_relationships(USER) == []
        # The failure previously surfaced as a silently skipped user: the
        # per-user catch swallowed the StaleDataError. A counted user pins
        # that the pass really ran.
        assert report["users"] == 1


class TestOrphanCleanup:
    async def _seed_orphan(self, db_manager, graph) -> None:
        left = await graph.storage.upsert_entity(
            user_id=USER, entity_type="person", name="Left", confidence=0.9
        )
        right = await graph.storage.upsert_entity(
            user_id=USER, entity_type="company", name="Right", confidence=0.9
        )
        await graph.storage.upsert_relationship(
            user_id=USER,
            from_entity_id=left["id"],
            to_entity_id=right["id"],
            rel_type="works_at",
            confidence=0.9,
        )
        # Delete one endpoint out from under the edge.
        from sqlalchemy import delete

        async with db_manager.get_async_session() as session:
            await session.execute(delete(KGEntity).where(KGEntity.id == right["id"]))

    async def test_orphaned_relationships_are_removed(self, db_manager, graph):
        await self._seed_orphan(db_manager, graph)

        service = _lint(db_manager, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["orphans_removed"] == 1
        assert await graph.storage.list_relationships(USER) == []

    async def test_orphan_cleanup_can_be_disabled(self, db_manager, graph):
        await self._seed_orphan(db_manager, graph)

        service = _lint(db_manager, config={"orphan_cleanup": False}, knowledge_graph=graph)
        report = await service.run_lint(user_id=USER)

        assert report["orphans_removed"] == 0
        assert len(await graph.storage.list_relationships(USER)) == 1


class TestLogGapsAndArtifacts:
    async def test_log_gaps_are_flagged(self, db_manager, captains_log):
        await captains_log.storage.upsert_entry(USER, date(2026, 1, 1), summary="a")
        await captains_log.storage.upsert_entry(USER, date(2026, 1, 20), summary="b")
        await captains_log.storage.upsert_entry(USER, date(2026, 1, 24), summary="c")

        service = _lint(db_manager, captains_log=captains_log)
        report = await service.run_lint(user_id=USER)

        assert report["log_gaps"] == 1
        assert "19 days between 2026-01-01 and 2026-01-20" in report["findings"][USER][0]

    async def test_stale_artifacts_are_flagged(self, db_manager, captains_log):
        stale_stamp = (utc_now_naive() - timedelta(days=120)).isoformat()
        fresh_stamp = utc_now_naive().isoformat()
        artifact_memory = FakeArtifactMemory(
            [
                {"name": "Old Report", "last_accessed_at": stale_stamp},
                {"name": "Fresh Diagram", "last_accessed_at": fresh_stamp},
            ]
        )

        service = _lint(db_manager, captains_log=captains_log, artifact_memory=artifact_memory)
        # The user has to exist somewhere for the all-users sweep; scope
        # directly instead.
        report = await service.run_lint(user_id=USER)

        assert report["stale_artifacts"] == 1
        assert "Old Report" in report["findings"][USER][0]
        assert all("Fresh Diagram" not in f for f in report["findings"][USER])

    async def test_tz_aware_timestamps_never_abort_the_lint_pass(self, db_manager, captains_log):
        """tz-aware ISO stamps must normalize instead of raising TypeError
        (which the per-user catch would turn into a silently skipped user)."""
        stale_aware = (utc_now_naive() - timedelta(days=120)).isoformat() + "+00:00"
        fresh_aware = utc_now_naive().isoformat() + "+00:00"
        artifact_memory = FakeArtifactMemory(
            [
                {"name": "Aware Old Report", "last_accessed_at": stale_aware},
                {"name": "Aware Fresh Diagram", "last_accessed_at": fresh_aware},
                {"name": "Broken Stamp", "last_accessed_at": "not-a-date"},
            ]
        )

        service = _lint(db_manager, captains_log=captains_log, artifact_memory=artifact_memory)
        report = await service.run_lint(user_id=USER)  # must not raise

        assert report["users"] == 1  # the user's pass completed
        assert report["stale_artifacts"] == 1
        assert "Aware Old Report" in report["findings"][USER][0]


class TestIndexIntegration:
    async def test_findings_feed_the_knowledge_index(self, db_manager, graph, captains_log):
        index = KnowledgeIndexService(
            db_manager, FORMATION_ID, knowledge_graph=graph, captains_log=captains_log
        )
        await _seed_conflicted_relationship(graph)
        await _backdate_graph_rows(db_manager, days=10)

        service = _lint(db_manager, knowledge_graph=graph, captains_log=captains_log, index=index)
        report = await service.run_lint(user_id=USER)

        # Lint regenerates the index unconditionally after the findings
        # write-back (set_lint_findings invalidates the cached blob).
        assert report["index_regenerated"] == 1
        findings = await index.get_lint_findings(USER)
        assert findings == report["findings"][USER]

        block = await index.get_index_block(USER)
        assert "Knowledge gaps flagged by last lint:" in block
        assert "lives_in" in block

    async def test_lint_regenerates_even_a_fresh_index(self, db_manager, graph, captains_log):
        """Pins the always-regenerate-after-lint decision: lint is weekly
        and regeneration is cheap, so no staleness gate applies."""
        index = KnowledgeIndexService(
            db_manager, FORMATION_ID, knowledge_graph=graph, captains_log=captains_log
        )
        await graph.storage.upsert_entity(
            user_id=USER, entity_type="person", name="Ran", confidence=0.9
        )
        assert await index.get_index_block(USER)  # cache is warm and fresh

        service = _lint(db_manager, knowledge_graph=graph, captains_log=captains_log, index=index)
        report = await service.run_lint(user_id=USER)

        assert report["index_regenerated"] == 1

    async def test_all_users_sweep_discovers_users_from_rows(self, db_manager, graph, captains_log):
        await graph.storage.upsert_entity(
            user_id="alpha", entity_type="person", name="A", confidence=0.9
        )
        await captains_log.storage.upsert_entry("beta", date(2026, 1, 1), summary="b")

        service = _lint(db_manager, knowledge_graph=graph, captains_log=captains_log)
        report = await service.run_lint()

        assert report["users"] == 2

    async def test_per_user_failure_is_isolated(self, db_manager, graph, monkeypatch):
        await graph.storage.upsert_entity(
            user_id="alpha", entity_type="person", name="A", confidence=0.9
        )
        await graph.storage.upsert_entity(
            user_id="beta", entity_type="person", name="B", confidence=0.9
        )

        service = _lint(db_manager, knowledge_graph=graph)
        original = service._lint_user

        async def flaky(user_id):
            if user_id == "alpha":
                raise RuntimeError("user boom")
            return await original(user_id)

        monkeypatch.setattr(service, "_lint_user", flaky)
        report = await service.run_lint()  # must not raise

        assert report["users"] == 1  # beta audited despite alpha's failure
