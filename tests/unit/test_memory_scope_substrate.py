"""Unit tests for the memory-namespaces Phase 1 scope substrate.

Long-term memory rows gain ``scope_type`` / ``scope_id`` columns with
pure user-scope semantics: every write stamps ``('user',
str(internal_user_id))``, existing rows read as user scope through the
server-side ``scope_type`` default, and a NULL ``scope_id`` means "the
row's owning user_id" (no backfill UPDATE — the same additive migration
posture as the meta_data / derived_from_event_ids columns).

Covered here:
  * Fresh SQLite databases get the scope columns and the scope index,
    and writes stamp user scope.
  * Existing (legacy) SQLite databases are ALTER-migrated additively:
    columns appear, old rows stay readable and report the user-scope
    default, and search results over a seeded fixture are identical to
    the pre-migration query output (regression pin — Phase 1 must be a
    zero-behavior change).
  * ``_migrate_add_scope_columns`` (the runtime migration used by
    ``_create_all_database_tables`` for the SQLAlchemy-owned backends)
    is additive and idempotent on its SQLite branch.

The PostgreSQL branches (``ADD COLUMN IF NOT EXISTS`` + the ORM
server_default) are pinned structurally in
``tests/unit/test_memory_model_factory.py`` and exercised end-to-end by
the e2e suite — unit tests run without a PostgreSQL server.

Patches ``probe_dimension`` / ``embed`` (as imported into ``sqlite``)
to avoid any OneLLM / network / HF calls.
"""

from __future__ import annotations

import hashlib
import sqlite3
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from muxi.runtime.services.memory.sqlite import SQLiteMemory

DIM = 768
MODEL = "local/nomic-ai/nomic-embed-text-v1.5"


def _deterministic_vec(text: str, dim: int = DIM) -> list[float]:
    """Hash text into a stable float32 vector (same trick as the
    ``test_sqlite_embedding`` suite) so add/search vectors line up."""
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32).tolist()


def _deterministic_embed(model, text, *, task=None, **_kw):
    if isinstance(text, list):
        return [_deterministic_vec(t) for t in text]
    return [_deterministic_vec(text)]


def _patched():
    return (
        patch(
            "muxi.runtime.services.memory.sqlite.probe_dimension",
            new_callable=AsyncMock,
        ),
        patch(
            "muxi.runtime.services.memory.sqlite.embed",
            new_callable=AsyncMock,
        ),
    )


def _table_columns(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "memory.db")


