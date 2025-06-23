#!/usr/bin/env python3
"""
@migration: scheduler_audit_trail
@generated: 2025-06-23 02:00:00
@description: Simple job lifecycle audit trail for scheduler
"""


def up() -> str:
    """
    Create a simple audit trail table for tracking job lifecycle events.

    This table tracks when jobs are:
    - Created
    - Updated
    - Paused
    - Resumed
    - Deleted
    - Replaced (when prompt fundamentally changes)

    Returns:
        SQL string to be executed for the up migration
    """
    return """
        -- Create audit trail table for job lifecycle events
        CREATE TABLE scheduled_job_audit (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(255) NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            action VARCHAR(50) NOT NULL,
            timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            changes TEXT,  -- JSON string of what changed
            reason TEXT,   -- Optional reason for the action

            -- Validate action values
            CONSTRAINT chk_audit_action CHECK (
                action IN ('created', 'updated', 'paused', 'resumed', 'deleted', 'replaced')
            )
        );

        -- Indexes for efficient querying
        CREATE INDEX idx_job_audit_job_id ON scheduled_job_audit(job_id);
        CREATE INDEX idx_job_audit_user_id ON scheduled_job_audit(user_id);
        CREATE INDEX idx_job_audit_timestamp ON scheduled_job_audit(timestamp DESC);

        -- Add comment explaining the table
        COMMENT ON TABLE scheduled_job_audit IS
            'Audit trail for scheduled job lifecycle events. Does not track executions.';
    """


def down() -> str:
    """
    Remove the audit trail table.

    Returns:
        SQL string to be executed for the down migration
    """
    return """
        -- Drop the audit trail table
        DROP TABLE IF EXISTS scheduled_job_audit;
    """
