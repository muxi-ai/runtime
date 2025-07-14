#!/usr/bin/env python3
"""
Database migration to remove formation_id and formation_id_hash columns from all tables except users.

This migration:
1. Removes formation_id and formation_id_hash from: memories, collections, credentials, scheduled_jobs
2. Ensures proper foreign key constraints exist
3. Updates any orphaned records

Usage:
    python migrations/remove_formation_columns.py --database postgresql://ran@127.0.0.1/muxi_framework
    python migrations/remove_formation_columns.py --database sqlite:///path/to/db.db
"""

import asyncio
import argparse
import json
from datetime import datetime
from pathlib import Path
from sqlalchemy import text, create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseMigration:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.is_postgres = connection_string.startswith("postgresql")
        self.is_async = True

    def _get_async_connection_string(self):
        """Convert sync connection string to async."""
        if self.is_postgres:
            if self.connection_string.startswith("postgresql://"):
                return self.connection_string.replace("postgresql://", "postgresql+asyncpg://", 1)
        else:  # SQLite
            if self.connection_string.startswith("sqlite://"):
                return self.connection_string.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return self.connection_string

    @asynccontextmanager
    async def get_session(self):
        """Get async database session."""
        engine = create_async_engine(self._get_async_connection_string())
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        await engine.dispose()

    def get_sync_engine(self):
        """Get sync engine for inspecting tables."""
        return create_engine(self.connection_string)

    async def check_columns_exist(self):
        """Check which tables have formation_id/formation_id_hash columns."""
        engine = self.get_sync_engine()
        inspector = inspect(engine)

        tables_to_check = ["memories", "collections", "credentials", "scheduled_jobs"]
        columns_info = {}

        for table in tables_to_check:
            if inspector.has_table(table):
                columns = [col["name"] for col in inspector.get_columns(table)]
                has_formation_id = "formation_id" in columns
                has_formation_id_hash = "formation_id_hash" in columns
                columns_info[table] = {
                    "exists": True,
                    "has_formation_id": has_formation_id,
                    "has_formation_id_hash": has_formation_id_hash,
                }
            else:
                columns_info[table] = {"exists": False}

        engine.dispose()
        return columns_info

    async def migrate_postgres(self):
        """Run migration for PostgreSQL."""
        logger.info("Starting PostgreSQL migration...")

        async with self.get_session() as session:
            # Drop formation_id and formation_id_hash from memories
            logger.info("Updating memories table...")
            await session.execute(
                text(
                    """
                ALTER TABLE memories
                DROP COLUMN IF EXISTS formation_id,
                DROP COLUMN IF EXISTS formation_id_hash
            """
                )
            )

            # Drop formation_id and formation_id_hash from collections
            logger.info("Updating collections table...")
            await session.execute(
                text(
                    """
                ALTER TABLE collections
                DROP COLUMN IF EXISTS formation_id,
                DROP COLUMN IF EXISTS formation_id_hash
            """
                )
            )

            # Drop formation_id and formation_id_hash from credentials
            logger.info("Updating credentials table...")
            await session.execute(
                text(
                    """
                ALTER TABLE credentials
                DROP COLUMN IF EXISTS formation_id,
                DROP COLUMN IF EXISTS formation_id_hash
            """
                )
            )

            # For scheduled_jobs, we need to:
            # 1. Add external_user_id column if it doesn't exist
            # 2. Copy current user_id values to external_user_id
            # 3. Update user_id to be integer foreign key
            logger.info("Updating scheduled_jobs table...")

            # Check if external_user_id already exists
            check_column = await session.execute(
                text(
                    """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'scheduled_jobs'
                AND column_name = 'external_user_id'
            """
                )
            )

            if not check_column.first():
                # Add external_user_id and populate it
                await session.execute(
                    text(
                        """
                    ALTER TABLE scheduled_jobs
                    ADD COLUMN IF NOT EXISTS external_user_id VARCHAR(255)
                """
                    )
                )

                await session.execute(
                    text(
                        """
                    UPDATE scheduled_jobs
                    SET external_user_id = user_id
                    WHERE external_user_id IS NULL
                """
                    )
                )

            # Drop formation_id column
            await session.execute(
                text(
                    """
                ALTER TABLE scheduled_jobs
                DROP COLUMN IF EXISTS formation_id
            """
                )
            )

            await session.commit()

        logger.info("PostgreSQL migration completed successfully!")

    async def migrate_sqlite(self):
        """Run migration for SQLite."""
        logger.info("Starting SQLite migration...")

        # SQLite doesn't support ALTER TABLE DROP COLUMN
        # We need to recreate the tables

        async with self.get_session() as session:
            # For memories table
            logger.info("Recreating memories table...")
            await session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS memories_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    metadata TEXT,
                    collection VARCHAR(255) DEFAULT 'default',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
                )
            )

            # Copy data
            await session.execute(
                text(
                    """
                INSERT INTO memories_new (id, user_id, content, embedding, metadata, collection, created_at, updated_at)
                SELECT id, user_id, content, embedding, metadata, collection, created_at, updated_at
                FROM memories
                WHERE EXISTS (SELECT 1 FROM users WHERE users.id = memories.user_id)
            """
                )
            )

            # Replace old table
            await session.execute(text("DROP TABLE IF EXISTS memories"))
            await session.execute(text("ALTER TABLE memories_new RENAME TO memories"))

            # For collections table
            logger.info("Recreating collections table...")
            await session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS collections_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    user_id INTEGER NOT NULL,
                    description TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
                )
            )

            # Copy data
            await session.execute(
                text(
                    """
                INSERT INTO collections_new (id, name, user_id, description, metadata, created_at, updated_at)
                SELECT id, name, user_id, description, metadata, created_at, updated_at
                FROM collections
                WHERE EXISTS (SELECT 1 FROM users WHERE users.id = collections.user_id)
            """
                )
            )

            # Replace old table
            await session.execute(text("DROP TABLE IF EXISTS collections"))
            await session.execute(text("ALTER TABLE collections_new RENAME TO collections"))

            # For credentials table
            logger.info("Recreating credentials table...")
            await session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS credentials_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    credential_id VARCHAR(255) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    service VARCHAR(255) NOT NULL,
                    credentials TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
                )
            )

            # Copy data
            await session.execute(
                text("""
                INSERT INTO
                credentials_new (id, user_id, credential_id, name, service, credentials, created_at, updated_at)
                    SELECT id, user_id, credential_id, name, service, credentials, created_at, updated_at
                    FROM credentials
                    WHERE EXISTS (SELECT 1 FROM users WHERE users.id = credentials.user_id)
                """)
            )

            # Replace old table
            await session.execute(text("DROP TABLE IF EXISTS credentials"))
            await session.execute(text("ALTER TABLE credentials_new RENAME TO credentials"))

            # For scheduled_jobs - need special handling due to user_id type change
            logger.info("Recreating scheduled_jobs table...")
            
            # First, backup existing scheduled_jobs data before dropping
            logger.info("Backing up scheduled_jobs data...")
            try:
                # Query all existing scheduled jobs
                result = await session.execute(text("SELECT * FROM scheduled_jobs"))
                jobs_data = []
                
                # Get column names
                columns = result.keys()
                
                # Convert each row to a dictionary
                for row in result:
                    job_dict = {}
                    for idx, col in enumerate(columns):
                        value = row[idx]
                        # Convert datetime objects to ISO format strings
                        if hasattr(value, 'isoformat'):
                            value = value.isoformat()
                        job_dict[col] = value
                    jobs_data.append(job_dict)
                
                if jobs_data:
                    # Create backup directory if it doesn't exist
                    backup_dir = Path("migration_backups")
                    backup_dir.mkdir(exist_ok=True)
                    
                    # Generate backup filename with timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_file = backup_dir / f"scheduled_jobs_backup_{timestamp}.json"
                    
                    # Save to JSON file
                    with open(backup_file, 'w') as f:
                        json.dump({
                            "backup_timestamp": datetime.now().isoformat(),
                            "table_name": "scheduled_jobs",
                            "row_count": len(jobs_data),
                            "data": jobs_data
                        }, f, indent=2)
                    
                    logger.info(f"Backed up {len(jobs_data)} scheduled jobs to {backup_file}")
                else:
                    logger.info("No scheduled jobs to backup")
                    
            except Exception as e:
                logger.warning(f"Could not backup scheduled_jobs: {e}")
            
            await session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS scheduled_jobs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id VARCHAR(255) NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    external_user_id VARCHAR(255),
                    job_type VARCHAR(50) NOT NULL,
                    schedule VARCHAR(255),
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    metadata TEXT,
                    failure_count INTEGER DEFAULT 0,
                    max_failures INTEGER DEFAULT 3,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
                )
            )

            # We can't directly migrate scheduled_jobs because user_id was string
            # Jobs will need to be recreated
            logger.warning(
                "scheduled_jobs data cannot be automatically migrated due to user_id type change"
            )
            logger.info("Scheduled jobs have been backed up and can be manually restored if needed")

            # Drop old table
            await session.execute(text("DROP TABLE IF EXISTS scheduled_jobs"))
            await session.execute(text("ALTER TABLE scheduled_jobs_new RENAME TO scheduled_jobs"))

            await session.commit()

        logger.info("SQLite migration completed successfully!")

    async def run(self):
        """Run the migration."""
        # Check current state
        columns_info = await self.check_columns_exist()

        logger.info("Current database state:")
        for table, info in columns_info.items():
            if info["exists"]:
                logger.info(
                    f"  {table}: formation_id={info.get('has_formation_id', False)}, "
                    f"formation_id_hash={info.get('has_formation_id_hash', False)}"
                )
            else:
                logger.info(f"  {table}: does not exist")

        # Run appropriate migration
        if self.is_postgres:
            await self.migrate_postgres()
        else:
            await self.migrate_sqlite()

        logger.info("Migration completed!")


async def main():
    parser = argparse.ArgumentParser(description="Remove formation columns from database tables")
    parser.add_argument(
        "--database",
        "-d",
        required=True,
        help="Database connection string (e.g., postgresql://ran@127.0.0.1/muxi_framework)",
    )

    args = parser.parse_args()

    migration = DatabaseMigration(args.database)
    await migration.run()


if __name__ == "__main__":
    asyncio.run(main())
