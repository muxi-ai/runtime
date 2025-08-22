#!/usr/bin/env python3
"""
@migration: encrypt_credentials
@generated: 2025-08-22 00:00:00
@description: Convert plaintext JSONB credentials to encrypted TEXT format

NOTE: This migration requires a separate Python script to encrypt the data.
The migration only handles the schema changes.
"""


def up() -> str:
    """
    Returns the SQL for the forward migration.

    This migration:
    1. Adds encrypted_credentials TEXT column
    2. Migrates data (needs separate script)
    3. Drops old JSONB column
    4. Renames encrypted column to credentials

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Step 1: Add encrypted_credentials column
        ALTER TABLE credentials
        ADD COLUMN IF NOT EXISTS encrypted_credentials TEXT;

        -- Step 2: Copy existing data temporarily (will be encrypted by script)
        UPDATE credentials
        SET encrypted_credentials = credentials::text
        WHERE credentials IS NOT NULL;

        -- Step 3: Drop the old JSONB column
        ALTER TABLE credentials DROP COLUMN credentials;

        -- Step 4: Rename encrypted column to credentials
        ALTER TABLE credentials
        RENAME COLUMN encrypted_credentials TO credentials;

        -- Step 5: Add NOT NULL constraint
        ALTER TABLE credentials
        ALTER COLUMN credentials SET NOT NULL;

        -- Note: After this migration, run encrypt_credentials_data.py to encrypt the data
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Step 1: Add back the JSONB column
        ALTER TABLE credentials
        ADD COLUMN IF NOT EXISTS credentials_jsonb JSONB;

        -- Step 2: Copy data back (needs decryption script first)
        UPDATE credentials
        SET credentials_jsonb =
            CASE
                WHEN credentials IS NOT NULL AND credentials != ''
                THEN credentials::jsonb
                ELSE '{}'::jsonb
            END;

        -- Step 3: Drop the encrypted TEXT column
        ALTER TABLE credentials DROP COLUMN credentials;

        -- Step 4: Rename JSONB column back to credentials
        ALTER TABLE credentials
        RENAME COLUMN credentials_jsonb TO credentials;

        -- Step 5: Restore default and NOT NULL
        ALTER TABLE credentials
        ALTER COLUMN credentials SET DEFAULT '{}'::jsonb,
        ALTER COLUMN credentials SET NOT NULL;

        -- Note: Before this rollback, run decrypt_credentials_data.py to decrypt the data
    """
