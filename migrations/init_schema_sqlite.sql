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

-- Memories table
CREATE TABLE IF NOT EXISTS memories (
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

CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_collection ON memories(collection);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_updated_at ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_user_created_at ON memories(user_id, created_at);

-- SQLite FTS5 for full-text search (equivalent to PostgreSQL GIN index)
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    text,
    content='memories',
    content_rowid='rowid'
);

-- Trigger to keep FTS index in sync with memories table
CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
    DELETE FROM memories_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
    DELETE FROM memories_fts WHERE rowid = old.rowid;
    INSERT INTO memories_fts(rowid, text) VALUES (new.rowid, new.text);
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

CREATE TRIGGER IF NOT EXISTS trigger_update_memories_updated_at
AFTER UPDATE ON memories
FOR EACH ROW
BEGIN
    UPDATE memories SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_update_credentials_updated_at
AFTER UPDATE ON credentials
FOR EACH ROW
BEGIN
    UPDATE credentials SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
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
