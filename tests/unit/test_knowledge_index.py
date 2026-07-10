"""Unit tests for Memory Revamp Phase 4: KnowledgeIndexService.

Covers the empty/disabled read paths (failure-isolated ""), rendering of
every section (entities, captain's log span, artifacts via the artifact
service seam, lint-findings gaps), the size cap with count-of-omitted
truncation, caching plus each regeneration trigger (log entry, artifact
save, entity count threshold, lint invalidation, 24h staleness),
system_config persistence of both the blob and the lint findings, and the
enabled: false inertness pin at the initialization seam.
"""

from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.services.memory.index import (
    DEFAULT_ENTITY_COUNT_THRESHOLD,
    DEFAULT_MAX_TOKENS,
    INDEX_KEY_FORMAT,
    KnowledgeIndexService,
)
from muxi.runtime.services.memory.log.service import CaptainsLogService

FORMATION_ID = "index-test-formation"
USER = "u1"


class FakeArtifactMemory:
    """Artifact-service seam double: the manifest the index rides."""

    def __init__(self, artifacts=None):
        self.enabled = True
        self.artifacts = artifacts if artifacts is not None else []

    async def list_artifacts(self, user_id, **kwargs):
        return list(self.artifacts)


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/index.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def graph(db_manager):
    return KnowledgeGraphService(db_manager, FORMATION_ID)


@pytest.fixture
def captains_log(db_manager, graph):
    return CaptainsLogService(db_manager, FORMATION_ID, knowledge_graph=graph)


@pytest.fixture
def artifact_memory():
    return FakeArtifactMemory(
        [
            {
                "name": "Q1 Strategy Report",
                "content_type": "application/pdf",
                "created_at": "2026-03-28T10:00:00",
                "last_accessed_at": "2026-03-28T10:00:00",
            }
        ]
    )


@pytest.fixture
def index(db_manager, graph, captains_log, artifact_memory):
    return KnowledgeIndexService(
        db_manager,
        FORMATION_ID,
        knowledge_graph=graph,
        captains_log=captains_log,
        artifact_memory=artifact_memory,
    )


async def _seed_entity(graph, name="Automaze", entity_type="company"):
    await graph.storage.upsert_entity(
        user_id=USER, entity_type=entity_type, name=name, confidence=0.9
    )


async def _seed_log_entry(captains_log, entry_date, summary="Finalized the memory PRD"):
    await captains_log.storage.upsert_entry(USER, entry_date, summary=summary)


class TestConfig:
    def test_defaults_match_prd(self, index):
        assert index.enabled is True
        assert index.max_tokens == DEFAULT_MAX_TOKENS
        assert index.max_chars == DEFAULT_MAX_TOKENS * 4
        assert index.entity_count_threshold == DEFAULT_ENTITY_COUNT_THRESHOLD
        assert index.regenerate_on == {
            "artifact_save",
            "entity_count_threshold",
            "lint",
            "log_entry",
        }

    def test_disabled_index_returns_empty(self, db_manager, graph):
        disabled = KnowledgeIndexService(
            db_manager, FORMATION_ID, config={"enabled": False}, knowledge_graph=graph
        )
        assert disabled.enabled is False


class TestReadPath:
    async def test_empty_store_renders_nothing(self, db_manager, graph, captains_log):
        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=FakeArtifactMemory([]),
        )
        assert await index.get_index_block(USER) == ""

    async def test_disabled_returns_empty_even_with_data(
        self, db_manager, graph, captains_log, artifact_memory
    ):
        await _seed_entity(graph)
        disabled = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"enabled": False},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=artifact_memory,
        )
        assert await disabled.get_index_block(USER) == ""

    async def test_blob_renders_all_sections(self, index, graph, captains_log):
        await _seed_entity(graph, "Automaze", "company")
        await _seed_entity(graph, "London", "location")
        await _seed_log_entry(captains_log, date(2026, 1, 15))
        await _seed_log_entry(captains_log, date(2026, 4, 3), summary="Memory PRD finalised")
        await index.set_lint_findings(USER, ["stale entity 'Berlin office'"])

        block = await index.get_index_block(USER)

        assert block.startswith("[Memory Index - as of ")
        assert "Entities (2):" in block
        assert "Automaze (Company)" in block
        assert "Captain's Log: 2 entries spanning 2026-01-15 - 2026-04-03" in block
        assert "Most recent: Memory PRD finalised" in block
        # Artifact manifest (artifact-memory Phase 2 shape).
        assert "Artifacts (1):" in block
        assert "Q1 Strategy Report (pdf) by overlord | 2026-03-28" in block
        assert "Knowledge gaps flagged by last lint: stale entity 'Berlin office'" in block

    async def test_read_failure_returns_empty(self, index, monkeypatch):
        async def explode(user_id):
            raise RuntimeError("db down")

        monkeypatch.setattr(index, "_fingerprint", explode)
        assert await index.get_index_block(USER) == ""


