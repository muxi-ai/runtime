#!/usr/bin/env python3
"""
Migration to add missing foreign key constraints.

This migration adds foreign key constraints that were missing from:
- credentials.user_id => users.id
- scheduled_job_audit.user_id => users.id
- scheduled_jobs.user_id => users.id
- scheduled_job_audit.job_id => scheduled_jobs.job_id
"""

import asyncio
from sqlalchemy import text
from src.muxi.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Add missing foreign key constraints."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Add foreign key constraint for credentials.user_id
            try:
                await session.execute(text("""
                    ALTER TABLE credentials
                    ADD CONSTRAINT fk_credentials_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
                """))
                print("✅ Added foreign key constraint: credentials.user_id => users.id")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Foreign key constraint fk_credentials_user_id already exists")
                else:
                    print(f"⚠️  Failed to add credentials.user_id constraint: {e}")

            # Add foreign key constraint for scheduled_jobs.user_id
            try:
                await session.execute(text("""
                    ALTER TABLE scheduled_jobs
                    ADD CONSTRAINT fk_scheduled_jobs_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
                """))
                print("✅ Added foreign key constraint: scheduled_jobs.user_id => users.id")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Foreign key constraint fk_scheduled_jobs_user_id already exists")
                else:
                    print(f"⚠️  Failed to add scheduled_jobs.user_id constraint: {e}")

            # Add foreign key constraint for scheduled_job_audit.user_id
            try:
                await session.execute(text("""
                    ALTER TABLE scheduled_job_audit
                    ADD CONSTRAINT fk_scheduled_job_audit_user_id
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    ON DELETE CASCADE
                """))
                print("✅ Added foreign key constraint: scheduled_job_audit.user_id => users.id")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Foreign key constraint fk_scheduled_job_audit_user_id already exists")
                else:
                    print(f"⚠️  Failed to add scheduled_job_audit.user_id constraint: {e}")

            # Add foreign key constraint for scheduled_job_audit.job_id
            try:
                await session.execute(text("""
                    ALTER TABLE scheduled_job_audit
                    ADD CONSTRAINT fk_scheduled_job_audit_job_id
                    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(job_id)
                    ON DELETE CASCADE
                """))
                print("✅ Added foreign key constraint: scheduled_job_audit.job_id => scheduled_jobs.job_id")
            except Exception as e:
                if "already exists" in str(e):
                    print("ℹ️  Foreign key constraint fk_scheduled_job_audit_job_id already exists")
                else:
                    print(f"⚠️  Failed to add scheduled_job_audit.job_id constraint: {e}")

            await session.commit()
            print("\n✅ Successfully added all missing foreign key constraints")

        except Exception as e:
            await session.rollback()
            print(f"❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Remove the added foreign key constraints (rollback)."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            # Drop foreign key constraints
            constraints = [
                "fk_credentials_user_id",
                "fk_scheduled_jobs_user_id",
                "fk_scheduled_job_audit_user_id",
                "fk_scheduled_job_audit_job_id"
            ]

            for constraint in constraints:
                table = constraint.replace("fk_", "").rsplit("_", 2)[0]
                try:
                    await session.execute(text(f"""
                        ALTER TABLE {table}
                        DROP CONSTRAINT IF EXISTS {constraint}
                    """))
                    print(f"✅ Dropped foreign key constraint: {constraint}")
                except Exception as e:
                    print(f"⚠️  Failed to drop constraint {constraint}: {e}")

            await session.commit()
            print("\n✅ Successfully rolled back migration")

        except Exception as e:
            await session.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python add_foreign_key_constraints.py <up|down> <connection_string>")
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
