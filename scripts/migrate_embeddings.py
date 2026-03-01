#!/usr/bin/env python3
"""Migrate memories between dimension-specific tables.

Re-embeds all memories from memories_{from_dim} into memories_{to_dim}
using the target embedding model.  Supports PostgreSQL and SQLite.

Usage:
    # Local 384 -> OpenAI 1536
    python scripts/migrate_embeddings.py \
        --connection-string "postgresql://localhost/muxi" \
        --from-dim 384 --to-dim 1536 \
        --to-model "openai/text-embedding-3-small" \
        --openai-api-key "sk-YOUR_KEY_HERE"

    # OpenAI 1536 -> local 768
    python scripts/migrate_embeddings.py \
        --connection-string "postgresql://localhost/muxi" \
        --from-dim 1536 --to-dim 768 \
        --to-model "local/all-mpnet-base-v2"

    # SQLite
    python scripts/migrate_embeddings.py \
        --connection-string "memory.db" \
        --from-dim 384 --to-dim 1536 \
        --to-model "openai/text-embedding-3-small" \
        --openai-api-key "sk-YOUR_KEY_HERE"

    # Migrate legacy 'memories' table (no dimension suffix)
    python scripts/migrate_embeddings.py \
        --connection-string "postgresql://..." \
        --from-table "memories" --to-dim 1536 \
        --to-model "openai/text-embedding-3-small" \
        --openai-api-key "sk-YOUR_KEY_HERE"
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from typing import List, Optional, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


BATCH_SIZE = 50


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migrate memories between dimension-specific tables"
    )
    parser.add_argument(
        "--connection-string", required=True,
        help="PostgreSQL URI or SQLite .db file path",
    )
    parser.add_argument("--from-dim", type=int, help="Source dimension (e.g. 384)")
    parser.add_argument("--to-dim", type=int, required=True, help="Target dimension (e.g. 1536)")
    parser.add_argument(
        "--to-model", required=True,
        help='Target embedding model (e.g. "openai/text-embedding-3-small" or "local/all-mpnet-base-v2")',
    )
    parser.add_argument("--from-table", help='Override source table name (e.g. "memories" for legacy)')
    parser.add_argument("--openai-api-key", help="OpenAI API key (required for OpenAI models)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Batch size (default {BATCH_SIZE})")
    parser.add_argument("--dry-run", action="store_true", help="Show counts without migrating")
    return parser.parse_args()


def is_sqlite(conn_str: str) -> bool:
    return conn_str.endswith(".db") or "sqlite" in conn_str.lower()


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------


def get_embedder(model_name: str, api_key: Optional[str] = None):
    """Return an async callable(text) -> List[float]."""
    from muxi.runtime.services.memory.local_embeddings import is_local_model, resolve_local_model_name

    if is_local_model(model_name):
        bare = resolve_local_model_name(model_name)
        from muxi.runtime.services.memory.local_embeddings import LocalEmbeddingProvider

        provider = LocalEmbeddingProvider(model_name=bare)

        async def _embed(text: str) -> List[float]:
            return await provider.embed(text)

        return _embed
    else:
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        from muxi.runtime.services.llm import LLM

        llm = LLM(model=model_name)

        async def _embed(text: str) -> List[float]:
            resp = await llm.embed(text)
            if hasattr(resp, "data") and isinstance(resp.data, list):
                first = resp.data[0]
                if hasattr(first, "embedding"):
                    return first.embedding
                return list(first)
            return list(resp)

        return _embed


# ---------------------------------------------------------------------------
# PostgreSQL migration
# ---------------------------------------------------------------------------


async def migrate_postgres(args):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    conn_str = args.connection_string
    if conn_str.startswith("postgresql://"):
        conn_str = conn_str.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(conn_str)
    src_table = args.from_table or f"memories_{args.from_dim}"
    dst_table = f"memories_{args.to_dim}"

    async with engine.begin() as conn:
        # Check source table exists
        result = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"),
            {"t": src_table},
        )
        if not result.scalar():
            print(f"ERROR: source table '{src_table}' does not exist")
            return

        # Count
        result = await conn.execute(text(f"SELECT count(*) FROM {src_table}"))
        total = result.scalar()
        print(f"Source: {src_table} ({total} memories)")
        print(f"Target: {dst_table}")

        if args.dry_run:
            print("Dry run — no changes made.")
            await engine.dispose()
            return

        if total == 0:
            print("Nothing to migrate.")
            await engine.dispose()
            return

        # Ensure target table (let ORM handle it via get_memory_model)
        from muxi.runtime.services.memory.long_term import get_memory_model
        from muxi.runtime.services.db import Base

        get_memory_model(args.to_dim)
        await conn.run_sync(Base.metadata.create_all)

    embed = get_embedder(args.to_model, args.openai_api_key)

    migrated = 0
    start = time.time()

    async with engine.begin() as conn:
        rows = await conn.execute(
            text(f"SELECT id, user_id, text, meta_data, collection, created_at, updated_at FROM {src_table}")
        )
        all_rows = rows.fetchall()

    for i in range(0, len(all_rows), args.batch_size):
        batch = all_rows[i : i + args.batch_size]
        embeddings: List[Tuple[str, List[float]]] = []

        for row in batch:
            emb = await embed(row[2])  # row.text
            embeddings.append((row[0], emb))  # (id, embedding)

        async with engine.begin() as conn:
            for row, (rid, emb) in zip(batch, embeddings):
                # Check if already migrated
                existing = await conn.execute(
                    text(f"SELECT 1 FROM {dst_table} WHERE id = :id"), {"id": rid}
                )
                if existing.scalar():
                    continue

                await conn.execute(
                    text(
                        f"INSERT INTO {dst_table} (id, user_id, text, embedding, meta_data, collection, created_at, updated_at) "
                        f"VALUES (:id, :uid, :txt, :emb, :meta, :coll, :ca, :ua)"
                    ),
                    {
                        "id": rid,
                        "uid": row[1],
                        "txt": row[2],
                        "emb": str(emb),
                        "meta": row[3] if isinstance(row[3], str) else json.dumps(row[3] or {}),
                        "coll": row[4],
                        "ca": row[5],
                        "ua": row[6],
                    },
                )
                migrated += 1

        elapsed = time.time() - start
        print(f"  [{i + len(batch)}/{len(all_rows)}] migrated={migrated} ({elapsed:.1f}s)")

    await engine.dispose()
    elapsed = time.time() - start
    print(f"\nDone. Migrated {migrated} memories in {elapsed:.1f}s")
    print(f"Source table '{src_table}' was NOT deleted. Remove it manually if desired.")


# ---------------------------------------------------------------------------
# SQLite migration
# ---------------------------------------------------------------------------


async def migrate_sqlite(args):
    conn = sqlite3.connect(args.connection_string)

    src_table = args.from_table or f"memories_{args.from_dim}"
    dst_table = f"memories_{args.to_dim}"

    # Check source
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (src_table,)
    )
    if not cursor.fetchone():
        print(f"ERROR: source table '{src_table}' does not exist")
        conn.close()
        return

    cursor = conn.execute(f"SELECT count(*) FROM {src_table}")
    total = cursor.fetchone()[0]
    print(f"Source: {src_table} ({total} memories)")
    print(f"Target: {dst_table}")

    if args.dry_run:
        print("Dry run — no changes made.")
        conn.close()
        return

    if total == 0:
        print("Nothing to migrate.")
        conn.close()
        return

    # Ensure target table
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {dst_table} (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            collection TEXT NOT NULL,
            text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()

    embed = get_embedder(args.to_model, args.openai_api_key)

    import numpy as np

    rows = conn.execute(
        f"SELECT id, user_id, text, metadata, collection, created_at, updated_at FROM {src_table}"
    ).fetchall()

    migrated = 0
    start = time.time()

    for i in range(0, len(rows), args.batch_size):
        batch = rows[i : i + args.batch_size]

        for row in batch:
            rid = row[0]
            # Check if already migrated
            exists = conn.execute(f"SELECT 1 FROM {dst_table} WHERE id = ?", (rid,)).fetchone()
            if exists:
                continue

            emb = await embed(row[2])
            emb_blob = np.array(emb, dtype=np.float32).tobytes()

            conn.execute(
                f"INSERT INTO {dst_table} (id, user_id, collection, text, embedding, metadata, created_at, updated_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rid, row[1], row[4], row[2], emb_blob, row[3], row[5], row[6]),
            )
            migrated += 1

        conn.commit()
        elapsed = time.time() - start
        print(f"  [{i + len(batch)}/{len(rows)}] migrated={migrated} ({elapsed:.1f}s)")

    conn.close()
    elapsed = time.time() - start
    print(f"\nDone. Migrated {migrated} memories in {elapsed:.1f}s")
    print(f"Source table '{src_table}' was NOT deleted. Remove it manually if desired.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    args = parse_args()

    if not args.from_dim and not args.from_table:
        print("ERROR: must specify either --from-dim or --from-table")
        sys.exit(1)

    if args.from_dim == args.to_dim and not args.from_table:
        print("ERROR: --from-dim and --to-dim are the same")
        sys.exit(1)

    print(f"Embedding model: {args.to_model}")
    print(f"Target dimension: {args.to_dim}")
    print()

    if is_sqlite(args.connection_string):
        await migrate_sqlite(args)
    else:
        await migrate_postgres(args)


if __name__ == "__main__":
    asyncio.run(main())
