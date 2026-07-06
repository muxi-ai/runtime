"""Unit tests for Memory Revamp Phase 2: captain's log storage round-trips.

Covers entry upserts keyed by (user, date), source lineage idempotency and
DAG cycle rejection, the log-derivation edge iterator, and the lessons
lifecycle (dedup-by-hash confirmation, applied bookkeeping, confidence
decay with archive threshold, and over-cap scope detection).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.log.models import (
    SOURCE_TYPE_BUFFER_ITEM,
    SOURCE_TYPE_LOG_ENTRY,
)
from muxi.runtime.services.memory.log.storage import (
    CONFIRMATION_CONFIDENCE_BUMP,
    CaptainsLogStorage,
    LessonStorage,
    normalize_rule,
    rule_hash,
)
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "log-test-formation"

TODAY = date(2026, 7, 6)
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def db_manager(tmp_path):
    """File-backed SQLite DatabaseManager (sync + async engines share it)."""
    manager = DatabaseManager(f"sqlite:///{tmp_path}/log.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def storage(db_manager):
    return CaptainsLogStorage(db_manager, FORMATION_ID)


@pytest.fixture
def lessons(db_manager):
    return LessonStorage(db_manager, FORMATION_ID)


class TestEntryRoundTrips:
    async def test_insert_and_get(self, storage):
        created = await storage.upsert_entry(
            "u1",
            TODAY,
            summary="Finalized memory PRD",
            decisions=["KG over flat facts"],
            projects=["MUXI"],
            context="No infra gaps",
        )
        assert created["id"] > 0
        assert created["date"] == TODAY.isoformat()

        fetched = await storage.get_entry("u1", TODAY)
        assert fetched == created

    async def test_upsert_updates_same_date(self, storage):
        first = await storage.upsert_entry("u1", TODAY, summary="Morning summary")
        second = await storage.upsert_entry("u1", TODAY, summary="Merged summary", decisions=["D1"])
        assert second["id"] == first["id"]
        assert second["summary"] == "Merged summary"
        assert second["decisions"] == ["D1"]
        assert len(await storage.list_entries("u1")) == 1

    async def test_get_entry_by_public_id(self, storage):
        created = await storage.upsert_entry("u1", TODAY, summary="S")
        fetched = await storage.get_entry_by_public_id("u1", created["public_id"])
        assert fetched["id"] == created["id"]
        assert await storage.get_entry_by_public_id("u2", created["public_id"]) is None

    async def test_list_newest_first_with_date_filters(self, storage):
        await storage.upsert_entry("u1", YESTERDAY, summary="Old")
        await storage.upsert_entry("u1", TODAY, summary="New")

        entries = await storage.list_entries("u1")
        assert [e["summary"] for e in entries] == ["New", "Old"]

        only_old = await storage.list_entries("u1", date_to=YESTERDAY)
        assert [e["summary"] for e in only_old] == ["Old"]

        only_new = await storage.list_entries("u1", date_from=TODAY)
        assert [e["summary"] for e in only_new] == ["New"]

    async def test_user_isolation(self, storage):
        await storage.upsert_entry("u1", TODAY, summary="Mine")
        await storage.upsert_entry("u2", TODAY, summary="Theirs")
        assert [e["summary"] for e in await storage.list_entries("u1")] == ["Mine"]
        assert [e["summary"] for e in await storage.list_entries("u2")] == ["Theirs"]


class TestSourceLineage:
    async def test_add_and_get_sources(self, storage):
        entry = await storage.upsert_entry("u1", TODAY, summary="S")
        counts = await storage.add_sources(
            "u1",
            entry["id"],
            [
                {"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": "100.1"},
                {"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": "100.2"},
            ],
        )
        assert counts == {"added": 2, "skipped": 0, "rejected": 0}

        sources = await storage.get_sources(entry["id"])
        assert [s["source_id"] for s in sources] == ["100.1", "100.2"]

    async def test_duplicate_sources_skipped(self, storage):
        entry = await storage.upsert_entry("u1", TODAY, summary="S")
        payload = [{"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": "100.1"}]
        await storage.add_sources("u1", entry["id"], payload)
        counts = await storage.add_sources("u1", entry["id"], payload)
        assert counts == {"added": 0, "skipped": 1, "rejected": 0}
        assert len(await storage.get_sources(entry["id"])) == 1

    async def test_invalid_sources_rejected(self, storage):
        entry = await storage.upsert_entry("u1", TODAY, summary="S")
        counts = await storage.add_sources(
            "u1",
            entry["id"],
            [
                {"source_type": "unknown_type", "source_id": "x"},
                {"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": ""},
            ],
        )
        assert counts == {"added": 0, "skipped": 0, "rejected": 2}

    async def test_log_entry_sources_form_dag_edges(self, storage):
        old = await storage.upsert_entry("u1", YESTERDAY, summary="Old")
        new = await storage.upsert_entry("u1", TODAY, summary="New")
        counts = await storage.add_sources(
            "u1",
            new["id"],
            [{"source_type": SOURCE_TYPE_LOG_ENTRY, "source_id": str(old["id"])}],
        )
        assert counts["added"] == 1
        assert await storage.iter_log_edges("u1") == [(old["id"], new["id"])]

    async def test_cycle_creating_edge_rejected(self, storage):
        old = await storage.upsert_entry("u1", YESTERDAY, summary="Old")
        new = await storage.upsert_entry("u1", TODAY, summary="New")
        await storage.add_sources(
            "u1",
            new["id"],
            [{"source_type": SOURCE_TYPE_LOG_ENTRY, "source_id": str(old["id"])}],
        )
        # The reverse edge would close a cycle: rejected, never written.
        counts = await storage.add_sources(
            "u1",
            old["id"],
            [{"source_type": SOURCE_TYPE_LOG_ENTRY, "source_id": str(new["id"])}],
        )
        assert counts["rejected"] == 1
        assert await storage.iter_log_edges("u1") == [(old["id"], new["id"])]

    async def test_self_edge_rejected(self, storage):
        entry = await storage.upsert_entry("u1", TODAY, summary="S")
        counts = await storage.add_sources(
            "u1",
            entry["id"],
            [{"source_type": SOURCE_TYPE_LOG_ENTRY, "source_id": str(entry["id"])}],
        )
        assert counts["rejected"] == 1

    async def test_log_edges_scoped_per_user(self, storage):
        mine_old = await storage.upsert_entry("u1", YESTERDAY, summary="Old")
        mine_new = await storage.upsert_entry("u1", TODAY, summary="New")
        theirs = await storage.upsert_entry("u2", TODAY, summary="Other")
        await storage.add_sources(
            "u1",
            mine_new["id"],
            [{"source_type": SOURCE_TYPE_LOG_ENTRY, "source_id": str(mine_old["id"])}],
        )
        await storage.add_sources(
            "u2",
            theirs["id"],
            [{"source_type": SOURCE_TYPE_BUFFER_ITEM, "source_id": "1.0"}],
        )
        assert await storage.iter_log_edges("u1") == [(mine_old["id"], mine_new["id"])]
        assert await storage.iter_log_edges("u2") == []


class TestLessonUpserts:
    async def test_insert_and_list(self, lessons):
        lesson, created = await lessons.upsert_lesson(
            "u1", "assistant", "Prefer reportlab over fpdf", context="PDF generation"
        )
        assert created is True
        assert lesson["confidence"] == 0.5
        assert lesson["hits"] == 1
        assert lesson["rule_hash"] == rule_hash("Prefer reportlab over fpdf")

        listed = await lessons.list_active("u1")
        assert [item["id"] for item in listed] == [lesson["id"]]

    async def test_duplicate_is_confirmation(self, lessons):
        first, _ = await lessons.upsert_lesson("u1", "assistant", "Prefer reportlab over fpdf")
        second, created = await lessons.upsert_lesson(
            "u1", "assistant", "  prefer   REPORTLAB over fpdf  "
        )
        assert created is False
        assert second["id"] == first["id"]
        assert second["hits"] == 2
        assert second["confidence"] == pytest.approx(0.5 + CONFIRMATION_CONFIDENCE_BUMP)

    async def test_confirmation_confidence_capped(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Rule", confidence=0.95)
        confirmed, _ = await lessons.upsert_lesson("u1", "assistant", "Rule", confidence=0.95)
        assert confirmed["confidence"] == 1.0

    async def test_confirmation_revives_archived(self, lessons):
        lesson, _ = await lessons.upsert_lesson("u1", "assistant", "Rule")
        await lessons.archive_lessons([lesson["id"]])
        assert await lessons.list_active("u1") == []

        revived, created = await lessons.upsert_lesson("u1", "assistant", "Rule")
        assert created is False
        assert revived["archived"] is False
        assert len(await lessons.list_active("u1")) == 1

    async def test_scope_isolation(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Rule")
        await lessons.upsert_lesson("u1", "researcher", "Rule")
        await lessons.upsert_lesson("u2", "assistant", "Rule")

        assert len(await lessons.list_active("u1")) == 2
        assert len(await lessons.list_active("u1", agent_id="assistant")) == 1
        assert len(await lessons.list_active("u2")) == 1

    async def test_list_ordering_and_limit(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Low", confidence=0.3)
        await lessons.upsert_lesson("u1", "assistant", "High", confidence=0.9)
        await lessons.upsert_lesson("u1", "assistant", "Mid", confidence=0.6)

        listed = await lessons.list_active("u1", limit=2)
        assert [item["rule"] for item in listed] == ["High", "Mid"]

    async def test_mark_applied(self, lessons):
        lesson, _ = await lessons.upsert_lesson("u1", "assistant", "Rule")
        await lessons.mark_applied([lesson["id"]])
        listed = await lessons.list_active("u1")
        assert listed[0]["last_applied_at"] is not None

    async def test_mark_applied_empty_noop(self, lessons):
        await lessons.mark_applied([])  # must not raise


class TestLessonDecay:
    async def test_recent_lessons_not_decayed(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Fresh rule")
        counts = await lessons.run_decay(0.05, 0.2)
        assert counts == {"decayed": 0, "archived": 0}

    async def test_stale_lesson_decays_pro_rata(self, lessons):
        lesson, _ = await lessons.upsert_lesson("u1", "assistant", "Stale rule")
        future = utc_now_naive() + timedelta(days=30)
        counts = await lessons.run_decay(0.05, 0.2, now=future)
        assert counts["decayed"] == 1
        assert counts["archived"] == 0

        listed = await lessons.list_active("u1")
        assert listed[0]["confidence"] == pytest.approx(0.45, abs=0.005)
        assert listed[0]["decayed_at"] is not None

    async def test_decay_below_threshold_archives(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Weak rule", confidence=0.21)
        future = utc_now_naive() + timedelta(days=30)
        counts = await lessons.run_decay(0.05, 0.2, now=future)
        assert counts == {"decayed": 1, "archived": 1}
        assert await lessons.list_active("u1") == []

    async def test_zero_decay_rate_is_noop(self, lessons):
        await lessons.upsert_lesson("u1", "assistant", "Rule")
        future = utc_now_naive() + timedelta(days=365)
        assert await lessons.run_decay(0.0, 0.2, now=future) == {"decayed": 0, "archived": 0}


class TestScopesOverCap:
    async def test_detects_only_scopes_over_cap(self, lessons):
        for index in range(3):
            await lessons.upsert_lesson("u1", "assistant", f"Rule {index}")
        await lessons.upsert_lesson("u1", "researcher", "Solo rule")

        assert await lessons.scopes_over_cap(2) == [("u1", "assistant", 3)]
        assert await lessons.scopes_over_cap(3) == []


class TestRuleNormalization:
    def test_normalize_rule(self):
        assert normalize_rule("  Prefer   X\nover Y ") == "prefer x over y"

    def test_rule_hash_stable_across_formatting(self):
        assert rule_hash("Prefer X over Y") == rule_hash("  prefer   x OVER y ")
        assert rule_hash("Prefer X over Y") != rule_hash("Prefer Y over X")
        assert len(rule_hash("anything")) == 64
