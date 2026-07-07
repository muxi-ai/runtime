"""Unit tests for the Artifact Memory service (Phase 1 capture).

Covers the capture path from generate_file-shaped MuxiArtifact fixtures
(text content and binary data URLs), the gzip + AES-256-GCM storage
pipeline, versioning on name match, capture guards (empty content, secret
interpolation), user isolation, the artifact.saved audit event, and the
retention sweep. Runs on SQLite; set MUXI_TEST_POSTGRES_DSN to run the
same suite against a live PostgreSQL.
"""

from __future__ import annotations

import base64
import gzip
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from muxi.runtime.datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.artifacts import ArtifactMemoryService
from muxi.runtime.services.memory.artifacts.models import Artifact, SystemConfig
from muxi.runtime.services.memory.events.models import (
    EVENT_ARTIFACT_SAVED,
    MemoryEvent,
    ProjectionCheckpoint,
)
from muxi.runtime.services.memory.events.service import MemoryEventService
from muxi.runtime.utils.datetime_utils import utc_now_naive

FORMATION_ID = "artifact-test-formation"
POSTGRES_DSN = os.environ.get("MUXI_TEST_POSTGRES_DSN")
BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_DSN else [])

TABLES = [
    Artifact.__table__,
    SystemConfig.__table__,
    MemoryEvent.__table__,
    ProjectionCheckpoint.__table__,
]

GZIP_MAGIC = b"\x1f\x8b"


@pytest.fixture(params=BACKENDS)
def db_manager(request, tmp_path):
    """Database manager per backend with the artifact tables created.

    SQLite uses a file (not :memory:) because the DatabaseManager keeps
    separate sync and async engines; both must see the same tables.
    """
    if request.param == "postgresql":
        manager = DatabaseManager(POSTGRES_DSN)
        Base.metadata.drop_all(manager.engine, tables=TABLES)
    else:
        manager = DatabaseManager(f"sqlite:///{tmp_path}/artifacts.db")
    manager.create_tables(Base.metadata, tables=TABLES)
    yield manager
    if request.param == "postgresql":
        Base.metadata.drop_all(manager.engine, tables=TABLES)
    manager.engine.dispose()


@pytest.fixture
def store_dir(tmp_path):
    """Blob store base directory."""
    return tmp_path / "artifact-store"


def make_service(db_manager, store_dir, config=None, memory_events=None) -> ArtifactMemoryService:
    """Build a service with local storage rooted in the test tmp dir."""
    config = dict(config or {})
    config.setdefault("storage", {"type": "local", "path": str(store_dir)})
    return ArtifactMemoryService(
        db_manager=db_manager,
        formation_id=FORMATION_ID,
        config=config,
        memory_events=memory_events,
    )


def text_artifact(filename="notes.md", content="# Q1 notes\nRevenue up.") -> MuxiArtifact:
    """generate_file-shaped text artifact fixture."""
    return MuxiArtifact(
        type="text",
        format=filename.rsplit(".", 1)[-1],
        filename=filename,
        content=content,
        metadata=ArtifactMetadata(size_bytes=len(content), created_at=datetime.now()),
    )


def binary_artifact(filename="chart.png", raw=b"\x89PNG\r\n\x1a\nfakepixels") -> MuxiArtifact:
    """generate_file-shaped binary artifact fixture (data URL transport)."""
    payload = base64.b64encode(raw).decode("ascii")
    return MuxiArtifact(
        type="image",
        format=filename.rsplit(".", 1)[-1],
        filename=filename,
        data_url=f"data:image/png;base64,{payload}",
        metadata=ArtifactMetadata(size_bytes=len(raw), created_at=datetime.now()),
    )


async def backdate_expiry(db_manager, public_id: str, days: int) -> None:
    """Force an artifact's expiry into the past for sweep tests."""
    async with db_manager.get_async_session() as session:
        stmt = select(Artifact).filter_by(public_id=public_id)
        artifact = (await session.execute(stmt)).scalars().first()
        artifact.expires_at = utc_now_naive() - timedelta(days=days)
        await session.flush()


