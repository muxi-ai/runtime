#!/usr/bin/env python3
"""
@migration: cleanup_credentials_indexes
@generated: 2025-07-11 13:00:00
@description: Remove unnecessary indexes from credentials table to improve write performance
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Drop unnecessary indexes that are never used in queries
        DROP INDEX IF EXISTS idx_credentials_updated_at;
        DROP INDEX IF EXISTS idx_credentials_service_lower;
        DROP INDEX IF EXISTS idx_credentials_json;
        DROP INDEX IF EXISTS idx_credentials_created_at;
        DROP INDEX IF EXISTS idx_credentials_credential_id;
        
        -- Note: Keeping these indexes as they are actually used:
        -- - idx_credentials_user_id (used for user lookups)
        -- - idx_credentials_service (used for service lookups)
        -- - credentials_credential_id_key (UNIQUE constraint)
        -- - credentials_pkey (PRIMARY KEY)
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Recreate the dropped indexes
        CREATE INDEX IF NOT EXISTS idx_credentials_updated_at ON credentials(updated_at);
        CREATE INDEX IF NOT EXISTS idx_credentials_service_lower ON credentials(lower(service::text));
        CREATE INDEX IF NOT EXISTS idx_credentials_json ON credentials USING gin(credentials);
        CREATE INDEX IF NOT EXISTS idx_credentials_created_at ON credentials(created_at);
        CREATE INDEX IF NOT EXISTS idx_credentials_credential_id ON credentials(credential_id);
    """