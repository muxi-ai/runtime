#!/usr/bin/env python3
"""
@migration: add_formation_id_columns
@generated: 2025-06-30 10:23:50
@description: Add formation_id and formation_id_hash columns to all memory tables for multi-formation support
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Add formation_id columns to users table
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS formation_id VARCHAR(255) NOT NULL DEFAULT 'default-formation',
        ADD COLUMN IF NOT EXISTS formation_id_hash VARCHAR(64) NOT NULL DEFAULT '0c7e6a405862e402eb76a70f8a26fc732d07c32fab7e6e5f72a4e9835c8e2d0a';

        -- Create indexes for users table
        CREATE INDEX IF NOT EXISTS idx_users_formation_id_hash ON users(formation_id_hash);
        CREATE INDEX IF NOT EXISTS idx_users_formation_user ON users(formation_id_hash, external_user_id_hash);

        -- Add formation_id columns to memories table
        ALTER TABLE memories
        ADD COLUMN IF NOT EXISTS formation_id VARCHAR(255) NOT NULL DEFAULT 'default-formation',
        ADD COLUMN IF NOT EXISTS formation_id_hash VARCHAR(64) NOT NULL DEFAULT '0c7e6a405862e402eb76a70f8a26fc732d07c32fab7e6e5f72a4e9835c8e2d0a';

        -- Create indexes for memories table
        CREATE INDEX IF NOT EXISTS idx_memories_formation_id_hash ON memories(formation_id_hash);
        CREATE INDEX IF NOT EXISTS idx_memories_formation_collection ON memories(formation_id_hash, collection);

        -- Add formation_id columns to collections table
        ALTER TABLE collections
        ADD COLUMN IF NOT EXISTS formation_id VARCHAR(255) NOT NULL DEFAULT 'default-formation',
        ADD COLUMN IF NOT EXISTS formation_id_hash VARCHAR(64) NOT NULL DEFAULT '0c7e6a405862e402eb76a70f8a26fc732d07c32fab7e6e5f72a4e9835c8e2d0a';

        -- Create indexes for collections table
        CREATE INDEX IF NOT EXISTS idx_collections_formation_id_hash ON collections(formation_id_hash);
        CREATE INDEX IF NOT EXISTS idx_collections_formation_name ON collections(formation_id_hash, name);

        -- Add formation_id columns to credentials table (if exists)
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'credentials') THEN
                ALTER TABLE credentials
                ADD COLUMN IF NOT EXISTS formation_id VARCHAR(255) NOT NULL DEFAULT 'default-formation',
                ADD COLUMN IF NOT EXISTS formation_id_hash VARCHAR(64) NOT NULL DEFAULT '0c7e6a405862e402eb76a70f8a26fc732d07c32fab7e6e5f72a4e9835c8e2d0a';

                -- Create index for credentials table
                CREATE INDEX IF NOT EXISTS idx_credentials_formation_id_hash ON credentials(formation_id_hash);
            END IF;
        END
        $$;

        -- Note: The hash '0c7e6a405862e402eb76a70f8a26fc732d07c32fab7e6e5f72a4e9835c8e2d0a'
        -- is the SHA256 hash of 'default-formation'
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Drop indexes first
        DROP INDEX IF EXISTS idx_users_formation_id_hash;
        DROP INDEX IF EXISTS idx_users_formation_user;
        DROP INDEX IF EXISTS idx_memories_formation_id_hash;
        DROP INDEX IF EXISTS idx_memories_formation_collection;
        DROP INDEX IF EXISTS idx_collections_formation_id_hash;
        DROP INDEX IF EXISTS idx_collections_formation_name;
        DROP INDEX IF EXISTS idx_credentials_formation_id_hash;

        -- Remove columns from users table
        ALTER TABLE users
        DROP COLUMN IF EXISTS formation_id,
        DROP COLUMN IF EXISTS formation_id_hash;

        -- Remove columns from memories table
        ALTER TABLE memories
        DROP COLUMN IF EXISTS formation_id,
        DROP COLUMN IF EXISTS formation_id_hash;

        -- Remove columns from collections table
        ALTER TABLE collections
        DROP COLUMN IF EXISTS formation_id,
        DROP COLUMN IF EXISTS formation_id_hash;

        -- Remove columns from credentials table (if exists)
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'credentials') THEN
                ALTER TABLE credentials
                DROP COLUMN IF EXISTS formation_id,
                DROP COLUMN IF EXISTS formation_id_hash;
            END IF;
        END
        $$;
    """
