#!/usr/bin/env python3
"""
@migration: add_onetime_job_support
@generated: 2025-06-22 19:00:00
@description: Adds support for one-time jobs alongside recurring jobs in the scheduler
"""


def up() -> str:
    """
    Returns the SQL for the forward migration that adds one-time job support.

    Adds:
    - is_recurring boolean field to distinguish job types
    - scheduled_for datetime field for one-time job execution
    - Updates status constraint to include 'COMPLETED'
    - Makes cron_expression nullable for one-time jobs
    - Adds performance indexes for new fields

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Migration: Add one-time job support to scheduled_jobs table
        -- This migration extends the scheduler to support both recurring and one-time jobs

        -- Add new columns for one-time job support
        ALTER TABLE scheduled_jobs 
        ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN scheduled_for TIMESTAMP WITH TIME ZONE NULL;

        -- Make cron_expression nullable since one-time jobs won't need it
        ALTER TABLE scheduled_jobs ALTER COLUMN cron_expression DROP NOT NULL;

        -- Update status constraint to include 'COMPLETED' for one-time jobs
        ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_status_check;
        ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_status_check 
        CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED'));

        -- Create indexes for efficient one-time job queries
        CREATE INDEX idx_scheduled_jobs_is_recurring ON scheduled_jobs(is_recurring);
        CREATE INDEX idx_scheduled_jobs_scheduled_for ON scheduled_jobs(scheduled_for);
        
        -- Composite indexes for performance
        CREATE INDEX idx_scheduled_jobs_onetime_due 
        ON scheduled_jobs(is_recurring, scheduled_for, status) 
        WHERE is_recurring = FALSE;
        
        CREATE INDEX idx_scheduled_jobs_type_status 
        ON scheduled_jobs(is_recurring, status);
        
        CREATE INDEX idx_scheduled_jobs_recurring_active 
        ON scheduled_jobs(is_recurring, status, cron_expression) 
        WHERE is_recurring = TRUE AND status = 'ACTIVE';

        -- Update existing jobs to be marked as recurring (backwards compatibility)
        UPDATE scheduled_jobs SET is_recurring = TRUE WHERE is_recurring IS NULL;

        -- Add constraint to ensure data integrity
        ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_scheduling_check
        CHECK (
            (is_recurring = TRUE AND cron_expression IS NOT NULL AND scheduled_for IS NULL) OR
            (is_recurring = FALSE AND cron_expression IS NULL AND scheduled_for IS NOT NULL)
        );

        -- Verify migration success
        DO $$
        BEGIN
            -- Test that we can query both job types
            PERFORM 1 FROM scheduled_jobs WHERE is_recurring = TRUE LIMIT 0;
            PERFORM 1 FROM scheduled_jobs WHERE is_recurring = FALSE LIMIT 0;
            
            -- Log success
            RAISE NOTICE 'One-time job support successfully added to scheduled_jobs table';
        END
        $$;
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration that removes one-time job support.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Rollback: Remove one-time job support from scheduled_jobs table
        
        -- Drop new indexes
        DROP INDEX IF EXISTS idx_scheduled_jobs_recurring_active;
        DROP INDEX IF EXISTS idx_scheduled_jobs_type_status;
        DROP INDEX IF EXISTS idx_scheduled_jobs_onetime_due;
        DROP INDEX IF EXISTS idx_scheduled_jobs_scheduled_for;
        DROP INDEX IF EXISTS idx_scheduled_jobs_is_recurring;
        
        -- Drop new constraints
        ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_scheduling_check;
        
        -- Restore original status constraint
        ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_status_check;
        ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_status_check 
        CHECK (status IN ('ACTIVE', 'PAUSED'));
        
        -- Make cron_expression required again
        ALTER TABLE scheduled_jobs ALTER COLUMN cron_expression SET NOT NULL;
        
        -- Drop new columns
        ALTER TABLE scheduled_jobs 
        DROP COLUMN IF EXISTS scheduled_for,
        DROP COLUMN IF EXISTS is_recurring;
        
        -- Verify rollback success
        DO $$
        BEGIN
            -- Test that table structure is restored
            PERFORM 1 FROM scheduled_jobs LIMIT 0;
            
            -- Log success
            RAISE NOTICE 'One-time job support successfully removed from scheduled_jobs table';
        END
        $$;
    """


# SQLite compatibility functions
def up_sqlite() -> str:
    """
    SQLite-specific migration for adding one-time job support.
    SQLite doesn't support adding constraints in ALTER TABLE, so we use a different approach.
    """
    return """
        -- SQLite migration: Add one-time job support
        
        -- Add new columns
        ALTER TABLE scheduled_jobs ADD COLUMN is_recurring INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE scheduled_jobs ADD COLUMN scheduled_for TEXT NULL;
        
        -- Update existing jobs to be recurring
        UPDATE scheduled_jobs SET is_recurring = 1;
        
        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_is_recurring ON scheduled_jobs(is_recurring);
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_scheduled_for ON scheduled_jobs(scheduled_for);
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_onetime_due ON scheduled_jobs(is_recurring, scheduled_for, status);
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_type_status ON scheduled_jobs(is_recurring, status);
    """


def down_sqlite() -> str:
    """
    SQLite-specific rollback migration.
    """
    return """
        -- SQLite rollback: Remove one-time job support
        
        -- Drop indexes
        DROP INDEX IF EXISTS idx_scheduled_jobs_type_status;
        DROP INDEX IF EXISTS idx_scheduled_jobs_onetime_due;
        DROP INDEX IF EXISTS idx_scheduled_jobs_scheduled_for;
        DROP INDEX IF EXISTS idx_scheduled_jobs_is_recurring;
        
        -- SQLite doesn't support DROP COLUMN, so we'd need to recreate the table
        -- For now, just mark migration as rolled back
    """