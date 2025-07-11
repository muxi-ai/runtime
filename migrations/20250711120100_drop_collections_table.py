#!/usr/bin/env python3
"""
@migration: drop_collections_table
@generated: 2025-07-11 12:01:00
@description: Drops the collections table and all related indexes
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Drop all indexes related to collections table
        DROP INDEX IF EXISTS idx_collections_collection_id;
        DROP INDEX IF EXISTS idx_collections_user_id;
        
        -- Drop the collections table (CASCADE will handle any dependent objects)
        DROP TABLE IF EXISTS collections CASCADE;
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Recreate the collections table
        CREATE TABLE collections (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            collection_id CHAR(21) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Recreate indexes for faster lookups
        CREATE INDEX idx_collections_user_id ON collections(user_id);
        CREATE INDEX idx_collections_collection_id ON collections(collection_id);
    """