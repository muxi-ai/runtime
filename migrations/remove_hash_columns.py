#!/usr/bin/env python3
"""
Migration to remove hash columns from users table.

This migration removes the external_user_id_hash and formation_id_hash columns
that were used for optimization but add unnecessary complexity.
"""

import asyncio
from sqlalchemy import text
from src.muxi.runtime.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Remove hash columns from users table."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Drop the hash columns
            await session.execute(text("""
                ALTER TABLE users
                DROP COLUMN IF EXISTS external_user_id_hash,
                DROP COLUMN IF EXISTS formation_id_hash
            """))

            # Drop old unique constraints that use hash columns
            await session.execute(text("""
                ALTER TABLE users
                DROP CONSTRAINT IF EXISTS uq_user_formation_external_id
            """))

            # Try to add the new constraint (ignore if already exists)
            # Check if constraint exists before adding
            result = await session.execute(text("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name = 'users'
                AND constraint_name = 'uq_user_formation_external_id'
            """))

            if not result.fetchone():
                await session.execute(text("""
                    ALTER TABLE users
                    ADD CONSTRAINT uq_user_formation_external_id
                    UNIQUE (external_user_id, formation_id)
                """))

            # Create indexes on the normalized columns for performance
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_external_user_id
                ON users(external_user_id)
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_formation_id
                ON users(formation_id)
            """))

            await session.commit()
            print("✅ Successfully removed hash columns from users table")

        except Exception as e:
            await session.rollback()
            print(f"❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Add hash columns back to users table (rollback)."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Add hash columns back
            await session.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS external_user_id_hash VARCHAR(64),
                ADD COLUMN IF NOT EXISTS formation_id_hash VARCHAR(64)
            """))

            # Update hash values from existing data
            await session.execute(text("""
                UPDATE users
                SET external_user_id_hash = encode(sha256(external_user_id::bytea), 'hex'),
                    formation_id_hash = encode(sha256(formation_id::bytea), 'hex')
            """))

            # Make hash columns NOT NULL after populating
            await session.execute(text("""
                ALTER TABLE users
                ALTER COLUMN external_user_id_hash SET NOT NULL,
                ALTER COLUMN formation_id_hash SET NOT NULL
            """))

            # Recreate old constraints
            await session.execute(text("""
                ALTER TABLE users
                ADD CONSTRAINT uq_user_formation_external_id
                UNIQUE (external_user_id_hash, formation_id_hash)
            """))

            # Create indexes on hash columns
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_external_user_id_hash
                ON users(external_user_id_hash)
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_formation_id_hash
                ON users(formation_id_hash)
            """))

            await session.commit()
            print("✅ Successfully rolled back migration")

        except Exception as e:
            await session.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python remove_hash_columns.py <up|down> <connection_string>")
        sys.exit(1)

    direction = sys.argv[1]
    connection_string = sys.argv[2]

    if direction == "up":
        asyncio.run(migrate_up(connection_string))
    elif direction == "down":
        asyncio.run(migrate_down(connection_string))
    else:
        print("Direction must be 'up' or 'down'")
        sys.exit(1)
