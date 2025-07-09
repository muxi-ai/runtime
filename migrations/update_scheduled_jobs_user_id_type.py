#!/usr/bin/env python3
"""
Migration to update scheduled_jobs and scheduled_job_audit tables to use integer user_id.

This migration:
1. Adds new integer user_id columns
2. Migrates data from string user_id to integer (looking up users table)
3. Drops old string columns
4. Adds proper foreign key constraints
"""

import asyncio
from sqlalchemy import text
from src.muxi.runtime.services.db import get_database_manager


async def migrate_up(connection_string: str):
    """Update user_id columns to integer type and add foreign keys."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            print("Starting migration to update user_id columns to integer type...")

            # Step 1: Add new integer user_id columns
            print("\n1. Adding new integer user_id columns...")

            # Add user_id_new to scheduled_jobs
            await session.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN IF NOT EXISTS user_id_new INTEGER
            """))
            print("✅ Added user_id_new column to scheduled_jobs")

            # Add user_id_new to scheduled_job_audit
            await session.execute(text("""
                ALTER TABLE scheduled_job_audit
                ADD COLUMN IF NOT EXISTS user_id_new INTEGER
            """))
            print("✅ Added user_id_new column to scheduled_job_audit")

            # Step 2: Migrate data - look up users by external_user_id
            print("\n2. Migrating data from string user_id to integer user_id...")

            # Get all unique user_ids from scheduled_jobs
            result = await session.execute(text("""
                SELECT DISTINCT user_id FROM scheduled_jobs WHERE user_id IS NOT NULL
            """))
            job_user_ids = [row[0] for row in result.fetchall()]

            # Get all unique user_ids from scheduled_job_audit
            result = await session.execute(text("""
                SELECT DISTINCT user_id FROM scheduled_job_audit WHERE user_id IS NOT NULL
            """))
            audit_user_ids = [row[0] for row in result.fetchall()]

            # Combine and deduplicate
            all_user_ids = list(set(job_user_ids + audit_user_ids))
            print(f"Found {len(all_user_ids)} unique user_ids to migrate")

            # For each external_user_id, find the corresponding internal user.id
            for external_user_id in all_user_ids:
                # Find user in users table
                result = await session.execute(text("""
                    SELECT id FROM users
                    WHERE external_user_id = :external_user_id
                    LIMIT 1
                """), {"external_user_id": external_user_id})

                user_row = result.fetchone()
                if user_row:
                    internal_user_id = user_row[0]

                    # Update scheduled_jobs
                    await session.execute(text("""
                        UPDATE scheduled_jobs
                        SET user_id_new = :internal_user_id
                        WHERE user_id = :external_user_id
                    """), {
                        "internal_user_id": internal_user_id,
                        "external_user_id": external_user_id
                    })

                    # Update scheduled_job_audit
                    await session.execute(text("""
                        UPDATE scheduled_job_audit
                        SET user_id_new = :internal_user_id
                        WHERE user_id = :external_user_id
                    """), {
                        "internal_user_id": internal_user_id,
                        "external_user_id": external_user_id
                    })

                    print(f"  ✅ Migrated user_id '{external_user_id}' to internal ID {internal_user_id}")
                else:
                    print(f"  ⚠️  No user found for external_user_id '{external_user_id}'")

            # Step 3: Drop old columns and rename new ones
            print("\n3. Dropping old string columns and renaming new columns...")

            # Drop old user_id from scheduled_jobs
            await session.execute(text("""
                ALTER TABLE scheduled_jobs DROP COLUMN user_id
            """))
            print("✅ Dropped old user_id column from scheduled_jobs")

            # Rename user_id_new to user_id in scheduled_jobs
            await session.execute(text("""
                ALTER TABLE scheduled_jobs RENAME COLUMN user_id_new TO user_id
            """))
            print("✅ Renamed user_id_new to user_id in scheduled_jobs")

            # Drop old user_id from scheduled_job_audit
            await session.execute(text("""
                ALTER TABLE scheduled_job_audit DROP COLUMN user_id
            """))
            print("✅ Dropped old user_id column from scheduled_job_audit")

            # Rename user_id_new to user_id in scheduled_job_audit
            await session.execute(text("""
                ALTER TABLE scheduled_job_audit RENAME COLUMN user_id_new TO user_id
            """))
            print("✅ Renamed user_id_new to user_id in scheduled_job_audit")

            # Step 4: Add foreign key constraints
            print("\n4. Adding foreign key constraints...")

            # Add foreign key for scheduled_jobs.user_id
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
                    raise

            # Add foreign key for scheduled_job_audit.user_id
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
                    raise

            # The job_id foreign key should still work
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
                    raise

            # Step 5: Add NOT NULL constraint to user_id columns (only if there are rows)
            print("\n5. Checking if NOT NULL constraints can be added...")

            # Check if there are any rows in scheduled_jobs
            result = await session.execute(text("SELECT COUNT(*) FROM scheduled_jobs"))
            job_count = result.scalar()

            if job_count > 0:
                # Check if there are any NULL user_ids
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM scheduled_jobs WHERE user_id IS NULL
                """))
                null_count = result.scalar()

                if null_count == 0:
                    await session.execute(text("""
                        ALTER TABLE scheduled_jobs
                        ALTER COLUMN user_id SET NOT NULL
                    """))
                    print("✅ Added NOT NULL constraint to scheduled_jobs.user_id")
                else:
                    print(f"⚠️  Cannot add NOT NULL constraint to scheduled_jobs.user_id - {null_count} NULL values found")
            else:
                print("ℹ️  No rows in scheduled_jobs table - skipping NOT NULL constraint")

            # Check scheduled_job_audit
            result = await session.execute(text("SELECT COUNT(*) FROM scheduled_job_audit"))
            audit_count = result.scalar()

            if audit_count > 0:
                # Check if there are any NULL user_ids
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM scheduled_job_audit WHERE user_id IS NULL
                """))
                null_count = result.scalar()

                if null_count == 0:
                    await session.execute(text("""
                        ALTER TABLE scheduled_job_audit
                        ALTER COLUMN user_id SET NOT NULL
                    """))
                    print("✅ Added NOT NULL constraint to scheduled_job_audit.user_id")
                else:
                    print(f"⚠️  Cannot add NOT NULL constraint to scheduled_job_audit.user_id - {null_count} NULL values found")
            else:
                print("ℹ️  No rows in scheduled_job_audit table - skipping NOT NULL constraint")

            await session.commit()
            print("\n✅ Migration completed successfully!")

        except Exception as e:
            await session.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise


