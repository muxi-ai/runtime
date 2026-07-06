"""Unit tests for Memory Revamp Phase 2: captain's log schema.

Covers table creation on both database backends (exercised through SQLite,
which shares the SQLAlchemy models and metadata with PostgreSQL), the PRD
columns for captains_log / captains_log_sources / lessons, the per-scope
unique constraints, and the index set.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.log.models import (
    SOURCE_TYPE_BUFFER_ITEM,
    SOURCE_TYPE_LOG_ENTRY,
    SOURCE_TYPE_VECTOR_CHUNK,
    SOURCE_TYPES,
    CaptainsLogEntry,
    CaptainsLogSource,
    Lesson,
)

FORMATION_ID = "log-test-formation"

LOG_TABLES = [CaptainsLogEntry.__table__, CaptainsLogSource.__table__, Lesson.__table__]


@pytest.fixture
def engine():
    """In-memory SQLite engine with the captain's log tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=LOG_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """Session bound to the in-memory engine."""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestTableCreation:
    """All three tables create cleanly with the PRD columns."""

    def test_tables_exist(self, engine):
        tables = inspect(engine).get_table_names()
        assert "captains_log" in tables
        assert "captains_log_sources" in tables
        assert "lessons" in tables

    def test_entry_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("captains_log")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "formation_id",
            "date",
            "summary",
            "decisions",
            "projects",
            "context",
            "created_at",
            "updated_at",
        }

    def test_source_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("captains_log_sources")}
        assert columns == {"id", "log_id", "source_type", "source_id", "created_at"}

    def test_lesson_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("lessons")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "agent_id",
            "formation_id",
            "rule",
            "context",
            "rule_hash",
            "source_log_id",
            "confidence",
            "hits",
            "last_applied_at",
            "decayed_at",
            "archived",
            "created_at",
            "updated_at",
        }

    def test_indexes_present(self, engine):
        inspector = inspect(engine)
        entry_indexes = {index["name"] for index in inspector.get_indexes("captains_log")}
        assert "idx_captains_log_user_date" in entry_indexes

        source_indexes = {index["name"] for index in inspector.get_indexes("captains_log_sources")}
        assert "idx_captains_log_sources_log" in source_indexes

        lesson_indexes = {index["name"] for index in inspector.get_indexes("lessons")}
        assert "idx_lessons_scope" in lesson_indexes
        assert "idx_lessons_active_confidence" in lesson_indexes

    def test_source_type_vocabulary(self):
        assert SOURCE_TYPES == {
            SOURCE_TYPE_BUFFER_ITEM,
            SOURCE_TYPE_VECTOR_CHUNK,
            SOURCE_TYPE_LOG_ENTRY,
        }


class TestEntryRows:
    def test_integer_identity_and_nano_public_id(self, session):
        entry = CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        session.add(entry)
        session.commit()
        assert isinstance(entry.id, int)
        assert isinstance(entry.public_id, str)
        assert len(entry.public_id) == 21  # Nano ID, users-table convention

    def test_section_defaults(self, session):
        entry = CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        session.add(entry)
        session.commit()
        assert entry.summary is None
        assert entry.decisions == []
        assert entry.projects == []
        assert entry.context is None

    def test_one_entry_per_user_date(self, session):
        session.add(
            CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        )
        session.commit()
        session.add(
            CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_date_allowed_across_users(self, session):
        session.add(
            CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        )
        session.add(
            CaptainsLogEntry(user_id="u2", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        )
        session.commit()

    def test_to_dict_round_trip(self, session):
        entry = CaptainsLogEntry(
            user_id="u1",
            formation_id=FORMATION_ID,
            date=date(2026, 7, 6),
            summary="Finalized the memory PRD",
            decisions=["Knowledge graph over flat facts"],
            projects=["MUXI"],
            context="Stress-tested the use case",
        )
        session.add(entry)
        session.commit()
        data = entry.to_dict()
        assert data["date"] == "2026-07-06"
        assert data["summary"] == "Finalized the memory PRD"
        assert data["decisions"] == ["Knowledge graph over flat facts"]
        assert data["projects"] == ["MUXI"]
        assert data["context"] == "Stress-tested the use case"


class TestSourceRows:
    def _entry(self, session):
        entry = CaptainsLogEntry(user_id="u1", formation_id=FORMATION_ID, date=date(2026, 7, 6))
        session.add(entry)
        session.commit()
        return entry

    def test_unique_source_per_entry(self, session):
        entry = self._entry(session)
        session.add(
            CaptainsLogSource(
                log_id=entry.id, source_type=SOURCE_TYPE_BUFFER_ITEM, source_id="123.4"
            )
        )
        session.commit()
        session.add(
            CaptainsLogSource(
                log_id=entry.id, source_type=SOURCE_TYPE_BUFFER_ITEM, source_id="123.4"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_to_dict(self, session):
        entry = self._entry(session)
        source = CaptainsLogSource(
            log_id=entry.id, source_type=SOURCE_TYPE_VECTOR_CHUNK, source_id="chunk-42"
        )
        session.add(source)
        session.commit()
        data = source.to_dict()
        assert data["log_id"] == entry.id
        assert data["source_type"] == SOURCE_TYPE_VECTOR_CHUNK
        assert data["source_id"] == "chunk-42"


class TestLessonRows:
    def test_defaults(self, session):
        lesson = Lesson(
            user_id="u1",
            agent_id="assistant",
            formation_id=FORMATION_ID,
            rule="Prefer reportlab over fpdf for PDFs",
            rule_hash="a" * 64,
        )
        session.add(lesson)
        session.commit()
        assert lesson.confidence == 0.5
        assert lesson.hits == 1
        assert lesson.archived is False
        assert lesson.last_applied_at is None
        assert lesson.decayed_at is None
        assert len(lesson.public_id) == 21

    def test_rule_hash_unique_per_scope(self, session):
        session.add(
            Lesson(
                user_id="u1",
                agent_id="assistant",
                formation_id=FORMATION_ID,
                rule="Rule",
                rule_hash="b" * 64,
            )
        )
        session.commit()
        session.add(
            Lesson(
                user_id="u1",
                agent_id="assistant",
                formation_id=FORMATION_ID,
                rule="Rule again",
                rule_hash="b" * 64,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_rule_hash_allowed_across_agents(self, session):
        session.add(
            Lesson(
                user_id="u1",
                agent_id="assistant",
                formation_id=FORMATION_ID,
                rule="Rule",
                rule_hash="c" * 64,
            )
        )
        session.add(
            Lesson(
                user_id="u1",
                agent_id="researcher",
                formation_id=FORMATION_ID,
                rule="Rule",
                rule_hash="c" * 64,
            )
        )
        session.commit()
