"""Unit tests for the /v1/artifacts read endpoints (Phase 2 API surface).

Covers user scoping (X-Muxi-User-ID required; cross-user ids 404), the
inert posture without artifact memory, list shape (manifest ordering,
total), metadata reads, streamed content delivery (headers, bytes,
version selection, last_accessed refresh, header-injection hardening),
and version history.

Wiring fidelity: the app fixture attaches the service through a REAL
``Overlord`` instance built with the same ``configured_services``
handoff the Formation performs at boot, and the routes resolve it from
``formation._overlord`` exactly like at serving time. This is the
regression guard for the review blocker where the routes read a
formation attribute the serving path never populated and the test mocks
agreed with the wrong name -- an attribute drift on either side now
fails these tests instead of passing silently.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from muxi.runtime.datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from muxi.runtime.formation.overlord import Overlord
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


def make_overlord(artifact_memory) -> Overlord:
    """A real Overlord carrying the service via configured_services --
    the same handoff Formation performs (formation.py builds
    ``configured_services["artifact_memory"]`` from its init-time
    attribute; Overlord.__init__ exposes it as ``self.artifact_memory``,
    which is what the routes read)."""
    return Overlord(
        configured_services={
            "observability_manager": MagicMock(),
            "artifact_memory": artifact_memory,
        }
    )


def make_app(artifact_memory) -> FastAPI:
    """The artifacts router wired the way the runtime serves it."""
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.state.formation = SimpleNamespace(
        _overlord=make_overlord(artifact_memory),
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


class TestServiceResolution:
    """The routes must resolve the service from the live overlord, never
    from the formation's init-time attribute (review blocker #264)."""

    async def test_formation_attribute_alone_serves_nothing(self, service):
        # A formation carrying only the init-time attribute (no overlord
        # exposure) must NOT serve artifacts: flipping the routes back to
        # formation._artifact_memory makes this test fail.
        await seed(service, text_artifact())
        app = FastAPI()
        app.include_router(router, prefix="/v1")
        app.state.formation = SimpleNamespace(
            _artifact_memory=service,
            _overlord=make_overlord(None),
            formation_id=FORMATION_ID,
            request_middleware=None,
            permission_resolver=None,
        )
        response = TestClient(app).get("/v1/artifacts", headers=USER_HEADER)
        assert response.status_code == 200
        assert response.json()["data"]["total"] == 0

    async def test_overlord_wiring_serves(self, service, client):
        # The positive direction: the real Overlord configured_services
        # handoff is sufficient for the routes to serve.
        row = await seed(service, text_artifact())
        response = client.get("/v1/artifacts", headers=USER_HEADER)
        assert response.json()["data"]["total"] == 1
        assert response.json()["data"]["artifacts"][0]["id"] == row["public_id"]


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

    async def test_filename_header_injection_is_neutralized(self, service, client):
        # Artifact names are agent-generated: CR/LF in the name must not
        # smuggle extra HTTP headers through Content-Disposition.
        evil_name = 'evil\r\nX-Injected: 1\r\n.md"'
        row = await seed(service, text_artifact(evil_name, "payload"))
        response = client.get(f"/v1/artifacts/{row['public_id']}/content", headers=USER_HEADER)
        assert response.status_code == 200
        assert response.content == b"payload"
        assert "x-injected" not in response.headers
        disposition = response.headers["content-disposition"]
        assert "\r" not in disposition and "\n" not in disposition
        # RFC 6266: the true name rides filename* fully percent-encoded.
        assert "filename*=UTF-8''evil%0D%0AX-Injected" in disposition
        # The quoted ASCII fallback carries no quotes or control chars.
        assert 'filename="evil__X-Injected: 1__.md"' in disposition


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
