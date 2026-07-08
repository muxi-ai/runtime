-- =====================================================================
-- MUXI Framework - Complete SQLite Database Schema
-- =====================================================================
-- This is the SINGLE SOURCE OF TRUTH for SQLite database structure
-- Generated: 2025-10-11
-- 
-- To use:
--   sqlite3 muxi.db < migrations/init_schema_sqlite.sql
-- =====================================================================

-- Enable foreign keys (SQLite requires this per connection)
PRAGMA foreign_keys = ON;

-- =====================================================================
-- TABLES
-- =====================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_formation_id ON users(formation_id);

-- User identifiers table (for multi-identity support)
CREATE TABLE IF NOT EXISTS user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    identifier TEXT NOT NULL,
    identifier_type TEXT,
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(identifier, formation_id)
);

CREATE INDEX IF NOT EXISTS idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id ON user_identifiers(user_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_formation_id ON user_identifiers(formation_id);

-- Collections table (SQLite uses this for collection management)
CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(name, user_id)
);

CREATE INDEX IF NOT EXISTS idx_collections_user_id ON collections(user_id);
CREATE INDEX IF NOT EXISTS idx_collections_name ON collections(name);

-- =====================================================================
-- Memories tables - one per common embedding dimension
-- =====================================================================
-- SQLite has no native vector type, so embeddings are stored as BLOB
-- (packed float32 bytes). Each dim has its own table plus FTS5
-- virtual table + sync triggers so full-text search works uniformly.
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
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_384_user_id ON memories_384(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_384_collection ON memories_384(collection);
CREATE INDEX IF NOT EXISTS idx_memories_384_created_at ON memories_384(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_384_updated_at ON memories_384(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_384_user_created_at ON memories_384(user_id, created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_384_fts USING fts5(
    text,
    content='memories_384',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_384_fts_insert AFTER INSERT ON memories_384 BEGIN
    INSERT INTO memories_384_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_384_fts_delete AFTER DELETE ON memories_384 BEGIN
    DELETE FROM memories_384_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_384_fts_update AFTER UPDATE ON memories_384 BEGIN
    DELETE FROM memories_384_fts WHERE rowid = old.rowid;
    INSERT INTO memories_384_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- memories_768 -------------------------------------------------------
-- DEFAULT dim: Nomic v1.5, Nomic v2 MoE, all-mpnet, GTE.
CREATE TABLE IF NOT EXISTS memories_768 (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_768_user_id ON memories_768(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_768_collection ON memories_768(collection);
CREATE INDEX IF NOT EXISTS idx_memories_768_created_at ON memories_768(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_768_updated_at ON memories_768(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_768_user_created_at ON memories_768(user_id, created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_768_fts USING fts5(
    text,
    content='memories_768',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_768_fts_insert AFTER INSERT ON memories_768 BEGIN
    INSERT INTO memories_768_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_768_fts_delete AFTER DELETE ON memories_768 BEGIN
    DELETE FROM memories_768_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_768_fts_update AFTER UPDATE ON memories_768 BEGIN
    DELETE FROM memories_768_fts WHERE rowid = old.rowid;
    INSERT INTO memories_768_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- memories_1024 ------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories_1024 (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_1024_user_id ON memories_1024(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_1024_collection ON memories_1024(collection);
CREATE INDEX IF NOT EXISTS idx_memories_1024_created_at ON memories_1024(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1024_updated_at ON memories_1024(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_1024_user_created_at ON memories_1024(user_id, created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_1024_fts USING fts5(
    text,
    content='memories_1024',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_1024_fts_insert AFTER INSERT ON memories_1024 BEGIN
    INSERT INTO memories_1024_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_1024_fts_delete AFTER DELETE ON memories_1024 BEGIN
    DELETE FROM memories_1024_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_1024_fts_update AFTER UPDATE ON memories_1024 BEGIN
    DELETE FROM memories_1024_fts WHERE rowid = old.rowid;
    INSERT INTO memories_1024_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- memories_1536 ------------------------------------------------------
-- OpenAI ada-002, text-embedding-3-small.
CREATE TABLE IF NOT EXISTS memories_1536 (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_1536_user_id ON memories_1536(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_1536_collection ON memories_1536(collection);
CREATE INDEX IF NOT EXISTS idx_memories_1536_created_at ON memories_1536(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_1536_updated_at ON memories_1536(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_1536_user_created_at ON memories_1536(user_id, created_at);

-- SQLite FTS5 for full-text search (equivalent to PostgreSQL GIN index)
CREATE VIRTUAL TABLE IF NOT EXISTS memories_1536_fts USING fts5(
    text,
    content='memories_1536',
    content_rowid='rowid'
);

-- Trigger to keep FTS index in sync with memories table
CREATE TRIGGER IF NOT EXISTS memories_1536_fts_insert AFTER INSERT ON memories_1536 BEGIN
    INSERT INTO memories_1536_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_1536_fts_delete AFTER DELETE ON memories_1536 BEGIN
    DELETE FROM memories_1536_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_1536_fts_update AFTER UPDATE ON memories_1536 BEGIN
    DELETE FROM memories_1536_fts WHERE rowid = old.rowid;
    INSERT INTO memories_1536_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- memories_3072 ------------------------------------------------------
-- OpenAI text-embedding-3-large.
CREATE TABLE IF NOT EXISTS memories_3072 (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection TEXT NOT NULL DEFAULT 'default',
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memories_3072_user_id ON memories_3072(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_3072_collection ON memories_3072(collection);
CREATE INDEX IF NOT EXISTS idx_memories_3072_created_at ON memories_3072(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_3072_updated_at ON memories_3072(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_3072_user_created_at ON memories_3072(user_id, created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_3072_fts USING fts5(
    text,
    content='memories_3072',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_3072_fts_insert AFTER INSERT ON memories_3072 BEGIN
    INSERT INTO memories_3072_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_3072_fts_delete AFTER DELETE ON memories_3072 BEGIN
    DELETE FROM memories_3072_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_3072_fts_update AFTER UPDATE ON memories_3072 BEGIN
    DELETE FROM memories_3072_fts WHERE rowid = old.rowid;
    INSERT INTO memories_3072_fts(rowid, text) VALUES (new.rowid, new.text);
END;

-- Credentials table
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    credential_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    service TEXT NOT NULL,
    credentials TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_credentials_user_id ON credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_service ON credentials(service);
CREATE UNIQUE INDEX IF NOT EXISTS credentials_credential_id_key ON credentials(credential_id);

-- Scheduled jobs table
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    original_prompt TEXT NOT NULL,
    execution_prompt TEXT NOT NULL,
    is_recurring INTEGER NOT NULL DEFAULT 1,
    cron_expression TEXT,
    scheduled_for TIMESTAMP,
    exclusion_rules TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,
    last_run_status TEXT,
    last_run_failure_message TEXT,
    total_runs INTEGER NOT NULL DEFAULT 0,
    total_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    job_metadata TEXT DEFAULT '{}',
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
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
    WHERE is_recurring = 1 AND status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_onetime_due ON scheduled_jobs(scheduled_for, status) 
    WHERE is_recurring = 0 AND status = 'ACTIVE';

-- Scheduled job audit table
CREATE TABLE IF NOT EXISTS scheduled_job_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changes TEXT,
    reason TEXT,
    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
    CHECK (action IN ('created', 'updated', 'paused', 'resumed', 'deleted', 'replaced'))
);

CREATE INDEX IF NOT EXISTS idx_job_audit_job_id ON scheduled_job_audit(job_id);
CREATE INDEX IF NOT EXISTS idx_job_audit_timestamp ON scheduled_job_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_job_audit_user_id ON scheduled_job_audit(user_id);

-- User channel state table (Proactiveness Phase 1)
CREATE TABLE IF NOT EXISTS user_channel_state (
    user_id TEXT NOT NULL,
    formation_id TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, formation_id)
);

-- =====================================================================
-- TRIGGERS FOR UPDATED_AT
-- =====================================================================

CREATE TRIGGER IF NOT EXISTS trigger_update_scheduled_jobs_updated_at
AFTER UPDATE ON scheduled_jobs
FOR EACH ROW
BEGIN
    UPDATE scheduled_jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
    UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_collections_updated_at
AFTER UPDATE ON collections
FOR EACH ROW
BEGIN
    UPDATE collections SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_384_updated_at
AFTER UPDATE ON memories_384
FOR EACH ROW
BEGIN
    UPDATE memories_384 SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_768_updated_at
AFTER UPDATE ON memories_768
FOR EACH ROW
BEGIN
    UPDATE memories_768 SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_1024_updated_at
AFTER UPDATE ON memories_1024
FOR EACH ROW
BEGIN
    UPDATE memories_1024 SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_1536_updated_at
AFTER UPDATE ON memories_1536
FOR EACH ROW
BEGIN
    UPDATE memories_1536 SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_3072_updated_at
AFTER UPDATE ON memories_3072
FOR EACH ROW
BEGIN
    UPDATE memories_3072 SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_credentials_updated_at
AFTER UPDATE ON credentials
FOR EACH ROW
BEGIN
    UPDATE credentials SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_user_channel_state_updated_at
AFTER UPDATE ON user_channel_state
FOR EACH ROW
BEGIN
    UPDATE user_channel_state SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id AND formation_id = NEW.formation_id;
END;

-- =====================================================================
-- NOTES
-- =====================================================================
-- SQLite differences from PostgreSQL:
-- 1. No SERIAL type - use INTEGER PRIMARY KEY AUTOINCREMENT
-- 2. No JSONB type - use TEXT to store JSON strings
-- 3. No vector extension - embedding stored as BLOB
-- 4. BOOLEAN stored as INTEGER (0 = false, 1 = true)
-- 5. FTS5 virtual table for full-text search instead of GIN indexes
-- 6. No native nanoid() function - IDs generated in application code
-- 7. Triggers for updated_at must use UPDATE statement, not NEW.field assignment
-- 8. Foreign keys must be enabled per connection with PRAGMA foreign_keys = ON
