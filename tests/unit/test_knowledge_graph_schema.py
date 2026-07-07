"""Unit tests for Memory Revamp Phase 1: knowledge graph schema.

Covers table creation on both database backends (exercised through SQLite,
which shares the SQLAlchemy models and metadata with PostgreSQL), the PRD
columns (integer graph identity, status / contradicted_by / superseded_by),
the per-scope unique constraint, and the PRD index set.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from muxi.runtime.services.db import Base
from muxi.runtime.services.memory.graph.models import (
    ENTITY_TYPES,
    EXCLUSIVE_RELATIONSHIP_TYPES,
    RELATIONSHIP_TYPES,
    KGEntity,
    KGRelationship,
)

FORMATION_ID = "kg-test-formation"

KG_TABLES = [KGEntity.__table__, KGRelationship.__table__]


@pytest.fixture
def engine():
    """In-memory SQLite engine with the knowledge graph tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=KG_TABLES)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    """Session bound to the in-memory engine."""
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestTableCreation:
    """Both tables create cleanly with the PRD columns."""

    def test_tables_exist(self, engine):
        tables = inspect(engine).get_table_names()
        assert "kg_entities" in tables
        assert "kg_relationships" in tables

    def test_entity_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("kg_entities")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "formation_id",
            "type",
            "name",
            "attributes",
            "confidence",
            "status",
            "contradicted_by",
            "superseded_by",
            "derived_from_event_ids",
            "created_at",
            "updated_at",
        }

    def test_relationship_columns(self, engine):
        columns = {c["name"] for c in inspect(engine).get_columns("kg_relationships")}
        assert columns == {
            "id",
            "public_id",
            "user_id",
            "formation_id",
            "from_entity_id",
            "to_entity_id",
            "type",
            "attributes",
            "confidence",
            "status",
            "contradicted_by",
            "superseded_by",
            "derived_from_event_ids",
            "created_at",
            "updated_at",
        }

    def test_prd_indexes_present(self, engine):
        inspector = inspect(engine)
        entity_indexes = {index["name"] for index in inspector.get_indexes("kg_entities")}
        assert "idx_kg_entities_user_type" in entity_indexes
        assert "idx_kg_entities_user_name" in entity_indexes

        rel_indexes = {index["name"] for index in inspector.get_indexes("kg_relationships")}
        assert "idx_kg_relationships_user_type" in rel_indexes
        assert "idx_kg_relationships_from" in rel_indexes
        assert "idx_kg_relationships_to" in rel_indexes

    def test_integer_graph_identity(self, session):
        """Primary keys are integers usable as graph node/edge ids."""
        entity = KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="User")
        session.add(entity)
        session.commit()
        assert isinstance(entity.id, int)
        assert isinstance(entity.public_id, str)
        assert len(entity.public_id) == 21  # Nano ID, users-table convention

    def test_status_defaults_active(self, session):
        entity = KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="A")
        session.add(entity)
        session.commit()
        assert entity.status == "active"
        assert entity.contradicted_by is None
        assert entity.superseded_by is None


class TestConstraints:
    """Unique constraints and defaults enforce upsert semantics."""

    def test_entity_scope_unique(self, session):
        session.add(KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="Sarah"))
        session.commit()
        session.add(KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="Sarah"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_name_different_user_allowed(self, session):
        session.add(KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="Sarah"))
        session.add(KGEntity(user_id="u2", formation_id=FORMATION_ID, type="person", name="Sarah"))
        session.commit()

    def test_same_name_different_type_allowed(self, session):
        session.add(
            KGEntity(user_id="u1", formation_id=FORMATION_ID, type="person", name="Phoenix")
        )
        session.add(
            KGEntity(user_id="u1", formation_id=FORMATION_ID, type="location", name="Phoenix")
        )
        session.commit()


class TestVocabulary:
    """The PRD type vocabularies are complete."""

    def test_entity_types(self):
        assert set(ENTITY_TYPES) == {
            "person",
            "company",
            "project",
            "location",
            "preference",
            "topic",
        }

    def test_relationship_types(self):
        assert set(RELATIONSHIP_TYPES) == {
            "works_at",
            "founded",
            "building",
            "lives_in",
            "prefers",
            "knows",
            "interested_in",
            "part_of",
        }

    def test_exclusive_types_are_relationship_types(self):
        assert EXCLUSIVE_RELATIONSHIP_TYPES <= set(RELATIONSHIP_TYPES)


class TestCentralTableCreation:
    """_create_all_database_tables wires the kg tables in on both backends."""

    def test_sqlite_creates_kg_tables_but_not_memories(self, tmp_path):
        """On SQLite, kg tables are created centrally while the dim-specific
        memories table is left to SQLiteMemory (its raw-SQL schema owns the
        ``metadata`` column and FTS mirrors; the SQLAlchemy variant winning
        the CREATE TABLE IF NOT EXISTS race would break flat-fact storage)."""
        from muxi.runtime.formation.initialization import _create_all_database_tables
        from muxi.runtime.services.db import DatabaseManager

        db_manager = DatabaseManager(f"sqlite:///{tmp_path}/central.db")
        _create_all_database_tables(db_manager, embedding_dimension=1536)

        tables = inspect(db_manager.engine).get_table_names()
        assert "kg_entities" in tables
        assert "kg_relationships" in tables
        assert "users" in tables
        assert "memories_1536" not in tables  # owned by SQLiteMemory on this backend
        db_manager.engine.dispose()
