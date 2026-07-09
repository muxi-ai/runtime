"""Unit tests for the Artifact Memory service (Phase 1 capture).

Covers the capture path from generate_file-shaped MuxiArtifact fixtures
(text content and binary data URLs), the gzip + AES-256-GCM storage
pipeline, versioning on name match, capture guards (empty content, secret
interpolation), user isolation, the artifact.saved audit event, and the
retention sweep. Runs on SQLite; set MUXI_TEST_POSTGRES_DSN to run the
same suite against a live PostgreSQL.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

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
from muxi.runtime.utils.id_generator import get_default_nanoid

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


async def clear_expiry(db_manager, public_id: str) -> None:
    """Give an artifact a NULL expiry (captured under duration: 0)."""
    async with db_manager.get_async_session() as session:
        stmt = select(Artifact).filter_by(public_id=public_id)
        artifact = (await session.execute(stmt)).scalars().first()
        artifact.expires_at = None
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

    async def test_db_failure_cleans_up_orphaned_blob(self, db_manager, store_dir):
        # Force a real metadata-persist failure by dropping the artifacts
        # table after the service is built: the blob is written first, so
        # the compensating cleanup must remove it before re-raising --
        # otherwise it is unlocatable (random public_id) and invisible to
        # the retention sweep forever.
        service = make_service(db_manager, store_dir)
        Artifact.__table__.drop(db_manager.engine)
        try:
            with pytest.raises(SQLAlchemyError):
                await service._capture_one(
                    text_artifact(), user_id="u1", agent_id=None, conversation_id=None
                )
            blobs = list(store_dir.rglob("*.bin")) if store_dir.exists() else []
            assert blobs == [], f"Orphaned blobs left behind: {blobs}"
        finally:
            # Restore the table so the shared fixture teardown stays valid.
            Artifact.__table__.create(db_manager.engine)

    async def test_db_failure_is_swallowed_by_batch_capture(self, db_manager, store_dir):
        # The public capture path wraps the same failure without raising.
        service = make_service(db_manager, store_dir)
        Artifact.__table__.drop(db_manager.engine)
        try:
            captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
            assert captured == []
            blobs = list(store_dir.rglob("*.bin")) if store_dir.exists() else []
            assert blobs == []
        finally:
            Artifact.__table__.create(db_manager.engine)


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


class TestChainConcurrency:
    """Version-chain writes are race-proof at both layers."""

    async def test_concurrent_captures_extend_chain_sequentially(self, db_manager, store_dir):
        # N concurrent background captures of the same name must end with
        # exactly one live head and strictly sequential versions -- the
        # per-chain lock serializes the read-version/insert section.
        service = make_service(db_manager, store_dir)
        results = await asyncio.gather(
            *(
                service.capture_response_artifacts(
                    [text_artifact(content=f"body {i}")], user_id="u1"
                )
                for i in range(5)
            )
        )
        assert all(len(captured) == 1 for captured in results)

        rows = await service.list_artifacts("u1", latest_only=False)
        assert sorted(row["version"] for row in rows) == [1, 2, 3, 4, 5]
        heads = [row for row in rows if row["is_latest"]]
        assert len(heads) == 1
        assert heads[0]["version"] == 5
        # The parent chain is intact: v(n) points at v(n-1).
        by_version = {row["version"]: row for row in rows}
        for version in range(2, 6):
            assert by_version[version]["parent_id"] == by_version[version - 1]["id"]

    async def test_different_names_do_not_serialize(self, db_manager, store_dir):
        # Holding one chain's lock must not block captures of other names
        # (the lock map is keyed per (user, name), not per user).
        service = make_service(db_manager, store_dir)
        async with service._chain_lock("u1", "notes.md"):
            captured = await asyncio.wait_for(
                service.capture_response_artifacts(
                    [text_artifact("other.md", "unblocked")], user_id="u1"
                ),
                timeout=5,
            )
        assert len(captured) == 1

    async def test_same_name_waits_for_the_chain_lock(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        async with service._chain_lock("u1", "notes.md"):
            task = asyncio.create_task(
                service.capture_response_artifacts([text_artifact()], user_id="u1")
            )
            await asyncio.sleep(0.2)
            assert not task.done()  # blocked on the held chain lock
        captured = await asyncio.wait_for(task, timeout=5)
        assert len(captured) == 1

    async def test_chain_lock_maps_are_pruned(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await asyncio.gather(
            *(
                service.capture_response_artifacts(
                    [text_artifact(content=f"body {i}")], user_id="u1"
                )
                for i in range(3)
            )
        )
        assert service._chain_locks == {}
        assert service._chain_lock_waiters == {}

    async def test_lost_multiprocess_race_retries_once(self, db_manager, store_dir):
        # Deterministically reproduce the multi-process race the DB index
        # backstops: between this writer's head-read and insert, a
        # competing process commits a new head, and the loser's stale
        # write (version=1, is_latest=True against an empty chain) hits
        # the real chain-head unique index. All database work and the
        # IntegrityError are real; only the interleaving is orchestrated.
        service = make_service(db_manager, store_dir)
        storage = service.storage
        real_insert = storage._insert_version
        state = {"raced": False}

        async def racing_insert(**fields):
            if not state["raced"]:
                state["raced"] = True
                # The competing process wins the race for the chain head.
                competitor = dict(fields, public_id=get_default_nanoid())
                competitor["storage_ref"] = fields["storage_ref"] + ".rival"
                await real_insert(**competitor)
                # Replay this writer's stale computation: it read "no
                # head" before the competitor committed, so it inserts
                # version=1 as latest -- rejected by the database.
                async with db_manager.get_async_session() as session:
                    session.add(
                        Artifact(
                            user_id=fields["user_id"],
                            formation_id=FORMATION_ID,
                            name=fields["name"],
                            content_type=fields["content_type"],
                            summary="stale write from the losing racer",
                            storage_ref=fields["storage_ref"],
                            size_bytes=1,
                            compressed_bytes=1,
                            checksum_sha256="0" * 64,
                            version=1,
                            is_latest=True,
                        )
                    )
                    await session.flush()
                raise AssertionError("the stale insert must violate the chain-head index")
            return await real_insert(**fields)

        storage._insert_version = racing_insert
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")

        # The retry re-read the winner's head and extended the chain.
        assert len(captured) == 1
        assert captured[0]["version"] == 2
        rows = await service.list_artifacts("u1", latest_only=False)
        assert sorted(row["version"] for row in rows) == [1, 2]
        assert sum(row["is_latest"] for row in rows) == 1


class TestDedup:
    """Identical re-captures of a chain head are skipped (PRD open q. 2)."""

    async def test_identical_recapture_is_skipped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        first = await service.capture_response_artifacts(
            [text_artifact(content="same body")], user_id="u1"
        )
        assert len(first) == 1
        duplicate = await service.capture_response_artifacts(
            [text_artifact(content="same body")], user_id="u1"
        )
        assert duplicate == []
        rows = await service.list_artifacts("u1", latest_only=False)
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        # No orphan blob was written for the skipped duplicate.
        assert len(list(store_dir.rglob("*.bin"))) == 1

    async def test_changed_content_still_versions(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts([text_artifact(content="draft")], user_id="u1")
        second = await service.capture_response_artifacts(
            [text_artifact(content="final")], user_id="u1"
        )
        assert second[0]["version"] == 2

    async def test_same_size_different_content_versions(self, db_manager, store_dir):
        # The size gate alone must not decide: equal sizes force the
        # content comparison, which detects the difference.
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts([text_artifact(content="aaaa")], user_id="u1")
        second = await service.capture_response_artifacts(
            [text_artifact(content="bbbb")], user_id="u1"
        )
        assert second[0]["version"] == 2

    async def test_identical_content_different_users_both_capture(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await service.capture_response_artifacts([text_artifact(content="same")], user_id="u1")
        other = await service.capture_response_artifacts(
            [text_artifact(content="same")], user_id="u2"
        )
        assert len(other) == 1

    async def test_dedup_fails_open_on_missing_head_blob(self, db_manager, store_dir):
        # A corrupt store (head blob missing) must not block new captures:
        # the dedup check fails open and the capture proceeds as a version.
        service = make_service(db_manager, store_dir)
        first = await service.capture_response_artifacts(
            [text_artifact(content="same body")], user_id="u1"
        )
        (store_dir / first[0]["storage_ref"]).unlink()
        second = await service.capture_response_artifacts(
            [text_artifact(content="same body")], user_id="u1"
        )
        assert len(second) == 1
        assert second[0]["version"] == 2


class TestMaxSize:
    """Oversized content is skipped at capture (PRD open question 1)."""

    async def test_oversized_capture_is_skipped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"max_size_mb": 1})
        oversized = "x" * (1024 * 1024 + 1)
        captured = await service.capture_response_artifacts(
            [text_artifact(content=oversized)], user_id="u1"
        )
        assert captured == []
        assert await service.list_artifacts("u1") == []

    async def test_content_at_the_limit_is_captured(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir, config={"max_size_mb": 1})
        at_limit = "x" * (1024 * 1024)
        captured = await service.capture_response_artifacts(
            [text_artifact(content=at_limit)], user_id="u1"
        )
        assert len(captured) == 1


class TestRetrievalSurface:
    """Phase 2 reads: metadata, version resolution, history, manifest."""

    async def _seed_chain(self, service, bodies=("v1", "v2", "v3"), user_id="u1"):
        rows = []
        for body in bodies:
            captured = await service.capture_response_artifacts(
                [text_artifact(content=body)], user_id=user_id, agent_id="writer"
            )
            rows.append(captured[0])
        return rows

    async def test_get_metadata_is_user_scoped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        assert await service.get_metadata("u1", captured[0]["public_id"]) is not None
        assert await service.get_metadata("u2", captured[0]["public_id"]) is None

    async def test_get_history_returns_full_chain_from_any_version(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        v1, v2, v3 = await self._seed_chain(service)
        # Any version's public id resolves the whole chain, newest first.
        for anchor in (v1, v2, v3):
            chain = await service.get_history("u1", anchor["public_id"])
            assert [row["version"] for row in chain] == [3, 2, 1]
        assert chain[0]["is_latest"] is True
        assert chain[0]["agent_id"] == "writer"

    async def test_get_history_is_user_scoped(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        (head,) = await self._seed_chain(service, bodies=("only",))
        assert await service.get_history("u2", head["public_id"]) == []

    async def test_resolve_version_walks_the_chain(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        v1, v2, v3 = await self._seed_chain(service)
        resolved = await service.resolve_version("u1", v3["public_id"], version=1)
        assert resolved["public_id"] == v1["public_id"]
        # And the content of that version reads back.
        assert (await service.read_content("u1", resolved["public_id"])) == b"v1"

    async def test_resolve_version_unknown_version_is_none(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        v1, _, _ = await self._seed_chain(service)
        assert await service.resolve_version("u1", v1["public_id"], version=9) is None

    async def test_resolve_version_default_is_the_id_itself(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        v1, _, _ = await self._seed_chain(service)
        resolved = await service.resolve_version("u1", v1["public_id"])
        assert resolved["version"] == 1

    async def test_read_content_refreshes_last_accessed(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        captured = await service.capture_response_artifacts([text_artifact()], user_id="u1")
        before = captured[0]["last_accessed_at"]
        await asyncio.sleep(0.01)
        await service.read_content("u1", captured[0]["public_id"])
        after = (await service.get_metadata("u1", captured[0]["public_id"]))["last_accessed_at"]
        assert after > before

    async def test_manifest_orders_by_last_accessed_and_caps(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        for i in range(4):
            await service.capture_response_artifacts(
                [text_artifact(f"file-{i}.md", f"body {i}")], user_id="u1"
            )
        # Reading an older artifact bumps it to the top of the manifest.
        rows = await service.list_artifacts("u1")
        oldest = next(row for row in rows if row["name"] == "file-0.md")
        await asyncio.sleep(0.01)
        await service.read_content("u1", oldest["public_id"])

        manifest = await service.list_manifest("u1", limit=2)
        assert len(manifest) == 2
        assert manifest[0]["name"] == "file-0.md"

    async def test_count_artifacts_counts_latest_only(self, db_manager, store_dir):
        service = make_service(db_manager, store_dir)
        await self._seed_chain(service)  # 3 versions, 1 head
        await service.capture_response_artifacts(
            [text_artifact("other.md", "unrelated")], user_id="u1"
        )
        assert await service.count_artifacts("u1") == 2
        assert await service.count_artifacts("u2") == 0


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

    async def test_sweep_cascades_to_ancestor_versions(self, db_manager, store_dir):
        # Build a 3-version chain whose ancestors carry NULL expiry (as if
        # captured under duration: 0) while the head expires: the sweep
        # must retire the whole chain, or the superseded versions' blobs
        # leak forever -- non-latest rows are invisible to latest-only
        # listings and would never be reached again.
        service = make_service(
            db_manager,
            store_dir,
            config={"retention": {"policy": "last_updated", "duration": 1}},
        )
        chain = []
        for body in ("v1", "v2", "v3"):
            captured = await service.capture_response_artifacts(
                [text_artifact(content=body)], user_id="u1"
            )
            chain.append(captured[0])
        v1, v2, v3 = chain
        await clear_expiry(db_manager, v1["public_id"])
        await clear_expiry(db_manager, v2["public_id"])
        await backdate_expiry(db_manager, v3["public_id"], days=2)

        assert await service.run_retention_sweep() == 3

        # All three rows soft-deleted (metadata retained for audit) and
        # all three blobs pruned.
        assert await service.list_artifacts("u1", latest_only=False) == []
        audit = await service.list_artifacts("u1", latest_only=False, include_deleted=True)
        assert len(audit) == 3
        assert all(row["deleted_at"] is not None for row in audit)
        for row in (v1, v2, v3):
            assert not (store_dir / row["storage_ref"]).exists()

    async def test_sweep_leaves_live_chains_untouched(self, db_manager, store_dir):
        # A chain whose head is still live is not cascaded into, even when
        # an unrelated artifact expires in the same pass.
        service = make_service(
            db_manager,
            store_dir,
            config={"retention": {"policy": "last_updated", "duration": 30}},
        )
        chain = []
        for body in ("v1", "v2", "v3"):
            captured = await service.capture_response_artifacts(
                [text_artifact(content=body)], user_id="u1"
            )
            chain.append(captured[0])
        unrelated = (
            await service.capture_response_artifacts(
                [text_artifact("other.md", "expires soon")], user_id="u1"
            )
        )[0]
        await backdate_expiry(db_manager, unrelated["public_id"], days=31)

        assert await service.run_retention_sweep() == 1

        survivors = await service.list_artifacts("u1", latest_only=False)
        assert {row["public_id"] for row in survivors} == {row["public_id"] for row in chain}
        for row in chain:
            assert (store_dir / row["storage_ref"]).exists()
        assert not (store_dir / unrelated["storage_ref"]).exists()

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


class TestSavedEventFailureIsolation:
    """artifact.saved recording failure must not fail the capture (review P1).

    The blob and metadata row are committed before the audit event is
    recorded; a memory_events failure is logged and swallowed so the
    artifact is still returned as captured.
    """

    async def test_event_record_failure_keeps_artifact(self, db_manager, store_dir):
        class ExplodingEvents:
            async def record(self, **kwargs):
                raise RuntimeError("substrate down")

        service = make_service(db_manager, store_dir, memory_events=ExplodingEvents())
        captured = await service.capture_response_artifacts(
            [text_artifact("report.csv", "a,b\n1,2")], user_id="u1"
        )
        assert len(captured) == 1
        # The artifact row exists and is queryable despite the event failure
        rows = await service.list_artifacts(user_id="u1")
        assert any(r["name"] == "report.csv" for r in rows)
