#!/usr/bin/env python3
"""
Migration to remove redundant external_user_id column from scheduled_jobs table.

Since we now have a proper foreign key relationship to users table,
we can get the external_user_id through a JOIN when needed.
"""

import asyncio
from sqlalchemy import text
from src.muxi.runtime.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Remove external_user_id column from scheduled_jobs table."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            print("Removing redundant external_user_id column from scheduled_jobs...")

            # Check if column exists
            result = await session.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'scheduled_jobs'
                AND column_name = 'external_user_id'
            """))

            if result.fetchone():
                # Drop the column
                await session.execute(text("""
                    ALTER TABLE scheduled_jobs
                    DROP COLUMN external_user_id
                """))
                print("✅ Removed external_user_id column from scheduled_jobs")
            else:
                print("ℹ️  Column external_user_id does not exist in scheduled_jobs")

            await session.commit()
            print("\n✅ Migration completed successfully!")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Add external_user_id column back to scheduled_jobs table."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            print("Adding external_user_id column back to scheduled_jobs...")

            # Add column back
            await session.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN external_user_id VARCHAR(255)
            """))

            # Populate it from users table
            await session.execute(text("""
                UPDATE scheduled_jobs sj
                SET external_user_id = u.external_user_id
                FROM users u
                WHERE sj.user_id = u.id
            """))

            # Make it NOT NULL after populating
            result = await session.execute(text("""
                SELECT COUNT(*) FROM scheduled_jobs
            """))
            count = result.scalar()

            if count > 0:
                await session.execute(text("""
                    ALTER TABLE scheduled_jobs
                    ALTER COLUMN external_user_id SET NOT NULL
                """))

            await session.commit()
            print("✅ Rollback completed successfully")

        except Exception as e:
            await session.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python remove_scheduled_jobs_external_user_id.py <up|down> <connection_string>")
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
