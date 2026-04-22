"""Integration test for schema upgrade idempotency.

VAL-SCHEMA-005: applying the new ``init_schema_sqlite.sql`` to a DB
that already has a populated ``memories_1536`` table does not drop
data and does not fail. New dim tables (384, 768, 1024, 3072) are
created as expected.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def _pre_migration_schema() -> str:
    """Minimal pre-migration schema: only ``memories_1536`` exists."""
    return """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        public_id TEXT NOT NULL UNIQUE,
        formation_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS memories_1536 (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        collection TEXT NOT NULL DEFAULT 'default',
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        metadata TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_memories_1536_user_id ON memories_1536(user_id);
    """


def test_existing_1536_preserved(tmp_path):
    """VAL-SCHEMA-005: existing 1536-dim data survives schema upgrade."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    # Apply pre-migration schema and seed one row.
    conn.executescript(_pre_migration_schema())
    conn.execute("INSERT INTO users (public_id, formation_id) VALUES ('u0', 'legacy')")
    user_id = conn.execute("SELECT id FROM users WHERE public_id='u0'").fetchone()[0]
    seed_embedding = bytes([0] * 1536 * 4)  # 1536 float32 zeros
    conn.execute(
        "INSERT INTO memories_1536 (id, user_id, collection, text, embedding) "
        "VALUES (?, ?, ?, ?, ?)",
        ("legacy-id-1", user_id, "default", "legacy row", seed_embedding),
    )
    conn.commit()

    # Now apply the new schema — should be additive + idempotent.
    new_schema = Path("migrations/init_schema_sqlite.sql").read_text()
    conn.executescript(new_schema)
    conn.commit()

    # The legacy row must still be present.
    row = conn.execute("SELECT id, text FROM memories_1536 WHERE id = 'legacy-id-1'").fetchone()
    assert row == ("legacy-id-1", "legacy row")

    # All new dim tables must exist.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name LIKE 'memories_%' AND name NOT LIKE '%_fts%' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    assert set(names) >= {
        "memories_384",
        "memories_768",
        "memories_1024",
        "memories_1536",
        "memories_3072",
    }, names

    # Re-applying the schema must still succeed (idempotency).
    conn.executescript(new_schema)
    conn.commit()

    # And the legacy row is still there.
    row = conn.execute("SELECT id, text FROM memories_1536 WHERE id = 'legacy-id-1'").fetchone()
    assert row == ("legacy-id-1", "legacy row")

    conn.close()
