"""Unit tests for the structured adapter's pure logic (no formation boot).

The formation-backed paths are exercised by the harness fixture runs;
these tests pin the retrieval mapping logic with stubbed KG / log
storage.
"""

from types import SimpleNamespace

import pytest

from bench.memory.datasets import Question
from bench.memory.structured_adapter import StructuredMemoryAdapter


class _StubLogStorage:
    def __init__(self, entries):
        self.entries = entries

    async def list_entries(self, user_id, limit=10, date_from=None, date_to=None):
        return self.entries[:limit]


class _StubGraphStorage:
    async def list_entities(self, user_id, status=None, limit=100, entity_type=None):
        return []

    async def list_relationships(self, user_id, status=None, limit=200, **kwargs):
        return []


def _structured_adapter(log_entries, log_sources):
    adapter = StructuredMemoryAdapter(mode="structured")
    adapter.overlord = SimpleNamespace(
        captains_log=SimpleNamespace(storage=_StubLogStorage(log_entries)),
        knowledge_graph=SimpleNamespace(storage=_StubGraphStorage()),
    )
    adapter._log_sources = log_sources
    return adapter


def _question(date_from, date_to):
    return Question(
        question_id="q1",
        question="What happened?",
        answer="things",
        question_type="narrative_recall",
        date_from=date_from,
        date_to=date_to,
    )


class TestConstruction:
    def test_structured_mode_accepted(self):
        adapter = StructuredMemoryAdapter(mode="structured")
        assert adapter.mode == "structured"

    def test_vector_modes_still_accepted(self):
        assert StructuredMemoryAdapter(mode="combined").mode == "combined"

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError, match="Unknown mode"):
            StructuredMemoryAdapter(mode="kg-routing")


class TestLogSearch:
    @pytest.mark.asyncio
    async def test_multiple_dates_same_session_get_distinct_turn_ids(self):
        # One session sourcing TWO log entries on different dates: the
        # synthetic turn ids must be date-qualified, otherwise the
        # RRF/dedup key collapses them and the later date's narrative
        # text is silently dropped (false miss for that date's question).
        entries = [
            {"date": "2026-03-02", "summary": "second day", "decisions": ["ship it"]},
            {"date": "2026-03-01", "summary": "first day", "decisions": ["plan it"]},
        ]
        adapter = _structured_adapter(
            entries, {"2026-03-01": ["case_s01"], "2026-03-02": ["case_s01"]}
        )
        items = await adapter._search_log(
            "user", _question("2026-03-01", "2026-03-02"), fetch_limit=10
        )
        turn_ids = [item.turn_id for item in items]
        assert len(turn_ids) == len(set(turn_ids)) == 2
        assert set(turn_ids) == {"case_s01:log:2026-03-02", "case_s01:log:2026-03-01"}

    @pytest.mark.asyncio
    async def test_both_dates_survive_fused_search(self):
        entries = [
            {"date": "2026-03-02", "summary": "second day", "decisions": []},
            {"date": "2026-03-01", "summary": "first day", "decisions": []},
        ]
        adapter = _structured_adapter(
            entries, {"2026-03-01": ["case_s01"], "2026-03-02": ["case_s01"]}
        )
        items = await adapter.search_question(
            "user", _question("2026-03-01", "2026-03-02"), fetch_limit=10
        )
        texts = " ".join(item.text for item in items)
        assert "first day" in texts
        assert "second day" in texts

    @pytest.mark.asyncio
    async def test_synthetic_ids_never_collide_with_real_turns(self):
        entries = [{"date": "2026-03-01", "summary": "day", "decisions": []}]
        adapter = _structured_adapter(entries, {"2026-03-01": ["case_s01"]})
        items = await adapter._search_log(
            "user", _question("2026-03-01", "2026-03-01"), fetch_limit=10
        )
        # Real evidence turn ids are "{session_id}:{index}" with a numeric
        # index; the log id's ":log:" segment cannot match one.
        assert items[0].turn_id.startswith("case_s01:log:")

    @pytest.mark.asyncio
    async def test_no_date_window_skips_log(self):
        adapter = _structured_adapter(
            [{"date": "2026-03-01", "summary": "day", "decisions": []}],
            {"2026-03-01": ["case_s01"]},
        )
        assert await adapter._search_log("user", _question(None, None), 10) == []
