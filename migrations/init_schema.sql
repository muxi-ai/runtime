-- =====================================================================
-- MUXI Framework - Complete Database Schema
-- =====================================================================
-- This is the SINGLE SOURCE OF TRUTH for the database structure
-- Generated: 2025-10-11
-- 
-- To use:
--   psql -U muxi muxi_test < migrations/init_schema.sql
-- =====================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================================
-- FUNCTIONS
-- =====================================================================

-- nanoid() function for generating unique IDs
CREATE OR REPLACE FUNCTION nanoid(size integer DEFAULT 21, alphabet text DEFAULT '_-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'::text)
RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    idBuilder text := '';
    counter int := 0;
    bytes bytea;
    alphabetIndex int;
    alphabetArray text[];
    alphabetLength int;
    mask int;
    step int;
BEGIN
    alphabetArray := regexp_split_to_array(alphabet, '');
    alphabetLength := array_length(alphabetArray, 1);
    mask := (2 << CAST(FLOOR(LOG(alphabetLength - 1) / LOG(2)) AS int)) - 1;
    step := CAST(CEIL(1.6 * mask * size / alphabetLength) AS int);
    
    WHILE true LOOP
        bytes := gen_random_bytes(step);
        WHILE counter < step LOOP
            alphabetIndex := (get_byte(bytes, counter) & mask) + 1;
            IF alphabetIndex <= alphabetLength THEN
                idBuilder := idBuilder || alphabetArray[alphabetIndex];
                IF length(idBuilder) = size THEN
                    RETURN idBuilder;
                END IF;
            END IF;
            counter := counter + 1;
        END LOOP;
        counter := 0;
    END LOOP;
END
$$;

-- =====================================================================
-- TABLES
-- =====================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(21) NOT NULL UNIQUE,
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_formation_id ON users(formation_id);

-- User identifiers table (for multi-identity support)
CREATE TABLE IF NOT EXISTS user_identifiers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(50),
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, formation_id)
);

CREATE INDEX IF NOT EXISTS idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id ON user_identifiers(user_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_formation_id ON user_identifiers(formation_id);

-- Memories table
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(1536),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_collection ON memories(collection);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_user_created_at ON memories(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_text_gin ON memories USING gin(to_tsvector('english', text));

-- Vector similarity index
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories 
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Credentials table
CREATE TABLE IF NOT EXISTS credentials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id CHAR(21) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    service VARCHAR(255) NOT NULL,
    credentials TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_credentials_user_id ON credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_service ON credentials(service);
CREATE UNIQUE INDEX IF NOT EXISTS credentials_credential_id_key ON credentials(credential_id);

-- Scheduled jobs table
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id VARCHAR(255) PRIMARY KEY DEFAULT concat('sched_', nanoid()),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    original_prompt TEXT NOT NULL,
    execution_prompt TEXT NOT NULL,
    is_recurring BOOLEAN NOT NULL DEFAULT true,
    cron_expression VARCHAR(255),
    scheduled_for TIMESTAMP,
    exclusion_rules JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,
    last_run_status VARCHAR(20),
    last_run_failure_message TEXT,
    total_runs INTEGER NOT NULL DEFAULT 0,
    total_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    job_metadata JSONB DEFAULT '{}'::jsonb,
    CHECK (status IN ('ACTIVE', 'PAUSED', 'COMPLETED')),
    CHECK (last_run_status IS NULL OR last_run_status IN ('success', 'failed')),
    CHECK (total_runs >= 0),
    CHECK (total_failures >= 0),
    CHECK (consecutive_failures >= 0)
);

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_user_id ON scheduled_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_status ON scheduled_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_is_recurring ON scheduled_jobs(is_recurring);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_cron_expression ON scheduled_jobs(cron_expression);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_scheduled_for ON scheduled_jobs(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_last_run_at ON scheduled_jobs(last_run_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_active_jobs ON scheduled_jobs(status, cron_expression) 
    WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_recurring_active ON scheduled_jobs(status, cron_expression) 
    WHERE is_recurring = true AND status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_onetime_due ON scheduled_jobs(scheduled_for, status) 
    WHERE is_recurring = false AND status = 'ACTIVE';

-- Scheduled job audit table
CREATE TABLE IF NOT EXISTS scheduled_job_audit (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changes TEXT,
    reason TEXT,
    CHECK (action IN ('created', 'updated', 'paused', 'resumed', 'deleted', 'replaced'))
);

CREATE INDEX IF NOT EXISTS idx_job_audit_job_id ON scheduled_job_audit(job_id);
CREATE INDEX IF NOT EXISTS idx_job_audit_timestamp ON scheduled_job_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_job_audit_user_id ON scheduled_job_audit(user_id);

-- =====================================================================
-- TRIGGERS
-- =====================================================================

CREATE OR REPLACE FUNCTION update_scheduled_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_scheduled_jobs_updated_at
BEFORE UPDATE ON scheduled_jobs
FOR EACH ROW
EXECUTE FUNCTION update_scheduled_jobs_updated_at();

-- =====================================================================
-- COMMENTS
-- =====================================================================

COMMENT ON TABLE scheduled_job_audit IS 'Audit trail for scheduled job lifecycle events. Does not track executions.';
COMMENT ON TABLE memories IS 'Stores vector embeddings and text content for semantic search';
COMMENT ON TABLE users IS 'Multi-user support with formation isolation';
COMMENT ON COLUMN memories.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories.meta_data IS 'Additional metadata stored as JSON';

-- =====================================================================
-- GRANTS
-- =====================================================================

GRANT ALL ON SCHEMA public TO muxi;
GRANT ALL ON ALL TABLES IN SCHEMA public TO muxi;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO muxi;
