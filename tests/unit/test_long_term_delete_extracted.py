"""Unit tests for LongTermMemory.delete_extracted_memories.

The flat-fact projection reset must be one bulk DELETE filtered on the
JSON extraction-source marker -- rows are never loaded into memory and
never deleted one-by-one (Greptile review of the memory event substrate:
a per-row sweep is RAM-hungry and slow during a rebuild for an active
user). Covers both the statement shape (single bulk DELETE, no memories
SELECT) and the behavior (only the user's extraction-derived rows go;
conversations and other users survive).
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, select

from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.long_term import LongTermMemory, get_memory_model

FORMATION_ID = "ltm-delete-test-formation"


@pytest.fixture
def ltm(tmp_path):
    """Single-user LongTermMemory backed by a file SQLite database."""
    db_manager = DatabaseManager(f"sqlite:///{tmp_path}/ltm.db")
    get_memory_model(1536)  # ensure the dim table is registered with Base
    db_manager.create_tables(Base.metadata)
    memory = LongTermMemory(
        db_manager=db_manager,
        formation_id=FORMATION_ID,
        embedding_model="openai/text-embedding-3-small",
    )
    yield memory
    db_manager.engine.dispose()


def seed_memory(ltm, user_id: int, text: str, source: str) -> str:
    """Insert one memory row directly (no embedding round-trip)."""
    model = ltm.MemoryModel
    with ltm.Session() as session:
        row = model(
            user_id=user_id,
            text=text,
            meta_data={"source": source, "collection": "context"},
            collection="context",
        )
        session.add(row)
        session.commit()
        return row.id


class TestDeleteExtractedMemories:
    async def test_only_extraction_rows_for_the_user_are_deleted(self, ltm):
        internal_user_id = await ltm._resolve_user_id_async(None)
        seed_memory(ltm, internal_user_id, "Likes tea", "extraction")
        seed_memory(ltm, internal_user_id, "Works at Automaze", "extraction")
        seed_memory(ltm, internal_user_id, "raw conversation text", "conversation")

        # A second user's extraction row must survive the reset.
        from muxi.runtime.services.memory.long_term import User
        from muxi.runtime.utils.id_generator import get_default_nanoid

        with ltm.Session() as session:
            other = User(public_id=get_default_nanoid(), formation_id=FORMATION_ID)
            session.add(other)
            session.commit()
            other_id = other.id
        seed_memory(ltm, other_id, "Other user's fact", "extraction")

        deleted = await ltm.delete_extracted_memories()
        assert deleted == 2

        with ltm.Session() as session:
            remaining = session.execute(select(ltm.MemoryModel.text)).scalars().all()
        assert sorted(remaining) == ["Other user's fact", "raw conversation text"]

    async def test_no_rows_returns_zero(self, ltm):
        assert await ltm.delete_extracted_memories() == 0

    async def test_reset_is_a_single_bulk_delete(self, ltm):
        internal_user_id = await ltm._resolve_user_id_async(None)
        for index in range(5):
            seed_memory(ltm, internal_user_id, f"fact {index}", "extraction")
        seed_memory(ltm, internal_user_id, "conversation", "conversation")

        statements = []
        sync_engine = ltm.db_manager.async_engine.sync_engine

        def record_statement(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(sync_engine, "before_cursor_execute", record_statement)
        try:
            deleted = await ltm.delete_extracted_memories()
        finally:
            event.remove(sync_engine, "before_cursor_execute", record_statement)

        assert deleted == 5
        deletes = [s for s in statements if s.lstrip().upper().startswith("DELETE")]
        assert len(deletes) == 1  # one bulk statement, not one per memory
        assert "json_extract" in deletes[0].lower()  # filtered in SQL, not in Python
        # The memories table is never SELECTed: rows stay out of process memory.
        table = ltm.MemoryModel.__tablename__
        selects = [
            s for s in statements if s.lstrip().upper().startswith("SELECT") and table in s.lower()
        ]
        assert selects == []

    def test_postgres_dialect_compiles_to_json_path_operator(self, ltm):
        """The same expression renders meta_data ->> 'source' on PostgreSQL."""
        from sqlalchemy import JSON, delete, type_coerce
        from sqlalchemy.dialects import postgresql

        model = ltm.MemoryModel
        marker = type_coerce(model.meta_data, JSON)["source"].as_string()
        stmt = delete(model).where(model.user_id == 1).where(marker == "extraction")
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "meta_data ->> " in compiled
