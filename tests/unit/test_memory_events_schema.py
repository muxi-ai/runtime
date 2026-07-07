"""Unit tests for the Memory Event Substrate schema.

Covers table creation on both database backends (exercised through SQLite,
which shares the SQLAlchemy models and metadata with PostgreSQL; set
MUXI_TEST_POSTGRES_DSN to also run the suite against a live PostgreSQL),
the event/checkpoint column sets, the partial unique idempotency index,
and the versioned payload schema registry.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.events.models import (
    EVENT_FACT_EXTRACTED,
    EVENT_GRAPH_EXTRACTED,
    EVENT_INTERACTION_TURN,
    EVENT_LESSON_RECORDED,
    EVENT_LOG_ENTRY,
    EVENT_SCHEMAS,
    EVENT_USER_DELETION,
    MemoryEvent,
    ProjectionCheckpoint,
    validate_event_payload,
)

FORMATION_ID = "events-test-formation"

EVENT_TABLES = [MemoryEvent.__table__, ProjectionCheckpoint.__table__]

POSTGRES_DSN = os.environ.get("MUXI_TEST_POSTGRES_DSN")

BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_DSN else [])


@pytest.fixture(params=BACKENDS)
def engine(request):
    """Engine per backend with the substrate tables created."""
    if request.param == "postgresql":
        engine = create_engine(POSTGRES_DSN)
        Base.metadata.drop_all(engine, tables=EVENT_TABLES)
    else:
        engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=EVENT_TABLES)
    yield engine
    if request.param == "postgresql":
        Base.metadata.drop_all(engine, tables=EVENT_TABLES)
    engine.dispose()


@pytest.fixture
def session(engine):
    """Session bound to the backend engine."""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def make_event(**overrides) -> MemoryEvent:
    """Build a minimal valid event row."""
    fields = {
        "user_id": "u1",
        "formation_id": FORMATION_ID,
        "scope_type": "user",
        "scope_id": "u1",
        "event_type": EVENT_INTERACTION_TURN,
        "payload": {"user_message": "hello"},
        "source": "interaction",
    }
    fields.update(overrides)
    return MemoryEvent(**fields)


class TestTableCreation:
    """Both substrate tables create cleanly with the PRD columns."""

    def test_tables_exist(self, engine):
        tables = inspect(engine).get_table_names()
        assert "memory_events" in tables
        assert "projection_checkpoints" in tables

    def test_event_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("memory_events")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "formation_id",
            "scope_type",
            "scope_id",
            "occurred_at",
            "ingested_at",
            "event_type",
            "event_version",
            "payload",
            "source",
            "source_id",
            "source_confidence",
            "caused_by",
            "decay_rate",
            "expires_at",
            "deleted_at",
            "deleted_reason",
            "agent_id",
            "conversation_id",
        }

    def test_checkpoint_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("projection_checkpoints")}
        assert columns == {
            "id",
            "projection_name",
            "formation_id",
            "user_id",
            "last_event_id",
            "last_applied_at",
            "schema_version",
        }

    def test_event_indexes(self, engine):
        indexes = {index["name"] for index in inspect(engine).get_indexes("memory_events")}
        assert "idx_memory_events_idempotency" in indexes
        assert "idx_memory_events_user_time" in indexes
        assert "idx_memory_events_user_type" in indexes
        assert "idx_memory_events_user_source" in indexes
        assert "idx_memory_events_caused_by" in indexes


class TestScopeAndDefaults:
    """Forward-compatible scope columns and column defaults."""

    def test_user_scope_recorded(self, session):
        event = make_event()
        session.add(event)
        session.commit()
        assert event.scope_type == "user"
        assert event.scope_id == event.user_id

    def test_defaults(self, session):
        event = make_event()
        session.add(event)
        session.commit()
        assert event.event_version == 1
        assert event.source_confidence == 1.0
        assert event.decay_rate == "static"
        assert event.deleted_at is None
        assert event.occurred_at is not None
        assert event.ingested_at is not None
        assert len(event.public_id) == 21


class TestIdempotencyIndex:
    """The partial unique index enforces (scope, source, source_id) once."""

    def test_duplicate_source_id_rejected(self, session):
        session.add(make_event(source_id="turn/1"))
        session.commit()
        session.add(make_event(source_id="turn/1"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_null_source_id_unconstrained(self, session):
        session.add(make_event())
        session.add(make_event())
        session.commit()
        assert session.query(MemoryEvent).count() == 2

    def test_other_user_unconstrained(self, session):
        session.add(make_event(source_id="turn/1"))
        session.add(make_event(user_id="u2", scope_id="u2", source_id="turn/1"))
        session.commit()
        assert session.query(MemoryEvent).count() == 2


class TestCheckpointUniqueness:
    """One checkpoint row per (projection, formation, user)."""

    def test_duplicate_scope_rejected(self, session):
        session.add(
            ProjectionCheckpoint(
                projection_name="knowledge_graph",
                formation_id=FORMATION_ID,
                user_id="u1",
                last_event_id=1,
            )
        )
        session.commit()
        session.add(
            ProjectionCheckpoint(
                projection_name="knowledge_graph",
                formation_id=FORMATION_ID,
                user_id="u1",
                last_event_id=2,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestPayloadSchemaRegistry:
    """Versioned payload validation at write time."""

    def test_every_event_type_has_a_v1_schema(self):
        for event_type in (
            EVENT_INTERACTION_TURN,
            EVENT_FACT_EXTRACTED,
            EVENT_GRAPH_EXTRACTED,
            EVENT_LOG_ENTRY,
            EVENT_LESSON_RECORDED,
            EVENT_USER_DELETION,
        ):
            assert 1 in EVENT_SCHEMAS[event_type]

    def test_valid_payloads_pass(self):
        validate_event_payload(EVENT_INTERACTION_TURN, {"user_message": "hi"})
        validate_event_payload(
            EVENT_FACT_EXTRACTED,
            {"memory": "Likes tea", "collection": "preferences", "metadata": {}},
        )
        validate_event_payload(EVENT_GRAPH_EXTRACTED, {"entities": [], "relationships": []})
        validate_event_payload(
            EVENT_LOG_ENTRY,
            {"date": "2026-07-07", "summary": "Did things", "decisions": [], "sources": []},
        )
        validate_event_payload(EVENT_LESSON_RECORDED, {"agent_id": "overlord", "rule": "Be brief"})
        validate_event_payload(EVENT_USER_DELETION, {"reason": "gdpr", "target_event_ids": [1]})

    def test_unknown_event_type_rejected(self):
        with pytest.raises(ValueError, match="Unknown memory event type"):
            validate_event_payload("nope.event", {})

    def test_unknown_version_rejected(self):
        with pytest.raises(ValueError, match="Unknown version"):
            validate_event_payload(EVENT_INTERACTION_TURN, {"user_message": "hi"}, 2)

    def test_missing_required_key_rejected(self):
        with pytest.raises(ValueError, match="missing required keys"):
            validate_event_payload(EVENT_FACT_EXTRACTED, {"memory": "Likes tea"})

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="unknown keys"):
            validate_event_payload(EVENT_INTERACTION_TURN, {"user_message": "hi", "extra": 1})

    def test_non_dict_payload_rejected(self):
        with pytest.raises(ValueError, match="must be a dict"):
            validate_event_payload(EVENT_INTERACTION_TURN, ["hi"])

    def test_list_key_type_enforced(self):
        with pytest.raises(ValueError, match="must be a list"):
            validate_event_payload(EVENT_GRAPH_EXTRACTED, {"entities": "Acme", "relationships": []})
