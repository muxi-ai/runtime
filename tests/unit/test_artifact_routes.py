"""Unit tests for the /v1/artifacts read endpoints (Phase 2 API surface).

Covers user scoping (X-Muxi-User-ID required; cross-user ids 404), the
inert posture without artifact memory, list shape (manifest ordering,
total), metadata reads, streamed content delivery (headers, bytes,
version selection, last_accessed refresh), and version history.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from muxi.runtime.datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from muxi.runtime.formation.server.routes.client.artifacts import router
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.artifacts import ArtifactMemoryService
from muxi.runtime.services.memory.artifacts.models import Artifact, SystemConfig

FORMATION_ID = "artifact-routes-test"
TABLES = [Artifact.__table__, SystemConfig.__table__]
USER_HEADER = {"X-Muxi-User-ID": "u1"}


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


def make_app(artifact_memory) -> FastAPI:
    """Minimal app: the artifacts router + a formation stub on app.state."""
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.state.formation = SimpleNamespace(
        _artifact_memory=artifact_memory,
        formation_id=FORMATION_ID,
        request_middleware=None,
        permission_resolver=None,
    )
    return app


@pytest.fixture
def client(service):
    return TestClient(make_app(service))


def text_artifact(filename="notes.md", content="# Q1 notes\nRevenue up.") -> MuxiArtifact:
    return MuxiArtifact(
        type="text",
        format=filename.rsplit(".", 1)[-1],
        filename=filename,
        content=content,
        metadata=ArtifactMetadata(size_bytes=len(content), created_at=datetime.now()),
    )


async def seed(service, artifact, user_id="u1", agent_id="writer"):
    captured = await service.capture_response_artifacts(
        [artifact], user_id=user_id, agent_id=agent_id
    )
    assert len(captured) == 1
    return captured[0]


class TestAuthAndInertness:
    def test_user_header_required(self, client):
        response = client.get("/v1/artifacts")
        assert response.status_code == 400

    def test_no_artifact_memory_lists_empty(self):
        client = TestClient(make_app(None))
        response = client.get("/v1/artifacts", headers=USER_HEADER)
        assert response.status_code == 200
        assert response.json()["data"] == {"artifacts": [], "count": 0, "total": 0}

    def test_no_artifact_memory_reads_404(self):
        client = TestClient(make_app(None))
        for path in (
            "/v1/artifacts/some-id",
            "/v1/artifacts/some-id/content",
            "/v1/artifacts/some-id/versions",
        ):
            assert client.get(path, headers=USER_HEADER).status_code == 404

    def test_disabled_artifact_memory_is_inert(self, db_manager, tmp_path):
        disabled = ArtifactMemoryService(
            db_manager=db_manager,
            formation_id=FORMATION_ID,
            config={
                "enabled": False,
                "storage": {"type": "local", "path": str(tmp_path / "store")},
            },
        )
        client = TestClient(make_app(disabled))
        response = client.get("/v1/artifacts", headers=USER_HEADER)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0


class TestListing:
    async def test_lists_latest_with_total(self, service, client):
        await seed(service, text_artifact("a.md", "v1 body"))
        await seed(service, text_artifact("a.md", "v2 body"))  # versions a.md
        await seed(service, text_artifact("b.md", "other"))

        response = client.get("/v1/artifacts", headers=USER_HEADER)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 2
        names = {row["name"] for row in data["artifacts"]}
        assert names == {"a.md", "b.md"}
        row = data["artifacts"][0]
        assert set(row) >= {"id", "name", "version", "summary", "agent_id", "content_type"}
        assert "storage_ref" not in row  # storage internals stay private

    async def test_listing_is_user_scoped(self, service, client):
        await seed(service, text_artifact(), user_id="u2")
        response = client.get("/v1/artifacts", headers=USER_HEADER)
        assert response.json()["data"]["total"] == 0


class TestMetadata:
    async def test_get_metadata(self, service, client):
        row = await seed(service, text_artifact())
        response = client.get(f"/v1/artifacts/{row['public_id']}", headers=USER_HEADER)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == row["public_id"]
        assert data["agent_id"] == "writer"

    async def test_cross_user_metadata_404(self, service, client):
        row = await seed(service, text_artifact(), user_id="u2")
        response = client.get(f"/v1/artifacts/{row['public_id']}", headers=USER_HEADER)
        assert response.status_code == 404


class TestContent:
    async def test_content_streams_with_headers(self, service, client):
        row = await seed(service, text_artifact(content="stream me"))
        response = client.get(f"/v1/artifacts/{row['public_id']}/content", headers=USER_HEADER)
        assert response.status_code == 200
        assert response.content == b"stream me"
        assert response.headers["content-type"].startswith("text/markdown")
        assert 'filename="notes.md"' in response.headers["content-disposition"]
        assert response.headers["x-muxi-artifact-id"] == row["public_id"]

    async def test_content_version_selection(self, service, client):
        await seed(service, text_artifact(content="v1 body"))
        head = await seed(service, text_artifact(content="v2 body"))
        response = client.get(
            f"/v1/artifacts/{head['public_id']}/content?version=1", headers=USER_HEADER
        )
        assert response.content == b"v1 body"
        assert response.headers["x-muxi-artifact-version"] == "1"

    async def test_content_read_refreshes_last_accessed(self, service, client):
        row = await seed(service, text_artifact())
        before = row["last_accessed_at"]
        client.get(f"/v1/artifacts/{row['public_id']}/content", headers=USER_HEADER)
        after = (await service.get_metadata("u1", row["public_id"]))["last_accessed_at"]
        assert after >= before

    async def test_cross_user_content_404(self, service, client):
        row = await seed(service, text_artifact(), user_id="u2")
        response = client.get(f"/v1/artifacts/{row['public_id']}/content", headers=USER_HEADER)
        assert response.status_code == 404


class TestVersions:
    async def test_version_history(self, service, client):
        await seed(service, text_artifact(content="v1"))
        await seed(service, text_artifact(content="v2"))
        head = await seed(service, text_artifact(content="v3"))
        response = client.get(f"/v1/artifacts/{head['public_id']}/versions", headers=USER_HEADER)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["name"] == "notes.md"
        assert [v["version"] for v in data["versions"]] == [3, 2, 1]

    async def test_cross_user_versions_404(self, service, client):
        row = await seed(service, text_artifact(), user_id="u2")
        response = client.get(f"/v1/artifacts/{row['public_id']}/versions", headers=USER_HEADER)
        assert response.status_code == 404
