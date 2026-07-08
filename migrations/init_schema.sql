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

-- =====================================================================
-- Memories tables - one per common embedding dimension
-- =====================================================================
-- The runtime writes to the table matching the configured embedding
-- model's dimension. Tables for all common dims are pre-created so
-- first-write latency is predictable and no DDL is needed on the hot
-- path. Exotic dims fall back to runtime CREATE TABLE via
-- services/memory/sqlite.py::_create_memories_table and the PostgreSQL
-- equivalents, which remain idempotent via IF NOT EXISTS.
--
-- Dimension -> typical producer:
--   384  - legacy MiniLM (read-only support for re-embed migration)
--   768  - Nomic v1.5 (DEFAULT), Nomic v2 MoE, all-mpnet, GTE
--   1024 - Arctic Embed L v2.0, bge-m3, Cohere v3
--   1536 - OpenAI ada-002, text-embedding-3-small
--   3072 - OpenAI text-embedding-3-large
-- =====================================================================

-- memories_384 -------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories_384 (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(384),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_384_user_id ON memories_384(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_384_collection ON memories_384(collection);
CREATE INDEX IF NOT EXISTS idx_memories_384_created_at ON memories_384(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_384_updated_at ON memories_384(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_384_user_created_at ON memories_384(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_384_text_gin ON memories_384 USING gin(to_tsvector('english', text));
-- ivfflat uses vector_l2_ops to match the runtime's l2_distance() search path
-- (LongTermMemory.search / search_by_embedding). pgvector will not use a
-- cosine-ops index for an L2 query, so mismatching here silently forces a
-- sequential scan and regresses search latency at scale.
CREATE INDEX IF NOT EXISTS memories_384_embedding_idx ON memories_384
USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- memories_768 -------------------------------------------------------
-- DEFAULT dim: Nomic v1.5, Nomic v2 MoE, all-mpnet, GTE.
CREATE TABLE IF NOT EXISTS memories_768 (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(768),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_768_user_id ON memories_768(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_768_collection ON memories_768(collection);
CREATE INDEX IF NOT EXISTS idx_memories_768_created_at ON memories_768(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_768_updated_at ON memories_768(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_768_user_created_at ON memories_768(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_768_text_gin ON memories_768 USING gin(to_tsvector('english', text));
-- See memories_384: runtime uses l2_distance, so the ANN index must be vector_l2_ops.
CREATE INDEX IF NOT EXISTS memories_768_embedding_idx ON memories_768
USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- memories_1024 ------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories_1024 (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(1024),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_1024_user_id ON memories_1024(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_1024_collection ON memories_1024(collection);
CREATE INDEX IF NOT EXISTS idx_memories_1024_created_at ON memories_1024(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1024_updated_at ON memories_1024(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_1024_user_created_at ON memories_1024(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1024_text_gin ON memories_1024 USING gin(to_tsvector('english', text));
-- See memories_384: runtime uses l2_distance, so the ANN index must be vector_l2_ops.
CREATE INDEX IF NOT EXISTS memories_1024_embedding_idx ON memories_1024
USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- memories_1536 ------------------------------------------------------
-- OpenAI ada-002, text-embedding-3-small.
CREATE TABLE IF NOT EXISTS memories_1536 (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(1536),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_1536_user_id ON memories_1536(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_1536_collection ON memories_1536(collection);
CREATE INDEX IF NOT EXISTS idx_memories_1536_created_at ON memories_1536(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1536_updated_at ON memories_1536(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_1536_user_created_at ON memories_1536(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1536_text_gin ON memories_1536 USING gin(to_tsvector('english', text));

-- Vector similarity index -- vector_l2_ops to match runtime l2_distance().
--
-- UPGRADE PATH: Pre-migration databases created this index with
-- `vector_cosine_ops`, but the runtime now uses `l2_distance()`
-- (see `services/memory/long_term.py`). pgvector will NOT use a
-- cosine-ops index for an L2 query and silently falls back to a
-- sequential scan at search time -- a hard perf regression on any
-- non-trivial `memories_1536` table.
--
-- `CREATE INDEX IF NOT EXISTS` alone cannot fix this: if the index
-- name already exists (with the wrong ops class), the statement is
-- a no-op. We therefore DROP the index first so the CREATE always
-- lands the correct l2-ops variant. For fresh installs the DROP is
-- a no-op; for existing installs it rebuilds once and then stays
-- correct on every subsequent re-apply.
--
-- This drop+create is scoped to `memories_1536` only because it is
-- the single dimension table that existed in older schemas with the
-- wrong ops class. The other dimension tables (384 / 768 / 1024 /
-- 3072) were introduced in the embedding-platform migration and
-- have no pre-existing installations to upgrade, so they keep the
-- cheaper `CREATE INDEX IF NOT EXISTS` form.
DROP INDEX IF EXISTS memories_1536_embedding_idx;
CREATE INDEX memories_1536_embedding_idx ON memories_1536
USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- memories_3072 ------------------------------------------------------
-- OpenAI text-embedding-3-large.
CREATE TABLE IF NOT EXISTS memories_3072 (
    id VARCHAR(21) PRIMARY KEY DEFAULT nanoid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    embedding vector(3072),
    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    collection VARCHAR(255) NOT NULL DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memories_3072_user_id ON memories_3072(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_3072_collection ON memories_3072(collection);
CREATE INDEX IF NOT EXISTS idx_memories_3072_created_at ON memories_3072(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_3072_updated_at ON memories_3072(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_3072_user_created_at ON memories_3072(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_3072_text_gin ON memories_3072 USING gin(to_tsvector('english', text));
-- See memories_384: runtime uses l2_distance, so the ANN index must be vector_l2_ops.
CREATE INDEX IF NOT EXISTS memories_3072_embedding_idx ON memories_3072
USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

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

-- User channel state table (Proactiveness Phase 1)
CREATE TABLE IF NOT EXISTS user_channel_state (
    user_id VARCHAR(255) NOT NULL,
    formation_id VARCHAR(255) NOT NULL,
    state TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, formation_id)
);

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
COMMENT ON TABLE memories_384 IS 'Stores vector embeddings and text content for semantic search (384-dim legacy MiniLM)';
COMMENT ON TABLE memories_768 IS 'Stores vector embeddings and text content for semantic search (768-dim: Nomic v1.5 default, Nomic v2 MoE)';
COMMENT ON TABLE memories_1024 IS 'Stores vector embeddings and text content for semantic search (1024-dim: Arctic, bge-m3, Cohere v3)';
COMMENT ON TABLE memories_1536 IS 'Stores vector embeddings and text content for semantic search (1536-dim: OpenAI ada-002, text-embedding-3-small)';
COMMENT ON TABLE memories_3072 IS 'Stores vector embeddings and text content for semantic search (3072-dim: OpenAI text-embedding-3-large)';
COMMENT ON TABLE users IS 'Multi-user support with formation isolation';

-- Column comments are identical across all memories_* tables (schema is
-- a straight copy parameterized on dimension). Documenting each one so
-- psql \d, information_schema, and pgAdmin surface the same guidance no
-- matter which dim is active.
COMMENT ON COLUMN memories_384.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories_384.meta_data IS 'Additional metadata stored as JSON';
COMMENT ON COLUMN memories_768.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories_768.meta_data IS 'Additional metadata stored as JSON';
COMMENT ON COLUMN memories_1024.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories_1024.meta_data IS 'Additional metadata stored as JSON';
COMMENT ON COLUMN memories_1536.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories_1536.meta_data IS 'Additional metadata stored as JSON';
COMMENT ON COLUMN memories_3072.collection IS 'Collection name for organizing memories (e.g., preferences, user_identity, activities)';
COMMENT ON COLUMN memories_3072.meta_data IS 'Additional metadata stored as JSON';

-- =====================================================================
-- GRANTS
-- =====================================================================

GRANT ALL ON SCHEMA public TO muxi;
GRANT ALL ON ALL TABLES IN SCHEMA public TO muxi;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO muxi;
