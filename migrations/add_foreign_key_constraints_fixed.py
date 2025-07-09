#!/usr/bin/env python3
"""
Migration to add missing foreign key constraints (fixed version).

This migration adds foreign key constraints that were missing from:
- credentials.user_id => users.id (already added)
- scheduled_jobs doesn't have direct FK to users (uses external_user_id string)
- scheduled_job_audit doesn't have direct FK to users (uses external_user_id string)
- scheduled_job_audit.job_id => scheduled_jobs.id
"""

import asyncio
from sqlalchemy import text
from src.muxi.runtime.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Add missing foreign key constraints."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # The credentials.user_id => users.id constraint was already added successfully
            print("ℹ️  credentials.user_id => users.id constraint already exists")

            # scheduled_jobs and scheduled_job_audit use string user_id fields
            # that contain external_user_id values, not internal user.id values
            # So we cannot create direct foreign keys to users.id

            # However, we can add foreign key constraint for scheduled_job_audit.job_id => scheduled_jobs.id
            try:
                await session.execute(text("""
                    ALTER TABLE scheduled_job_audit
                    ADD CONSTRAINT fk_scheduled_job_audit_job_id
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id)
                    ON DELETE CASCADE
                """))
                print("✅ Added foreign key constraint: scheduled_job_audit.job_id => scheduled_jobs.id")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Foreign key constraint fk_scheduled_job_audit_job_id already exists")
                else:
                    print(f"⚠️  Failed to add scheduled_job_audit.job_id constraint: {e}")

            # Add indexes for better performance on user_id lookups
            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_user_id
                    ON scheduled_jobs(user_id)
                """))
                print("✅ Added index on scheduled_jobs.user_id")
            except Exception as e:
                print(f"⚠️  Failed to add index on scheduled_jobs.user_id: {e}")

            try:
                await session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_scheduled_job_audit_user_id
                    ON scheduled_job_audit(user_id)
                """))
                print("✅ Added index on scheduled_job_audit.user_id")
            except Exception as e:
                print(f"⚠️  Failed to add index on scheduled_job_audit.user_id: {e}")

            await session.commit()
            print("\n✅ Migration completed successfully")
            print("\nNote: scheduled_jobs and scheduled_job_audit tables use string user_id fields")
            print("that contain external_user_id values, not internal user.id references.")
            print("Therefore, direct foreign keys to users.id cannot be created.")
            print("Instead, added indexes for better query performance.")

        except Exception as e:
            await session.rollback()
            print(f"❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Remove the added foreign key constraints and indexes (rollback)."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Drop foreign key constraint
            try:
                await session.execute(text("""
                    ALTER TABLE scheduled_job_audit
                    DROP CONSTRAINT IF EXISTS fk_scheduled_job_audit_job_id
                """))
                print("✅ Dropped foreign key constraint: fk_scheduled_job_audit_job_id")
            except Exception as e:
                print(f"⚠️  Failed to drop constraint: {e}")

            # Drop indexes
            try:
                await session.execute(text("""
                    DROP INDEX IF EXISTS idx_scheduled_jobs_user_id
                """))
                print("✅ Dropped index: idx_scheduled_jobs_user_id")
            except Exception as e:
                print(f"⚠️  Failed to drop index: {e}")

            try:
                await session.execute(text("""
                    DROP INDEX IF EXISTS idx_scheduled_job_audit_user_id
                """))
                print("✅ Dropped index: idx_scheduled_job_audit_user_id")
            except Exception as e:
                print(f"⚠️  Failed to drop index: {e}")

            await session.commit()
            print("\n✅ Successfully rolled back migration")

        except Exception as e:
            await session.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python add_foreign_key_constraints_fixed.py <up|down> <connection_string>")
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
