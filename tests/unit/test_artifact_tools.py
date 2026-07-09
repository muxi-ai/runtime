"""Unit tests for the artifact retrieval built-in tools (Phase 2).

Covers tool registration gating (inert without an enabled artifact memory
service), get_artifact (id lookup with preview + lexical search),
get_artifact_content (full content, version selection, binary and
truncation guards), get_artifact_history (version chains), cross-user
denial on every tool, last_accessed_at refresh on retrieval, and failure
isolation (handlers return friendly errors, never raise).
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from types import SimpleNamespace

import pytest

from muxi.runtime.datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from muxi.runtime.formation.agents import artifact_dispatch
from muxi.runtime.formation.agents.artifact_dispatch import (
    artifact_tools_available,
    build_artifact_tools,
    handle_get_artifact,
    handle_get_artifact_content,
    handle_get_artifact_history,
)
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.artifacts import ArtifactMemoryService
from muxi.runtime.services.memory.artifacts.models import Artifact, SystemConfig

FORMATION_ID = "artifact-tools-test"
TABLES = [Artifact.__table__, SystemConfig.__table__]


@pytest.fixture
def db_manager(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/artifacts.db")
    manager.create_tables(Base.metadata, tables=TABLES)
    yield manager
    manager.engine.dispose()


@pytest.fixture
def service(db_manager, tmp_path):
    return ArtifactMemoryService(
        db_manager=db_manager,
        formation_id=FORMATION_ID,
        config={"storage": {"type": "local", "path": str(tmp_path / "store")}},
    )


@pytest.fixture
def overlord(service):
    """The only seam the handlers use: overlord.artifact_memory."""
    return SimpleNamespace(artifact_memory=service)


def text_artifact(filename="notes.md", content="# Q1 notes\nRevenue up.") -> MuxiArtifact:
    return MuxiArtifact(
        type="text",
        format=filename.rsplit(".", 1)[-1],
        filename=filename,
        content=content,
        metadata=ArtifactMetadata(size_bytes=len(content), created_at=datetime.now()),
    )


def binary_artifact(filename="chart.png", raw=b"\x89PNG\r\n\x1a\nfakepixels") -> MuxiArtifact:
    payload = base64.b64encode(raw).decode("ascii")
    return MuxiArtifact(
        type="image",
        format=filename.rsplit(".", 1)[-1],
        filename=filename,
        data_url=f"data:image/png;base64,{payload}",
        metadata=ArtifactMetadata(size_bytes=len(raw), created_at=datetime.now()),
    )


async def seed(service, artifact, user_id="u1", agent_id="writer"):
    captured = await service.capture_response_artifacts(
        [artifact], user_id=user_id, agent_id=agent_id
    )
    assert len(captured) == 1
    return captured[0]


class TestRegistrationGating:
    """No enabled artifact memory service means no tools at all."""

    def test_tools_absent_without_service(self):
        assert artifact_tools_available(SimpleNamespace()) is False
        assert artifact_tools_available(SimpleNamespace(artifact_memory=None)) is False

    def test_tools_absent_when_disabled(self):
        disabled = SimpleNamespace(artifact_memory=SimpleNamespace(enabled=False))
        assert artifact_tools_available(disabled) is False

    def test_tools_present_when_enabled(self, overlord):
        assert artifact_tools_available(overlord) is True

    def test_tool_definitions(self):
        tools = build_artifact_tools()
        names = [tool["function"]["name"] for tool in tools]
        assert names == ["get_artifact", "get_artifact_content", "get_artifact_history"]
        content_tool = tools[1]["function"]
        assert content_tool["parameters"]["required"] == ["id"]

    async def test_handlers_report_missing_service(self):
        bare = SimpleNamespace(artifact_memory=None)
        for handler in (
            handle_get_artifact,
            handle_get_artifact_content,
            handle_get_artifact_history,
        ):
            result = await handler("agent", {"id": "x"}, bare, user_id="u1")
            assert result["success"] is False
            assert "not available" in result["error"]


class TestGetArtifact:
    async def test_id_lookup_returns_metadata_and_preview(self, service, overlord):
        row = await seed(service, text_artifact())
        result = await handle_get_artifact(
            "agent", {"id": row["public_id"]}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["artifact"]["id"] == row["public_id"]
        assert result["artifact"]["name"] == "notes.md"
        assert result["artifact"]["agent"] == "writer"
        assert result["content_preview"].startswith("# Q1 notes")

    async def test_id_lookup_refreshes_last_accessed(self, service, overlord):
        row = await seed(service, text_artifact())
        before = row["last_accessed_at"]
        await asyncio.sleep(0.01)
        await handle_get_artifact("agent", {"id": row["public_id"]}, overlord, user_id="u1")
        after = (await service.get_metadata("u1", row["public_id"]))["last_accessed_at"]
        assert after > before

    async def test_cross_user_id_lookup_is_denied(self, service, overlord):
        row = await seed(service, text_artifact(), user_id="u1")
        result = await handle_get_artifact(
            "agent", {"id": row["public_id"]}, overlord, user_id="u2"
        )
        assert result["success"] is False
        assert "No artifact" in result["error"]

    async def test_binary_id_lookup_flags_binary_preview(self, service, overlord):
        row = await seed(service, binary_artifact())
        result = await handle_get_artifact(
            "agent", {"id": row["public_id"]}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["content_preview"] is None
        assert "Binary content" in result["note"]

    async def test_search_matches_name_and_summary(self, service, overlord):
        await seed(service, text_artifact("sales.csv", "month,revenue\njan,100"))
        await seed(service, text_artifact("plan.md", "roadmap"))
        result = await handle_get_artifact("agent", {"query": "sales"}, overlord, user_id="u1")
        assert result["success"] is True
        assert [row["name"] for row in result["artifacts"]] == ["sales.csv"]

    async def test_search_filters_by_category(self, service, overlord):
        await seed(service, text_artifact("notes.md"))
        await seed(service, binary_artifact("chart.png"))
        result = await handle_get_artifact("agent", {"category": "image"}, overlord, user_id="u1")
        assert [row["name"] for row in result["artifacts"]] == ["chart.png"]

    async def test_search_respects_limit(self, service, overlord):
        for i in range(4):
            await seed(service, text_artifact(f"file-{i}.md", f"body {i}"))
        result = await handle_get_artifact("agent", {"limit": 2}, overlord, user_id="u1")
        assert result["count"] == 2

    async def test_search_is_user_scoped(self, service, overlord):
        await seed(service, text_artifact(), user_id="u1")
        result = await handle_get_artifact("agent", {}, overlord, user_id="u2")
        assert result["success"] is True
        assert result["artifacts"] == []

    async def test_service_failure_returns_friendly_error(self, overlord, monkeypatch):
        async def explode(*args, **kwargs):
            raise RuntimeError("store down")

        monkeypatch.setattr(overlord.artifact_memory, "list_artifacts", explode)
        result = await handle_get_artifact("agent", {}, overlord, user_id="u1")
        assert result["success"] is False
        assert "store down" in result["error"]


class TestGetArtifactContent:
    async def test_full_text_content(self, service, overlord):
        row = await seed(service, text_artifact(content="full body text"))
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"]}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["content"] == "full body text"
        assert result["metadata"]["version"] == 1

    async def test_specific_version_content(self, service, overlord):
        await seed(service, text_artifact(content="v1 body"))
        head = await seed(service, text_artifact(content="v2 body"))
        result = await handle_get_artifact_content(
            "agent", {"id": head["public_id"], "version": 1}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["content"] == "v1 body"
        assert result["metadata"]["version"] == 1

    async def test_unknown_version_is_friendly(self, service, overlord):
        row = await seed(service, text_artifact())
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"], "version": 9}, overlord, user_id="u1"
        )
        assert result["success"] is False
        assert "no version 9" in result["error"]

    async def test_binary_content_is_guarded(self, service, overlord):
        row = await seed(service, binary_artifact())
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"]}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["content"] is None
        assert "Binary artifact" in result["note"]

    async def test_oversized_text_is_truncated(self, service, overlord, monkeypatch):
        monkeypatch.setattr(artifact_dispatch, "MAX_CONTENT_CHARS", 10)
        row = await seed(service, text_artifact(content="0123456789ABCDEF"))
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"]}, overlord, user_id="u1"
        )
        assert result["content"] == "0123456789"
        assert result["truncated"] is True

    async def test_cross_user_content_is_denied(self, service, overlord):
        row = await seed(service, text_artifact(), user_id="u1")
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"]}, overlord, user_id="u2"
        )
        assert result["success"] is False

    async def test_missing_id_is_friendly(self, overlord):
        result = await handle_get_artifact_content("agent", {}, overlord, user_id="u1")
        assert result["success"] is False
        assert "requires an artifact id" in result["error"]

    async def test_non_integer_version_is_friendly(self, service, overlord):
        row = await seed(service, text_artifact())
        result = await handle_get_artifact_content(
            "agent", {"id": row["public_id"], "version": "latest"}, overlord, user_id="u1"
        )
        assert result["success"] is False
        assert "version must be an integer" in result["error"]

    async def test_content_read_refreshes_last_accessed(self, service, overlord):
        row = await seed(service, text_artifact())
        before = row["last_accessed_at"]
        await asyncio.sleep(0.01)
        await handle_get_artifact_content("agent", {"id": row["public_id"]}, overlord, user_id="u1")
        after = (await service.get_metadata("u1", row["public_id"]))["last_accessed_at"]
        assert after > before


class TestGetArtifactHistory:
    async def test_history_returns_full_chain(self, service, overlord):
        await seed(service, text_artifact(content="v1"))
        await seed(service, text_artifact(content="v2"))
        head = await seed(service, text_artifact(content="v3"))
        result = await handle_get_artifact_history(
            "agent", {"id": head["public_id"]}, overlord, user_id="u1"
        )
        assert result["success"] is True
        assert result["name"] == "notes.md"
        assert [v["version"] for v in result["versions"]] == [3, 2, 1]
        assert result["versions"][0]["is_latest"] is True
        assert result["versions"][0]["agent"] == "writer"

    async def test_history_resolves_from_any_version(self, service, overlord):
        v1 = await seed(service, text_artifact(content="v1"))
        await seed(service, text_artifact(content="v2"))
        result = await handle_get_artifact_history(
            "agent", {"id": v1["public_id"]}, overlord, user_id="u1"
        )
        assert [v["version"] for v in result["versions"]] == [2, 1]

    async def test_cross_user_history_is_denied(self, service, overlord):
        row = await seed(service, text_artifact(), user_id="u1")
        result = await handle_get_artifact_history(
            "agent", {"id": row["public_id"]}, overlord, user_id="u2"
        )
        assert result["success"] is False

    async def test_missing_id_is_friendly(self, overlord):
        result = await handle_get_artifact_history("agent", {}, overlord, user_id="u1")
        assert result["success"] is False
        assert "requires an artifact id" in result["error"]

    async def test_service_failure_returns_friendly_error(self, overlord, monkeypatch):
        async def explode(*args, **kwargs):
            raise RuntimeError("chain walk failed")

        monkeypatch.setattr(overlord.artifact_memory, "get_history", explode)
        result = await handle_get_artifact_history("agent", {"id": "x"}, overlord, user_id="u1")
        assert result["success"] is False
        assert "chain walk failed" in result["error"]
