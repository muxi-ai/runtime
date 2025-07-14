#!/usr/bin/env python3
"""
Migration to add nano ID column to users table.

This migration adds a public_id column that can be safely exposed in APIs
and dashboards without revealing internal database IDs.
"""

import asyncio
import nanoid
from sqlalchemy import text
from src.muxi.runtime.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Add public_id column to users table."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Add public_id column
            await session.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS public_id VARCHAR(21)
            """))

            # Get all existing users
            result = await session.execute(text("""
                SELECT id FROM users WHERE public_id IS NULL
            """))
            users = result.fetchall()

            # Generate nano IDs for existing users
            for user in users:
                nano_id = nanoid.generate(size=21)
                await session.execute(text("""
                    UPDATE users
                    SET public_id = :nano_id
                    WHERE id = :user_id
                """), {"nano_id": nano_id, "user_id": user[0]})

            # Make column NOT NULL after populating
            await session.execute(text("""
                ALTER TABLE users
                ALTER COLUMN public_id SET NOT NULL
            """))

            # Add unique constraint if it doesn't exist
            # First check if constraint already exists (PostgreSQL)
            result = await session.execute(text("""
                SELECT COUNT(*) FROM information_schema.table_constraints 
                WHERE table_name = 'users' 
                AND constraint_name = 'uq_users_public_id'
                AND constraint_type = 'UNIQUE'
            """))
            constraint_exists = result.scalar() > 0
            
            if not constraint_exists:
                # Also check SQLite style
                try:
                    result = await session.execute(text("""
                        SELECT sql FROM sqlite_master 
                        WHERE type = 'index' 
                        AND name = 'uq_users_public_id'
                    """))
                    constraint_exists = result.scalar() is not None
                except Exception:
                    # Not SQLite, continue with PostgreSQL approach
                    pass
            
            if not constraint_exists:
                await session.execute(text("""
                    ALTER TABLE users
                    ADD CONSTRAINT uq_users_public_id
                    UNIQUE (public_id)
                """))

            # Create index for fast lookups
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_public_id
                ON users(public_id)
            """))

            await session.commit()
            print("✅ Successfully added public_id column to users table")
            if users:
                print(f"   Generated nano IDs for {len(users)} existing users")

        except Exception as e:
            await session.rollback()
            print(f"❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Remove public_id column from users table (rollback)."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Drop the index first
            await session.execute(text("""
                DROP INDEX IF EXISTS idx_users_public_id
            """))

            # Drop the constraint
            await session.execute(text("""
                ALTER TABLE users
                DROP CONSTRAINT IF EXISTS uq_users_public_id
            """))

            # Drop the column
            await session.execute(text("""
                ALTER TABLE users
                DROP COLUMN IF EXISTS public_id
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
        print("Usage: python add_user_nanoid.py <up|down> <connection_string>")
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
