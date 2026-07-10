"""Unit tests for the recall_history built-in tool (episodic memory).

Covers tool registration gating (inert without an enabled captain's log
service), the tool definition shape, date-range filtering (single day,
open-ended, swapped bounds), keyword filtering, limit clamping, user
isolation, invalid-date rejection, and failure isolation (handlers return
friendly errors, never raise).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from muxi.runtime.formation.agents.recall_dispatch import (
    build_recall_tools,
    handle_recall_history,
    recall_tools_available,
)
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.log.service import CaptainsLogService

FORMATION_ID = "recall-tool-test"


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/recall.db")
    manager.create_tables(Base.metadata)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def service(db_manager):
    return CaptainsLogService(db_manager, FORMATION_ID)


@pytest.fixture
def overlord(service):
    """The only seam the handler uses: overlord.captains_log."""
    return SimpleNamespace(captains_log=service)


async def seed_entries(service, user_id="alice"):
    """Three dated entries for one user, oldest first."""
    await service.storage.upsert_entry(
        user_id,
        date(2026, 7, 6),
        summary="Kicked off the Bluebird project.",
        decisions=["Use PostgreSQL"],
        projects=["Bluebird"],
        context="Project kickoff.",
    )
    await service.storage.upsert_entry(
        user_id,
        date(2026, 7, 7),
        summary="Reviewed the launch checklist.",
        decisions=["Ship on Friday"],
        projects=["Bluebird"],
        context="Launch planning.",
    )
    await service.storage.upsert_entry(
        user_id,
        date(2026, 7, 8),
        summary="Discussed the marketing plan.",
        decisions=[],
        projects=["Marketing"],
        context="Campaign ideas.",
    )


class TestGating:
    def test_available_with_enabled_service(self, overlord):
        assert recall_tools_available(overlord) is True

    def test_unavailable_without_service(self):
        assert recall_tools_available(SimpleNamespace()) is False
        assert recall_tools_available(SimpleNamespace(captains_log=None)) is False

    def test_unavailable_when_disabled(self, db_manager):
        disabled = CaptainsLogService(db_manager, FORMATION_ID, config={"enabled": False})
        assert recall_tools_available(SimpleNamespace(captains_log=disabled)) is False

    async def test_handler_friendly_error_without_service(self):
        result = await handle_recall_history("agent", {}, SimpleNamespace(), user_id="alice")
        assert result["success"] is False
        assert "not available" in result["error"]


class TestToolDefinition:
    def test_shape(self):
        tools = build_recall_tools()
        assert len(tools) == 1
        function = tools[0]["function"]
        assert function["name"] == "recall_history"
        properties = function["parameters"]["properties"]
        assert set(properties) == {"date_from", "date_to", "query", "limit"}
        # Every parameter is optional: the model may recall recent history
        # without a date anchor.
        assert "required" not in function["parameters"]
        assert "YYYY-MM-DD" in function["description"]


class TestDateFiltering:
    async def test_single_day_range(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent",
            {"date_from": "2026-07-07", "date_to": "2026-07-07"},
            overlord,
            user_id="alice",
        )
        assert result["success"] is True
        assert [entry["date"] for entry in result["entries"]] == ["2026-07-07"]
        assert result["entries"][0]["summary"] == "Reviewed the launch checklist."
        assert result["entries"][0]["decisions"] == ["Ship on Friday"]

    async def test_range_returns_newest_first(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent",
            {"date_from": "2026-07-06", "date_to": "2026-07-08"},
            overlord,
            user_id="alice",
        )
        assert [entry["date"] for entry in result["entries"]] == [
            "2026-07-08",
            "2026-07-07",
            "2026-07-06",
        ]

    async def test_open_ended_from(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent", {"date_from": "2026-07-08"}, overlord, user_id="alice"
        )
        assert [entry["date"] for entry in result["entries"]] == ["2026-07-08"]

    async def test_swapped_bounds_are_normalized(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent",
            {"date_from": "2026-07-08", "date_to": "2026-07-06"},
            overlord,
            user_id="alice",
        )
        assert result["count"] == 3

    async def test_empty_range_returns_hint(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent",
            {"date_from": "2025-01-01", "date_to": "2025-01-31"},
            overlord,
            user_id="alice",
        )
        assert result["success"] is True
        assert result["count"] == 0
        assert "widening" in result["message"]

    @pytest.mark.parametrize("field", ["date_from", "date_to"])
    async def test_invalid_date_rejected_with_field_name(self, service, overlord, field):
        result = await handle_recall_history(
            "agent", {field: "last Tuesday"}, overlord, user_id="alice"
        )
        assert result["success"] is False
        assert field in result["error"]
        assert "YYYY-MM-DD" in result["error"]


class TestQueryAndLimit:
    async def test_query_filters_lexically(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent", {"query": "marketing"}, overlord, user_id="alice"
        )
        assert [entry["date"] for entry in result["entries"]] == ["2026-07-08"]

    async def test_query_matches_decisions(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history(
            "agent", {"query": "ship on friday"}, overlord, user_id="alice"
        )
        assert [entry["date"] for entry in result["entries"]] == ["2026-07-07"]

    async def test_limit_clamped(self, service, overlord):
        await seed_entries(service)
        result = await handle_recall_history("agent", {"limit": 1}, overlord, user_id="alice")
        assert result["count"] == 1
        result = await handle_recall_history("agent", {"limit": 0}, overlord, user_id="alice")
        assert result["count"] >= 1  # clamped up to 1
        result = await handle_recall_history(
            "agent", {"limit": "not a number"}, overlord, user_id="alice"
        )
        assert result["success"] is True


class TestUserIsolation:
    async def test_other_users_entries_invisible(self, service, overlord):
        await seed_entries(service, user_id="alice")
        result = await handle_recall_history("agent", {}, overlord, user_id="bob")
        assert result["success"] is True
        assert result["count"] == 0

    async def test_missing_user_defaults_to_single_user_scope(self, service, overlord):
        await seed_entries(service, user_id="0")
        result = await handle_recall_history("agent", {}, overlord, user_id=None)
        assert result["count"] == 3


class TestFailureIsolation:
    async def test_storage_error_returns_friendly_error(self, service, overlord, monkeypatch):
        async def boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(service, "get_history", boom)
        result = await handle_recall_history("agent", {}, overlord, user_id="alice")
        assert result["success"] is False
        assert "db down" in result["error"]