async def migrate_down(connection_string: str):
    """Revert user_id columns back to string type."""
    db_manager = get_database_manager(connection_string)

    async with db_manager.AsyncSession() as session:
        try:
            print("Starting rollback migration...")

            # Drop foreign key constraints first
            await session.execute(text("""
                ALTER TABLE scheduled_jobs
                DROP CONSTRAINT IF EXISTS fk_scheduled_jobs_user_id
            """))

            await session.execute(text("""
                ALTER TABLE scheduled_job_audit
                DROP CONSTRAINT IF EXISTS fk_scheduled_job_audit_user_id
            """))

            # Add string columns back
            await session.execute(text("""
                ALTER TABLE scheduled_jobs
                ADD COLUMN user_id_old VARCHAR(255)
            """))

            await session.execute(text("""
                ALTER TABLE scheduled_job_audit
                ADD COLUMN user_id_old VARCHAR(255)
            """))

            # Migrate data back (integer to string)
            await session.execute(text("""
                UPDATE scheduled_jobs sj
                SET user_id_old = u.external_user_id
                FROM users u
                WHERE sj.user_id = u.id
            """))

            await session.execute(text("""
                UPDATE scheduled_job_audit sja
                SET user_id_old = u.external_user_id
                FROM users u
                WHERE sja.user_id = u.id
            """))

            # Drop integer columns
            await session.execute(text("""
                ALTER TABLE scheduled_jobs DROP COLUMN user_id
            """))

            await session.execute(text("""
                ALTER TABLE scheduled_job_audit DROP COLUMN user_id
            """))

            # Rename old columns back
            await session.execute(text("""
                ALTER TABLE scheduled_jobs RENAME COLUMN user_id_old TO user_id
            """))

            await session.execute(text("""
                ALTER TABLE scheduled_job_audit RENAME COLUMN user_id_old TO user_id
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
        print("Usage: python update_scheduled_jobs_user_id_type.py <up|down> <connection_string>")
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
