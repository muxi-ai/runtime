"""Unit tests for the Artifact Memory schema (Phase 1).

Covers table creation on both database backends (exercised through SQLite,
which shares the SQLAlchemy models and metadata with PostgreSQL; set
MUXI_TEST_POSTGRES_DSN to also run the suite against a live PostgreSQL),
the artifacts / system_config column sets, indexes, defaults, and the
artifact.saved payload schema registered with the event substrate.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.artifacts.models import Artifact, SystemConfig
from muxi.runtime.services.memory.events.models import (
    EVENT_ARTIFACT_SAVED,
    EVENT_SCHEMAS,
    validate_event_payload,
)

FORMATION_ID = "artifact-test-formation"

ARTIFACT_TABLES = [Artifact.__table__, SystemConfig.__table__]

POSTGRES_DSN = os.environ.get("MUXI_TEST_POSTGRES_DSN")

BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_DSN else [])


@pytest.fixture(params=BACKENDS)
def engine(request):
    """Engine per backend with the artifact memory tables created."""
    if request.param == "postgresql":
        engine = create_engine(POSTGRES_DSN)
        Base.metadata.drop_all(engine, tables=ARTIFACT_TABLES)
    else:
        engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=ARTIFACT_TABLES)
    yield engine
    if request.param == "postgresql":
        Base.metadata.drop_all(engine, tables=ARTIFACT_TABLES)
    engine.dispose()


@pytest.fixture
def session(engine):
    """Session bound to the backend engine."""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def make_artifact(**overrides) -> Artifact:
    """Build a minimal valid artifact row."""
    fields = {
        "user_id": "u1",
        "formation_id": FORMATION_ID,
        "name": "report.pdf",
        "content_type": "application/pdf",
        "summary": "Quarterly report",
        "storage_ref": "u1/ab/abcdef.bin",
        "size_bytes": 1024,
        "compressed_bytes": 512,
        "checksum_sha256": "0" * 64,
    }
    fields.update(overrides)
    return Artifact(**fields)


class TestTableCreation:
    """Both artifact memory tables create cleanly with the PRD columns."""

    def test_tables_exist(self, engine):
        tables = inspect(engine).get_table_names()
        assert "artifacts" in tables
        assert "system_config" in tables

    def test_artifact_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("artifacts")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "formation_id",
            "agent_id",
            "conversation_id",
            "version",
            "parent_id",
            "is_latest",
            "name",
            "content_type",
            "category",
            "summary",
            "tags",
            "storage_ref",
            "size_bytes",
            "compressed_bytes",
            "checksum_sha256",
            "created_at",
            "updated_at",
            "last_accessed_at",
            "expires_at",
            "deleted_at",
        }

    def test_system_config_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("system_config")}
        assert columns == {"key", "value"}

    def test_artifact_indexes(self, engine):
        indexes = {index["name"] for index in inspect(engine).get_indexes("artifacts")}
        assert "idx_artifacts_user" in indexes
        assert "idx_artifacts_user_latest" in indexes
        assert "idx_artifacts_user_name" in indexes
        assert "idx_artifacts_agent" in indexes
        assert "idx_artifacts_parent" in indexes


class TestDefaults:
    """Column defaults match the capture contract."""

    def test_defaults(self, session):
        artifact = make_artifact()
        session.add(artifact)
        session.commit()
        assert artifact.version == 1
        assert artifact.parent_id is None
        assert artifact.is_latest is True
        assert artifact.tags == []
        assert artifact.category is None
        assert artifact.created_at is not None
        assert artifact.updated_at is not None
        assert artifact.last_accessed_at is not None
        assert artifact.expires_at is None
        assert artifact.deleted_at is None
        assert len(artifact.public_id) == 21

    def test_public_id_unique(self, session):
        session.add(make_artifact(public_id="fixed-public-id-00001"))
        session.commit()
        session.add(make_artifact(public_id="fixed-public-id-00001"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_system_config_key_is_primary(self, session):
        session.add(SystemConfig(key="formation_instance_id", value="abc"))
        session.commit()
        session.add(SystemConfig(key="formation_instance_id", value="def"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestVersionChainColumns:
    """The version chain columns store as written on both backends."""

    def test_version_chain_round_trip(self, session):
        v1 = make_artifact()
        session.add(v1)
        session.commit()
        v1.is_latest = False
        v2 = make_artifact(version=2, parent_id=v1.id, is_latest=True)
        session.add(v2)
        session.commit()
        assert v2.version == 2
        assert v2.parent_id == v1.id
        assert v1.is_latest is False
        assert v2.is_latest is True


class TestArtifactSavedEventSchema:
    """artifact.saved is registered with the event substrate registry."""

    def test_v1_schema_registered(self):
        assert 1 in EVENT_SCHEMAS[EVENT_ARTIFACT_SAVED]

    def test_valid_payload_passes(self):
        validate_event_payload(
            EVENT_ARTIFACT_SAVED,
            {
                "artifact_id": "abc123",
                "name": "report.pdf",
                "version": 2,
                "content_type": "application/pdf",
                "category": "document",
                "size_bytes": 1024,
                "checksum_sha256": "0" * 64,
                "storage_ref": "u1/ab/abc123.bin",
                "tags": ["q1", "sales"],
            },
        )

    def test_missing_required_key_rejected(self):
        with pytest.raises(ValueError, match="missing required keys"):
            validate_event_payload(
                EVENT_ARTIFACT_SAVED,
                {"artifact_id": "abc123", "name": "report.pdf", "version": 1},
            )

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="unknown keys"):
            validate_event_payload(
                EVENT_ARTIFACT_SAVED,
                {
                    "artifact_id": "abc123",
                    "name": "report.pdf",
                    "version": 1,
                    "content_type": "application/pdf",
                    "blob": "never-ship-content-through-events",
                },
            )

    def test_tags_must_be_a_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            validate_event_payload(
                EVENT_ARTIFACT_SAVED,
                {
                    "artifact_id": "abc123",
                    "name": "report.pdf",
                    "version": 1,
                    "content_type": "application/pdf",
                    "tags": "q1",
                },
            )
