"""GDPR / selective-forgetting tests (Memory Substrate Phase 2d).

Deletion is a write: forgetting a source soft-deletes its events
(reversible during the grace period), records the user.deletion audit
event, and a rebuild recomputes projections as if the source was never
imported. The hard-purge worker later removes the soft-deleted rows.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.events import KnowledgeGraphProjector, MemoryEventService
from muxi.runtime.services.memory.graph.service import KnowledgeGraphService
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "gdpr-test-formation"
USER = "u1"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/gdpr.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def events(db_manager):
    return MemoryEventService(db_manager, FORMATION_ID)


@pytest.fixture
def graph(db_manager, events):
    service = KnowledgeGraphService(db_manager, FORMATION_ID, event_log=events)
    events.register_projector(KnowledgeGraphProjector(service))
    return service


def extraction(company):
    return {
        "entities": [{"name": company, "type": "company", "confidence": 0.9}],
        "relationships": [],
    }


async def seed_two_sources(graph):
    """Facts from a chat turn and from an imported source (gmail)."""
    await graph.store_extraction(USER, extraction("Acme"), source="interaction")
    await graph.store_extraction(USER, extraction("MailCorp"), source="gmail")


class TestForgetAndRebuild:
    async def test_rebuild_after_forget_removes_derived_state(self, events, graph):
        await seed_two_sources(graph)
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is not None

        result = await events.forget_source(USER, "gmail", reason="gdpr")
        assert result["deleted_events"] == 1
        assert "knowledge_graph" in result["rebuild_required"]

        await events.rebuild(USER, projection="knowledge_graph")

        # The gmail-derived fact is gone; the interaction fact survives.
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is None
        assert await graph.storage.get_entity(USER, "company", "Acme") is not None

    async def test_deletion_is_reversible_during_grace_period(self, events, graph):
        """Un-forgetting = clearing the soft delete; the next rebuild
        restores the derived state (the PRD's grace-period undo)."""
        await seed_two_sources(graph)
        await events.forget_source(USER, "gmail", reason="user_request")
        await events.rebuild(USER, projection="knowledge_graph")
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is None

        # Undo within the grace period: the event content is intact.
        deleted = await events.list_events(USER, source="gmail", include_deleted=True)
        assert len(deleted) == 1 and deleted[0]["deleted_at"] is not None
        from sqlalchemy import text

        with events.db_manager.engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE memory_events SET deleted_at = NULL, deleted_reason = NULL "
                    "WHERE id = :id"
                ),
                {"id": deleted[0]["id"]},
            )
            conn.commit()

        await events.rebuild(USER, projection="knowledge_graph")
        assert await graph.storage.get_entity(USER, "company", "MailCorp") is not None

    async def test_audit_trail_event_recorded(self, events, graph):
        await seed_two_sources(graph)
        await events.forget_source(USER, "gmail", reason="gdpr")
        audit = await events.list_events(USER, event_types=["user.deletion"])
        assert len(audit) == 1
        assert audit[0]["payload"]["reason"] == "gdpr"
        assert audit[0]["payload"]["source"] == "gmail"
        assert len(audit[0]["payload"]["target_event_ids"]) == 1

    async def test_hard_purge_removes_after_grace_period(self, events, graph):
        await seed_two_sources(graph)
        await events.forget_source(USER, "gmail", reason="gdpr")

        # Inside the grace period: nothing purged.
        assert await events.run_hard_purge() == 0

        # Age the soft delete past the grace period.
        from sqlalchemy import text

        cutoff = utc_now_naive() - timedelta(days=events.grace_period_days + 1)
        with events.db_manager.engine.connect() as conn:
            conn.execute(
                text("UPDATE memory_events SET deleted_at = :ts WHERE deleted_at IS NOT NULL"),
                {"ts": cutoff},
            )
            conn.commit()

        assert await events.run_hard_purge() == 1
        remaining = await events.list_events(USER, include_deleted=True)
        assert all(e["source"] != "gmail" for e in remaining)
