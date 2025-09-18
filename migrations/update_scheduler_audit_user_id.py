#!/usr/bin/env python3
"""
Migration: Update scheduled_job_audit table user_id column type

Changes user_id from INTEGER (foreign key to users.id) to VARCHAR(255)
to store external_user_id directly instead of internal user id.

This fixes the issue where audit entries fail because we pass string
external_user_id but the column expects integer user_id.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, os.getcwd())

from src.muxi.services.db import DatabaseManager  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def migrate_up():
    """Apply migration - change user_id to VARCHAR."""
    db = DatabaseManager(connection_string="postgresql://ran@127.0.0.1/muxi_framework")

    try:
        with db.get_session() as session:
            # Drop any foreign key constraints on user_id
            session.execute(text("""
                ALTER TABLE scheduled_job_audit
                DROP CONSTRAINT IF EXISTS scheduled_job_audit_user_id_fkey
            """))
            session.execute(text("""
                ALTER TABLE scheduled_job_audit
                DROP CONSTRAINT IF EXISTS fk_scheduled_job_audit_user_id
            """))

            # Change column type from INTEGER to VARCHAR(255)
            session.execute(text("""
                ALTER TABLE scheduled_job_audit
                ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::VARCHAR
            """))

            session.commit()
            print("✅ Migration successful: user_id column updated to VARCHAR(255)")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        pass  # DatabaseManager doesn't need explicit close


async def migrate_down():
    """Rollback migration - change user_id back to INTEGER."""
    db = DatabaseManager(connection_string="postgresql://ran@127.0.0.1/muxi_framework")

    try:
        with db.get_session() as session:
            # Note: This will fail if there are non-numeric user_ids
            session.execute(text("""
                ALTER TABLE scheduled_job_audit
                ALTER COLUMN user_id TYPE INTEGER USING user_id::INTEGER
            """))

            # Re-add foreign key constraint
            session.execute(text("""
                ALTER TABLE scheduled_job_audit
                ADD CONSTRAINT scheduled_job_audit_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES users(id)
            """))

            session.commit()
            print("✅ Rollback successful: user_id column reverted to INTEGER")

    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        raise
    finally:
        pass  # DatabaseManager doesn't need explicit close


async def check_current_schema():
    """Check current schema of the audit table."""
    db = DatabaseManager(connection_string="postgresql://ran@127.0.0.1/muxi_framework")

    try:
        with db.get_session() as session:
            result = session.execute(text("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_name = 'scheduled_job_audit'
                AND column_name = 'user_id'
            """))

            row = result.fetchone()
            if row:
                print(f"Current user_id column: type={row[1]}, max_length={row[2]}")
                return row[1].lower()
            else:
                print("No user_id column found in scheduled_job_audit table")
                return None

    finally:
        pass  # DatabaseManager doesn't need explicit close


async def main():
    """Run migration with safety checks."""
    print("=" * 60)
    print("SCHEDULER AUDIT TABLE MIGRATION")
    print("=" * 60)

    # Check current schema
    print("\nChecking current schema...")
    current_type = await check_current_schema()

    if current_type is None:
        print("❌ Table or column doesn't exist")
        return 1

    if current_type == "character varying":
        print("✅ Column is already VARCHAR - no migration needed")
        return 0

    if current_type == "integer":
        print("Column is INTEGER - migration needed")

        # Run migration
        print("\nApplying migration...")
        try:
            await migrate_up()

            # Verify migration
            print("\nVerifying migration...")
            new_type = await check_current_schema()
            if new_type == "character varying":
                print("✅ Migration verified successfully")
                return 0
            else:
                print(f"❌ Migration verification failed: type is {new_type}")
                return 1

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            return 1
    else:
        print(f"⚠️ Unexpected column type: {current_type}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
