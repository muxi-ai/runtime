#!/usr/bin/env python3
"""
@migration: enhance_user_schema
@generated: 2024-12-15
@description: Enhance existing user table to support flexible external IDs
WITHOUT breaking existing functionality
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- ADD columns to existing table instead of replacing
        ALTER TABLE users
        ADD COLUMN external_user_id TEXT NULL,
        ADD COLUMN external_user_id_hash VARCHAR(64) NULL;

        -- Create index on the hash column for performance
        CREATE INDEX idx_users_external_user_id_hash ON users(external_user_id_hash);

        -- Migrate existing user_id (CHAR(21)) values to external_user_id
        -- This preserves all existing user associations
        UPDATE users
        SET external_user_id = user_id,
            external_user_id_hash = encode(sha256(user_id::bytea), 'hex')
        WHERE external_user_id IS NULL;

        -- Now make external_user_id NOT NULL
        ALTER TABLE users
        ALTER COLUMN external_user_id SET NOT NULL,
        ALTER COLUMN external_user_id_hash SET NOT NULL;

        -- Add unique constraint for fast lookups
        ALTER TABLE users
        ADD CONSTRAINT uq_users_external_id_hash UNIQUE (external_user_id_hash);

        -- Keep existing user_id column for backward compatibility during transition
        -- Will be removed in later migration after all components updated
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Safe rollback - remove added columns
        ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_external_id_hash;
        DROP INDEX IF EXISTS idx_users_external_user_id_hash;
        ALTER TABLE users DROP COLUMN IF EXISTS external_user_id_hash;
        ALTER TABLE users DROP COLUMN IF EXISTS external_user_id;
    """
