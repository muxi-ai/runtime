#!/usr/bin/env python3
"""
@migration: add_job_metadata_column
@generated: 2025-06-22 22:25:45
@description: ...
"""


def up() -> str:
    """
    Add job_metadata column to scheduled_jobs table.
    This column was renamed from 'metadata' to avoid SQLAlchemy conflicts.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Add job_metadata column to scheduled_jobs table
        ALTER TABLE scheduled_jobs ADD COLUMN job_metadata TEXT DEFAULT '{}';

        -- Create index for job_metadata if needed for performance (PostgreSQL only)
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_job_metadata ON scheduled_jobs USING gin ((job_metadata::jsonb));
    """


def down() -> str:
    """
    Remove job_metadata column from scheduled_jobs table.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Remove job_metadata column and its index
        DROP INDEX IF EXISTS idx_scheduled_jobs_job_metadata;
        ALTER TABLE scheduled_jobs DROP COLUMN IF EXISTS job_metadata;
    """
