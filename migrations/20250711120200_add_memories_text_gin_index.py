#!/usr/bin/env python3
"""
@migration: add_memories_text_gin_index
@generated: 2025-07-11 12:02:00
@description: Adds GIN index on memories.text column for better text search performance
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Create GIN index on text column for efficient full-text search
        CREATE INDEX IF NOT EXISTS idx_memories_text_gin 
        ON memories USING gin(to_tsvector('english', text));
        
        -- Also create a regular btree index for pattern matching (LIKE queries)
        CREATE INDEX IF NOT EXISTS idx_memories_text_pattern 
        ON memories (text text_pattern_ops);
        
        -- Create index on collection column for faster filtering
        CREATE INDEX IF NOT EXISTS idx_memories_collection
        ON memories (collection);
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Remove all indexes added by this migration
        DROP INDEX IF EXISTS idx_memories_text_gin;
        DROP INDEX IF EXISTS idx_memories_text_pattern;
        DROP INDEX IF EXISTS idx_memories_collection;
    """