#!/usr/bin/env python3
"""
Add indexes to credentials table for performance optimization.

This migration adds indexes to support efficient credential lookups
by user_id, service, and formation_id_hash.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


async def create_index_if_not_exists(conn, index_name: str, index_sql: str):
    """
    Create an index if it doesn't already exist.

    This function handles the creation of indexes in a database-agnostic way,
    checking for existing indexes using proper error handling rather than
    string matching.
    """
    try:
        await conn.execute(text(index_sql))
        return True
    except OperationalError as e:
        # For SQLite, check if the error is about an existing index
        # SQLite uses SQLITE_ERROR (1) for "index already exists"
        if hasattr(e.orig, "args") and len(e.orig.args) > 0:
            error_msg = str(e.orig.args[0]).lower()
            # Check for index already exists error
            if "already exists" in error_msg and "index" in error_msg:
                return False

        # For other databases or unknown errors, re-raise
        raise


async def add_indexes(connection_string: str):
    """Add indexes to credentials table."""

    # Convert connection string for async if needed
    if connection_string.startswith("postgresql://"):
        async_connection_string = connection_string.replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    elif connection_string.startswith("sqlite://"):
        async_connection_string = connection_string.replace("sqlite://", "sqlite+aiosqlite://")
    else:
        async_connection_string = connection_string

    engine = create_async_engine(async_connection_string, echo=True)

    async with engine.begin() as conn:
        print("Adding indexes to credentials table...")

        # Check if we're using PostgreSQL or SQLite
        if "postgresql" in async_connection_string:
            # PostgreSQL
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_credentials_user_service
                ON credentials(user_id, service, formation_id_hash);
            """
                )
            )

            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_credentials_user_formation
                ON credentials(user_id, formation_id_hash);
            """
                )
            )

            # Also add an index for service lookup (case-insensitive)
            await conn.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_credentials_service_lower
                ON credentials(LOWER(service));
            """
                )
            )

        else:
            # SQLite
            # Note: SQLite doesn't support IF NOT EXISTS for indexes in older versions
            # We'll use our helper function for robust error handling

            # Create first index
            await create_index_if_not_exists(
                conn,
                "idx_credentials_user_service",
                """
                CREATE INDEX idx_credentials_user_service
                ON credentials(user_id, service, formation_id_hash);
                """,
            )

            # Create second index
            await create_index_if_not_exists(
                conn,
                "idx_credentials_user_formation",
                """
                CREATE INDEX idx_credentials_user_formation
                ON credentials(user_id, formation_id_hash);
                """,
            )

            # Create third index
            await create_index_if_not_exists(
                conn,
                "idx_credentials_service_lower",
                """
                CREATE INDEX idx_credentials_service_lower
                ON credentials(service COLLATE NOCASE);
                """,
            )

        print("✅ Indexes added successfully!")

    await engine.dispose()


async def check_indexes(connection_string: str):
    """Check if indexes exist on credentials table."""

    # Convert connection string for async if needed
    if connection_string.startswith("postgresql://"):
        async_connection_string = connection_string.replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    elif connection_string.startswith("sqlite://"):
        async_connection_string = connection_string.replace("sqlite://", "sqlite+aiosqlite://")
    else:
        async_connection_string = connection_string

    engine = create_async_engine(async_connection_string, echo=False)

    async with engine.connect() as conn:
        if "postgresql" in async_connection_string:
            # PostgreSQL - check pg_indexes
            result = await conn.execute(
                text(
                    """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'credentials'
                AND schemaname = 'public'
                ORDER BY indexname;
            """
                )
            )
            indexes = [row[0] for row in result]

        else:
            # SQLite - check sqlite_master
            result = await conn.execute(
                text(
                    """
                SELECT name
                FROM sqlite_master
                WHERE type = 'index'
                AND tbl_name = 'credentials'
                ORDER BY name;
            """
                )
            )
            indexes = [row[0] for row in result]

        print("\nExisting indexes on credentials table:")
        for idx in indexes:
            print(f"  - {idx}")

    await engine.dispose()


def main():
    """Main migration runner."""
    if len(sys.argv) < 3:
        print("Usage: python add_credential_indexes.py <command> <connection_string>")
        print("Commands: migrate, check")
        print("Example: python add_credential_indexes.py migrate postgresql://user@localhost/db")
        sys.exit(1)

    command = sys.argv[1]
    connection_string = sys.argv[2]

    if command == "migrate":
        asyncio.run(add_indexes(connection_string))
    elif command == "check":
        asyncio.run(check_indexes(connection_string))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