LEGACY_SCHEMA = f"""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    identifier TEXT NOT NULL,
    identifier_type TEXT,
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(identifier, formation_id)
);
CREATE TABLE memories_{DIM} (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


def _seed_legacy_db(db_path: str, formation_id: str, texts: list[str]) -> None:
    """Create a pre-scope-substrate database with seeded memory rows."""
    conn = sqlite3.connect(db_path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO users (public_id, formation_id) VALUES (?, ?)",
        ("legacy-public-id-000000", formation_id),
    )
    user_id = conn.execute("SELECT id FROM users").fetchone()[0]
    conn.execute(
        "INSERT INTO user_identifiers (user_id, identifier, formation_id) VALUES (?, ?, ?)",
        (user_id, "0", formation_id),
    )
    for i, text in enumerate(texts):
        blob = np.array(_deterministic_vec(text), dtype=np.float32).tobytes()
        conn.execute(
            f"INSERT INTO memories_{DIM} (id, user_id, collection, text, embedding, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"legacy-{i:017d}", user_id, "default", text, blob, "{}"),
        )
    conn.commit()
    conn.close()


async def test_fresh_db_has_scope_columns_and_writes_stamp_user_scope(db_path):
    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = _deterministic_embed

        mem = SQLiteMemory(db_path=db_path, formation_id="test-formation", embedding_model=MODEL)
        memory_id = await mem.add("scoped fact")

        columns = _table_columns(mem.conn, f"memories_{DIM}")
        assert "scope_type" in columns
        assert "scope_id" in columns

        row = mem.conn.execute(
            f"SELECT scope_type, scope_id, user_id FROM memories_{DIM} WHERE id = ?",
            (memory_id,),
        ).fetchone()
        assert row[0] == "user"
        assert row[1] == str(row[2])  # scope_id mirrors the owning user id

        # The scope fan-out index exists alongside the legacy indexes.
        indexes = {r[1] for r in mem.conn.execute(f"PRAGMA index_list(memories_{DIM})").fetchall()}
        assert f"idx_memories_{DIM}_scope" in indexes


async def test_legacy_db_migrates_additively_and_search_is_unchanged(db_path):
    """Columns appear on an old DB, old rows stay readable as user scope,
    and vector search over the seeded fixture returns exactly what the
    pre-migration query returned (zero-behavior-change regression pin)."""
    formation_id = "test-formation"
    seeded = ["the sky is blue", "cats purr", "water boils at 100C"]
    _seed_legacy_db(db_path, formation_id, seeded)

    # Pre-migration search baseline, computed with the exact query shape
    # the runtime used before the scope columns existed.
    query_blob = np.array(_deterministic_vec("cats purr"), dtype=np.float32).tobytes()
    baseline_conn = sqlite3.connect(db_path)
    from muxi.runtime.extensions import SQLiteVecExtension

    SQLiteVecExtension.load_extension(baseline_conn)
    baseline = baseline_conn.execute(
        f"""
        SELECT m.text, vec_distance_cosine(m.embedding, ?) as score
        FROM memories_{DIM} m
        JOIN users u ON m.user_id = u.id
        WHERE u.formation_id = ?
        ORDER BY score ASC
        LIMIT 5
        """,
        (query_blob, formation_id),
    ).fetchall()
    baseline_conn.close()
    assert baseline[0][0] == "cats purr"

    probe_patch, embed_patch = _patched()
    with probe_patch as mock_probe, embed_patch as mock_embed:
        mock_probe.return_value = DIM
        mock_embed.side_effect = _deterministic_embed

        mem = SQLiteMemory(db_path=db_path, formation_id=formation_id, embedding_model=MODEL)
        # Trigger _ensure_dim -> _create_memories_table -> additive ALTER.
        results = await mem.search("cats purr", limit=5)

        # Columns appeared without touching existing rows.
        columns = _table_columns(mem.conn, f"memories_{DIM}")
        assert "scope_type" in columns
        assert "scope_id" in columns

        # Old rows read as user scope: scope_type backfills through the
        # column default; scope_id stays NULL ("the owning user_id").
        rows = mem.conn.execute(
            f"SELECT scope_type, scope_id FROM memories_{DIM} WHERE id LIKE 'legacy-%'"
        ).fetchall()
        assert len(rows) == len(seeded)
        assert all(r[0] == "user" and r[1] is None for r in rows)

        # Regression pin: identical result set and ordering pre/post.
        assert [r["text"] for r in results] == [text for text, _ in baseline]
        assert results[0]["text"] == "cats purr"

        # New writes into the migrated table stamp user scope.
        new_id = await mem.add("dogs bark")
        scope_type, scope_id, user_id = mem.conn.execute(
            f"SELECT scope_type, scope_id, user_id FROM memories_{DIM} WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert scope_type == "user"
        assert scope_id == str(user_id)

        # Old and new rows are searched together, scope-agnostically.
        results = await mem.search("dogs bark", limit=5)
        assert results[0]["text"] == "dogs bark"
        assert {r["text"] for r in results} == set(seeded) | {"dogs bark"}


class _FakeDBManager:
    """Minimal stand-in for DatabaseManager as read by the scope migrations."""

    database_type = "sqlite"

    def __init__(self, engine):
        self.engine = engine


def test_migrate_add_scope_columns_is_additive_and_idempotent(tmp_path):
    """The runtime migration used by _create_all_database_tables adds the
    columns to an old-schema table and is a no-op when re-run."""
    from sqlalchemy import create_engine, text

    from muxi.runtime.formation.initialization import _migrate_add_scope_columns

    db_file = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE memories_384 ("
                "id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, "
                "collection TEXT NOT NULL, text TEXT NOT NULL, "
                "embedding BLOB NOT NULL, metadata TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO memories_384 (id, user_id, collection, text, embedding) "
                "VALUES ('m1', 1, 'default', 'old row', x'00')"
            )
        )
        conn.commit()

    db_manager = _FakeDBManager(engine)
    _migrate_add_scope_columns(db_manager, "memories_384")
    # Idempotent: a second run must not raise or duplicate columns.
    _migrate_add_scope_columns(db_manager, "memories_384")

    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(memories_384)"))]
        assert columns.count("scope_type") == 1
        assert columns.count("scope_id") == 1
        # The pre-existing row reads as user scope via the column default.
        row = conn.execute(
            text("SELECT scope_type, scope_id FROM memories_384 WHERE id = 'm1'")
        ).fetchone()
        assert row[0] == "user"
        assert row[1] is None

    # Missing table: swallowed (create_tables owns first-run creation).
    _migrate_add_scope_columns(db_manager, "memories_9999")


def test_migrate_scope_columns_covers_all_dimension_tables(tmp_path):
    """A database carrying memories tables from other embedding dimensions
    (e.g. after switching embedding models) gets scope columns on ALL of
    them, not just the active dimension's -- and companion tables that
    merely share the prefix are left alone."""
    from sqlalchemy import create_engine, text

    from muxi.runtime.formation.initialization import _migrate_scope_columns_all_dims

    db_file = tmp_path / "runtime.db"
    engine = create_engine(f"sqlite:///{db_file}")
    old_schema = (
        "id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, "
        "collection TEXT NOT NULL, text TEXT NOT NULL, "
        "embedding BLOB NOT NULL, metadata TEXT"
    )
    with engine.connect() as conn:
        # Two old-schema dimension tables (embedding model was switched)
        # plus a companion table that matches the prefix but not the
        # memories_{dim} pattern.
        conn.execute(text(f"CREATE TABLE memories_384 ({old_schema})"))
        conn.execute(text(f"CREATE TABLE memories_768 ({old_schema})"))
        conn.execute(text("CREATE TABLE memories_384_fts (id TEXT PRIMARY KEY)"))
        conn.commit()

    db_manager = _FakeDBManager(engine)
    # Active table is a third dimension that doesn't exist yet -- its
    # migration is swallowed (create_tables owns first-run creation).
    _migrate_scope_columns_all_dims(db_manager, "memories_1536")

    with engine.connect() as conn:
        for table in ("memories_384", "memories_768"):
            columns = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
            assert "scope_type" in columns, table
            assert "scope_id" in columns, table
        # The companion table was not altered.
        fts_columns = [row[1] for row in conn.execute(text("PRAGMA table_info(memories_384_fts)"))]
        assert "scope_type" not in fts_columns
        assert "scope_id" not in fts_columns