class TestCapture:
    """The capture path persists generate_file outputs."""

    async def test_capture_text_artifact(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts(
            [text_artifact()], user_id="u1", agent_id="generator", conversation_id="s1"
        )
        assert len(captured) == 1
        row = captured[0]
        assert row["name"] == "notes.md"
        assert row["content_type"] == "text/markdown"
        assert row["category"] == "text"
        assert row["version"] == 1
        assert row["is_latest"] is True
        assert row["agent_id"] == "generator"
        assert row["conversation_id"] == "s1"
        assert row["size_bytes"] == len("# Q1 notes\nRevenue up.".encode())
        assert row["compressed_bytes"] > 0
        assert row["expires_at"] is None  # default retention: forever
        assert row["summary"]  # deterministic capture summary, never empty

    async def test_capture_binary_artifact_round_trips(self, db_manager, store_dir):
        raw = b"\x89PNG\r\n\x1a\nfakepixels"
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts(
            [binary_artifact(raw=raw)], user_id="u1"
        )
        assert len(captured) == 1
        assert captured[0]["content_type"] == "image/png"
        content = await service.read_content("u1", captured[0]["public_id"])
        assert content == raw

    async def test_blob_is_encrypted_at_rest(self, db_manager, store_dir):
        content = "# Q1 notes\nRevenue up."
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts(
            [text_artifact(content=content)], user_id="u1"
        )
        blob = service.blob_store.read(captured[0]["storage_ref"])
        assert not blob.startswith(GZIP_MAGIC)  # not the bare gzip stream
        assert content.encode() not in blob  # no plaintext leakage
        # The service still round-trips it through the derived key.
        restored = await service.read_content("u1", captured[0]["public_id"])
        assert restored == content.encode()

    async def test_encryption_disabled_stores_gzip(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"encryption": {"enabled": False}})
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        blob = service.blob_store.read(captured[0]["storage_ref"])
        assert blob.startswith(GZIP_MAGIC)
        assert gzip.decompress(blob) == "# Q1 notes\nRevenue up.".encode()

    async def test_checksum_matches_stored_blob(self, db_manager, store_dir):
        import hashlib

        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        blob = service.blob_store.read(captured[0]["storage_ref"])
        assert hashlib.sha256(blob).hexdigest() == captured[0]["checksum_sha256"]

    async def test_instance_id_is_stable_across_service_instances(self, db_manager, store_dir):
        first = make_service(db_manager, store_dir)
        captured = await first.capture_response_artifacts([text_artifact()], user_id="u1")
        # A fresh service against the same database derives the same key.
        second = make_service(db_manager, store_dir)
        restored = await second.read_content("u1", captured[0]["public_id"])
        assert restored == "# Q1 notes\nRevenue up.".encode()


class TestCaptureGuards:
    """Capture guards skip unusable or unsafe content without failing."""

    async def test_empty_content_skipped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts(
            [text_artifact(content="")], user_id="u1"
        )
        assert captured == []
        assert await service.list_artifacts("u1") == []

    async def test_secret_interpolation_skipped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts(
            [text_artifact(content='api_key: "${{ secrets.OPENAI_API_KEY }}"')],
            user_id="u1",
        )
        assert captured == []
        assert await service.list_artifacts("u1") == []

    async def test_capture_failure_is_isolated(self, db_manager, tmp_path):
        # Root the blob store at a path occupied by a *file* so the write
        # fails for real, then verify the batch continues and no exception
        # escapes the capture path.
        blocked = tmp_path / "blocked-store"
        blocked.write_text("not a directory")
        service = make_service(db_manager, blocked)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert captured == []

    async def test_disabled_service_is_inert(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"enabled": False})
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert captured == []
        assert not store_dir.exists()  # no blob directory is ever created