class TestArtifactManifest:
    """The artifact section renders the PRD 2.1 manifest shape and cap."""

    @staticmethod
    def _manifest_row(i: int, agent: str = "finance-agent") -> dict:
        return {
            "public_id": f"artifact-id-{i:03d}",
            "name": f"Report {i:03d}",
            "version": i + 1,
            "content_type": "text/markdown",
            "agent_id": agent,
            "summary": f"Quarterly analysis number {i}",
            "created_at": "2026-07-01T10:00:00",
            "updated_at": "2026-07-02T10:00:00",
            "last_accessed_at": "2026-07-03T10:00:00",
        }

    async def test_manifest_line_carries_id_version_agent_and_summary(
        self, db_manager, graph, captains_log
    ):
        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"max_tokens": 2000},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=FakeArtifactMemory([self._manifest_row(0)]),
        )
        block = await index.get_index_block(USER)
        assert (
            "- artifact-id-000 v1 | Report 000 (markdown) by finance-agent | 2026-07-03 "
            "-- Quarterly analysis number 0"
        ) in block

    async def test_manifest_caps_at_20_with_retrieval_pointer(
        self, db_manager, graph, captains_log
    ):
        rows = [self._manifest_row(i) for i in range(25)]
        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"max_tokens": 5000},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=FakeArtifactMemory(rows),
        )
        block = await index.get_index_block(USER)
        assert "Artifacts (25):" in block
        assert "artifact-id-019" in block
        assert "artifact-id-020" not in block  # beyond the 20-entry cap
        assert "... and 5 more. Use get_artifact to search." in block

    async def test_manifest_uses_service_manifest_ordering(self, db_manager, graph, captains_log):
        """When the artifact service exposes list_manifest (the real Phase 2
        surface), the index uses it with the configured cap."""

        calls = {}

        class ManifestFake(FakeArtifactMemory):
            async def list_manifest(self, user_id, limit):
                calls["limit"] = limit
                return self.artifacts[:limit]

            async def count_artifacts(self, user_id):
                return len(self.artifacts)

        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"max_tokens": 2000, "artifact_cap": 3},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=ManifestFake([self._manifest_row(i) for i in range(5)]),
        )
        block = await index.get_index_block(USER)
        assert calls["limit"] == 3
        assert "Artifacts (5):" in block
        assert "... and 2 more. Use get_artifact to search." in block


class TestSizeCap:
    async def test_blob_never_exceeds_max_tokens(
        self, db_manager, graph, captains_log, artifact_memory
    ):
        small = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"max_tokens": 100},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=artifact_memory,
        )
        for i in range(30):
            await _seed_entity(graph, f"Very Long Entity Name Number {i:02d}", "project")
        await _seed_log_entry(captains_log, date(2026, 4, 3), summary="S" * 300)
        await small.set_lint_findings(USER, [f"finding number {i}" for i in range(10)])

        block = await small.get_index_block(USER)

        assert block
        assert len(block) <= small.max_chars

    async def test_truncation_reports_omitted_count(self, index, graph):
        for i in range(30):
            await _seed_entity(graph, f"Entity With A Reasonably Long Name {i:02d}", "topic")

        block = await index.get_index_block(USER)

        assert "Entities (30):" in block
        assert "more]" in block  # "[+N more]" marker with the omitted count


