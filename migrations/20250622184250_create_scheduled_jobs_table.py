#!/usr/bin/env python3
"""
@migration: create_scheduled_jobs_table
@generated: 2025-06-22 18:42:50
@description: Creates the scheduled_jobs table for the MUXI scheduler feature
"""


def up() -> str:
    """
    Returns the SQL for the forward migration that creates the scheduled_jobs table.

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Migration: Create scheduled_jobs table for MUXI scheduler
        -- This migration creates the table for storing scheduled task information
        -- using map/reduce pattern with dynamic exclusion rules

        -- Enable required extensions
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        -- Create the scheduled_jobs table
        CREATE TABLE scheduled_jobs (
          id VARCHAR(255) PRIMARY KEY DEFAULT CONCAT('sched_', nanoid()),
          user_id VARCHAR(255) NOT NULL,
          formation_id VARCHAR(255) NOT NULL,
          title VARCHAR(500) NOT NULL,
          original_prompt TEXT NOT NULL,
          execution_prompt TEXT NOT NULL,
          cron_expression VARCHAR(255) NOT NULL,
          exclusion_rules JSONB DEFAULT '[]',
          status VARCHAR(20) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PAUSED')),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          -- Execution tracking (simplified for map/reduce pattern)
          last_run_at TIMESTAMP WITH TIME ZONE NULL,
          last_run_status VARCHAR(20) NULL CHECK (last_run_status IS NULL OR last_run_status IN ('success', 'failed')),
          last_run_failure_message TEXT NULL,
          total_runs INTEGER DEFAULT 0 CHECK (total_runs >= 0),
          total_failures INTEGER DEFAULT 0 CHECK (total_failures >= 0),
          consecutive_failures INTEGER DEFAULT 0 CHECK (consecutive_failures >= 0),
          metadata JSONB DEFAULT '{}'
        );

        -- Create indexes for performance optimization
        CREATE INDEX idx_scheduled_jobs_user_id ON scheduled_jobs(user_id);
        CREATE INDEX idx_scheduled_jobs_status ON scheduled_jobs(status);
        CREATE INDEX idx_scheduled_jobs_formation_id ON scheduled_jobs(formation_id);
        CREATE INDEX idx_scheduled_jobs_cron_expression ON scheduled_jobs(cron_expression);
        CREATE INDEX idx_scheduled_jobs_last_run_at ON scheduled_jobs(last_run_at);

        -- Composite indexes for common query patterns
        CREATE INDEX idx_scheduled_jobs_user_status ON scheduled_jobs(user_id, status);
        CREATE INDEX idx_scheduled_jobs_active_jobs ON scheduled_jobs(status, cron_expression) WHERE status = 'ACTIVE';

        -- Add trigger for automatic updated_at timestamp
        CREATE OR REPLACE FUNCTION update_scheduled_jobs_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trigger_update_scheduled_jobs_updated_at
            BEFORE UPDATE ON scheduled_jobs
            FOR EACH ROW
            EXECUTE FUNCTION update_scheduled_jobs_updated_at();

        -- Verify table creation
        DO $$
        BEGIN
            -- Test that we can reference the table
            PERFORM 1 FROM scheduled_jobs LIMIT 0;

            -- Log success
            RAISE NOTICE 'scheduled_jobs table successfully created with all indexes and constraints';
        END
        $$;
    """


def down() -> str:
    """
    Returns the SQL for the rollback migration that drops the scheduled_jobs table.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Drop the scheduled_jobs table and all related objects
        DROP TRIGGER IF EXISTS trigger_update_scheduled_jobs_updated_at ON scheduled_jobs;
        DROP FUNCTION IF EXISTS update_scheduled_jobs_updated_at();

        -- Drop indexes (will be dropped automatically with table, but being explicit)
        DROP INDEX IF EXISTS idx_scheduled_jobs_active_jobs;
        DROP INDEX IF EXISTS idx_scheduled_jobs_user_status;
        DROP INDEX IF EXISTS idx_scheduled_jobs_last_run_at;
        DROP INDEX IF EXISTS idx_scheduled_jobs_cron_expression;
        DROP INDEX IF EXISTS idx_scheduled_jobs_formation_id;
        DROP INDEX IF EXISTS idx_scheduled_jobs_status;
        DROP INDEX IF EXISTS idx_scheduled_jobs_user_id;

        -- Drop the table
        DROP TABLE IF EXISTS scheduled_jobs CASCADE;
    """