class TestVersioning:
    """Same-name captures extend the version chain (PRD 1.4)."""

    async def test_name_match_creates_new_version(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        first = await service.capture_response_artifacts(
            [text_artifact(content="v1 draft")], user_id="u1"
        )
        second = await service.capture_response_artifacts(
            [text_artifact(content="v2 final")], user_id="u1"
        )
        v1, v2 = first[0], second[0]
        assert v2["version"] == 2
        assert v2["parent_id"] == v1["id"]
        assert v2["is_latest"] is True

        all_versions = await service.list_artifacts("u1", latest_only=False)
        assert len(all_versions) == 2
        demoted = next(row for row in all_versions if row["id"] == v1["id"])
        assert demoted["is_latest"] is False

        # Both blobs are retained for history (PRD: previous version's
        # blob is NOT deleted).
        assert (await service.read_content("u1", v1["public_id"])) == b"v1 draft"
        assert (await service.read_content("u1", v2["public_id"])) == b"v2 final"

    async def test_latest_only_listing_shows_chain_heads(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts(
            [text_artifact(content="v1"), text_artifact("other.md", "unrelated")],
            user_id="u1",
        )
        await service.capture_response_artifacts([text_artifact(content="v2")], user_id="u1")
        latest = await service.list_artifacts("u1")
        assert {(row["name"], row["version"]) for row in latest} == {
            ("notes.md", 2),
            ("other.md", 1),
        }

    async def test_same_name_different_users_do_not_chain(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts([text_artifact()], user_id="u1")
        other = await service.capture_response_artifacts([text_artifact()], user_id="u2")
        assert other[0]["version"] == 1
        assert other[0]["parent_id"] is None


class TestUserIsolation:
    """All reads are user-scoped; per-user keys segregate blobs."""

    async def test_listing_is_user_scoped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert await service.list_artifacts("u2") == []

    async def test_read_is_user_scoped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        with pytest.raises(KeyError):
            await service.read_content("u2", captured[0]["public_id"])

    async def test_traversal_user_id_stays_inside_store(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="../../evil")
        blob_path = (store_dir / captured[0]["storage_ref"]).resolve()
        assert store_dir.resolve() in blob_path.parents
        assert blob_path.exists()


class TestAuditEvents:
    """Each capture records an artifact.saved event when the substrate exists."""

    async def test_capture_records_artifact_saved(self, db_manager, store_dir):
        events = MemoryEventService(db_manager, FORMATION_ID)
        service = make_service(db_manager, store_dir, memory_events=events)
        captured = await service.capture_response_artifacts(
            [text_artifact()], user_id="u1", agent_id="generator"
        )
        recorded = await events.list_events("u1", event_types=[EVENT_ARTIFACT_SAVED])
        assert len(recorded) == 1
        payload = recorded[0]["payload"]
        assert payload["artifact_id"] == captured[0]["public_id"]
        assert payload["name"] == "notes.md"
        assert payload["version"] == 1
        assert recorded[0]["source"] == "artifact_memory"
        assert recorded[0]["agent_id"] == "generator"

    async def test_capture_works_without_event_substrate(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, memory_events=None)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert len(captured) == 1


class TestRetention:
    """The retention sweep soft-deletes expired rows and prunes blobs."""

    async def test_expiry_computed_from_duration(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"retention": {"duration": 5}})
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert captured[0]["expires_at"] is not None

    async def test_zero_duration_means_forever(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"retention": {"duration": 0}})
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert captured[0]["expires_at"] is None
        assert await service.run_retention_sweep() == 0

    async def test_sweep_removes_expired_artifacts(self, db_manager, store_dir):
        service = make_service(
            db_manager,
            store_dir,
            config={"retention": {"policy": "last_updated", "duration": 1}},
        )
        captured = await service.capture_response_artifacts(
            [text_artifact(), text_artifact("keep.md", "still fresh")], user_id="u1"
        )
        expired, fresh = captured[0], captured[1]
        await backdate_expiry(db_manager, expired["public_id"], days=2)

        assert await service.run_retention_sweep() == 1

        # Soft delete: metadata retained, listing excludes, blob pruned.
        remaining = await service.list_artifacts("u1")
        assert [row["public_id"] for row in remaining] == [fresh["public_id"]]
        audit = await service.list_artifacts("u1", include_deleted=True)
        assert len(audit) == 2
        blob_path = store_dir / expired["storage_ref"]
        assert not blob_path.exists()
        assert (store_dir / fresh["storage_ref"]).exists()

        # The sweep is idempotent.
        assert await service.run_retention_sweep() == 0

    async def test_last_accessed_read_extends_expiry(self, db_manager, store_dir):
        service = make_service(
            db_manager,
            store_dir,
            config={"retention": {"policy": "last_accessed", "duration": 30}},
        )
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        before = captured[0]["expires_at"]
        await service.read_content("u1", captured[0]["public_id"])
        row = (await service.list_artifacts("u1"))[0]
        assert row["expires_at"] >= before

    async def test_sweep_loop_lifecycle(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"retention": {"duration": 1}})
        service.start()
        assert service._sweep_task is not None
        await service.stop()
        assert service._sweep_task is None

    async def test_sweep_loop_not_started_without_duration(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        service.start()
        assert service._sweep_task is None