class TestCachingAndRegeneration:
    async def test_unchanged_store_serves_cached_blob(self, index, graph):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        second = await index.get_index_block(USER)
        assert second is first  # identity: cache hit, no re-render

    async def test_new_log_entry_triggers_regeneration(self, index, graph, captains_log):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        await _seed_log_entry(captains_log, date(2026, 4, 3))
        second = await index.get_index_block(USER)
        assert second is not first
        assert "Captain's Log: 1 entries" in second

    async def test_artifact_save_triggers_regeneration(self, index, graph, artifact_memory):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        artifact_memory.artifacts.append(
            {"name": "New Diagram", "content_type": "image/png", "created_at": "2026-04-05"}
        )
        second = await index.get_index_block(USER)
        assert second is not first
        assert "New Diagram" in second

    async def test_entity_growth_below_threshold_keeps_cache(self, index, graph):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        await _seed_entity(graph, "One More", "topic")  # +1 < threshold (10)
        second = await index.get_index_block(USER)
        assert second is first

    async def test_entity_count_threshold_triggers_regeneration(
        self, db_manager, graph, captains_log, artifact_memory
    ):
        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"entity_count_threshold": 2},
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=artifact_memory,
        )
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        await _seed_entity(graph, "Second", "topic")
        await _seed_entity(graph, "Third", "topic")
        second = await index.get_index_block(USER)
        assert second is not first
        assert "Entities (3):" in second

    async def test_lint_invalidation_triggers_regeneration(self, index, graph):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        await index.set_lint_findings(USER, ["missing relationship for 'Sarah Chen'"])
        second = await index.get_index_block(USER)
        assert second is not first
        assert "missing relationship for 'Sarah Chen'" in second

    async def test_stale_blob_regenerates_after_24h(self, index, graph):
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        index._cache[USER]["generated_at"] = time.time() - 90_000  # > 24h ago
        second = await index.get_index_block(USER)
        assert second is not first

    async def test_disabled_triggers_are_respected(
        self, db_manager, graph, captains_log, artifact_memory
    ):
        index = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            config={"regenerate_on": ["lint"]},  # log_entry trigger off
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=artifact_memory,
        )
        await _seed_entity(graph)
        first = await index.get_index_block(USER)
        await _seed_log_entry(captains_log, date(2026, 4, 3))
        second = await index.get_index_block(USER)
        assert second is first  # log change ignored by config


class TestPersistence:
    async def test_blob_persisted_in_system_config(self, index, graph, db_manager):
        await _seed_entity(graph)
        block = await index.get_index_block(USER)

        from muxi.runtime.services.memory.artifacts.models import SystemConfig

        async with db_manager.get_async_session() as session:
            row = await session.get(SystemConfig, INDEX_KEY_FORMAT.format(user_id=USER))
        assert row is not None
        assert row.value == block

    async def test_lint_findings_survive_service_restart(
        self, index, db_manager, graph, captains_log, artifact_memory
    ):
        await index.set_lint_findings(USER, ["captain's log gap: 12 days"])

        reborn = KnowledgeIndexService(
            db_manager,
            FORMATION_ID,
            knowledge_graph=graph,
            captains_log=captains_log,
            artifact_memory=artifact_memory,
        )
        assert await reborn.get_lint_findings(USER) == ["captain's log gap: 12 days"]


class TestInitializationSeam:
    def test_initialize_skips_without_sources(self, db_manager):
        from muxi.runtime.formation.initialization import _initialize_memory_index

        formation = SimpleNamespace(
            _db_manager=db_manager,
            _knowledge_graph=None,
            _captains_log=None,
            _artifact_memory=None,
            formation_id=FORMATION_ID,
        )
        _initialize_memory_index(formation, {})
        assert formation._memory_index is None

    def test_initialize_disabled_pin(self, db_manager, graph):
        from muxi.runtime.formation.initialization import _initialize_memory_index

        formation = SimpleNamespace(
            _db_manager=db_manager,
            _knowledge_graph=graph,
            _captains_log=None,
            _artifact_memory=None,
            formation_id=FORMATION_ID,
        )
        _initialize_memory_index(formation, {"enabled": False})
        assert formation._memory_index is None

    def test_initialize_with_sources(self, db_manager, graph):
        from muxi.runtime.formation.initialization import _initialize_memory_index

        formation = SimpleNamespace(
            _db_manager=db_manager,
            _knowledge_graph=graph,
            _captains_log=None,
            _artifact_memory=None,
            formation_id=FORMATION_ID,
        )
        _initialize_memory_index(formation, {"max_tokens": 200})
        assert formation._memory_index is not None
        assert formation._memory_index.max_tokens == 200
