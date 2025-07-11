#!/usr/bin/env python3
"""
@migration: revert_credentials_fulltext_search
@generated: 2025-07-11 12:00:00
@description: Reverts the full-text search functionality added to credentials table
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Drop trigger for automatic tsvector updates
        DROP TRIGGER IF EXISTS update_credentials_name_tsv ON credentials;
        
        -- Drop function for updating tsvector
        DROP FUNCTION IF EXISTS update_credentials_name_tsv();
        
        -- Drop indexes for full-text search and trigram matching
        DROP INDEX IF EXISTS idx_credentials_name_tsv;
        DROP INDEX IF EXISTS idx_credentials_name_trgm;
        
        -- Drop the tsvector column
        ALTER TABLE credentials
        DROP COLUMN IF EXISTS name_tsv;
        
        -- Note: We're keeping the pg_trgm extension as it might be used elsewhere
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Re-add tsvector column for full-text search
        ALTER TABLE credentials
        ADD COLUMN IF NOT EXISTS name_tsv tsvector;
        
        -- Update existing rows to populate tsvector
        UPDATE credentials
        SET name_tsv = to_tsvector('english', name)
        WHERE name_tsv IS NULL;
        
        -- Recreate GIN index on tsvector column for full-text search
        CREATE INDEX IF NOT EXISTS idx_credentials_name_tsv
        ON credentials USING gin(name_tsv);
        
        -- Recreate trigram GIN index for fuzzy matching
        CREATE INDEX IF NOT EXISTS idx_credentials_name_trgm
        ON credentials USING gin(name gin_trgm_ops);
        
        -- Recreate function to automatically update tsvector
        CREATE OR REPLACE FUNCTION update_credentials_name_tsv()
        RETURNS trigger AS $$
        BEGIN
            NEW.name_tsv := to_tsvector('english', NEW.name);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        
        -- Recreate trigger for automatic tsvector updates
        CREATE TRIGGER update_credentials_name_tsv
        BEFORE INSERT OR UPDATE ON credentials
        FOR EACH ROW
        EXECUTE FUNCTION update_credentials_name_tsv();
    """