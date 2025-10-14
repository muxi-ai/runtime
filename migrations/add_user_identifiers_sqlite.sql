-- =====================================================================
-- Migration: Add user_identifiers table for multi-identity support (SQLite)
-- =====================================================================
-- This migration enables multiple external identifiers (email, Slack ID,
-- Telegram handle, etc.) to map to a single MUXI user.
--
-- Note: SQLite is primarily single-user mode (user_id = "0"), but we
-- maintain the same schema for compatibility and to avoid errors.
--
-- Changes:
-- 1. Create user_identifiers table for many-to-one identifier mapping
-- 2. Migrate existing external_user_id data to user_identifiers
-- 3. Drop external_user_id column from users table (requires table rebuild)
--
-- To apply:
--   sqlite3 muxi.db < migrations/add_user_identifiers_sqlite.sql
-- =====================================================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-- Step 1: Create user_identifiers table
CREATE TABLE IF NOT EXISTS user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    identifier TEXT NOT NULL,
    identifier_type TEXT,  -- Optional: 'email', 'slack', 'telegram', etc.
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(identifier, formation_id)
);

-- Create indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_user_id ON user_identifiers(user_id);
CREATE INDEX IF NOT EXISTS idx_user_identifiers_formation_id ON user_identifiers(formation_id);

-- Step 2: Migrate existing external_user_id values to user_identifiers
-- This preserves all existing user identifiers
INSERT INTO user_identifiers (user_id, identifier, formation_id, created_at)
SELECT id, external_user_id, formation_id, created_at 
FROM users
WHERE external_user_id IS NOT NULL;

-- Step 3: Drop external_user_id column from users table
-- SQLite doesn't support DROP COLUMN directly, so we need to rebuild the table

-- 3a. Create new users table without external_user_id
CREATE TABLE users_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    formation_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3b. Copy data from old table to new table
INSERT INTO users_new (id, public_id, formation_id, created_at, updated_at)
SELECT id, public_id, formation_id, created_at, updated_at
FROM users;

-- 3c. Drop old table
DROP TABLE users;

-- 3d. Rename new table to users
ALTER TABLE users_new RENAME TO users;

-- 3e. Recreate indexes on users table
CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_formation_id ON users(formation_id);

COMMIT;

-- Verification queries (run after migration):
-- SELECT COUNT(*) FROM user_identifiers;  -- Should match original user count
-- SELECT u.id, u.public_id, ui.identifier, ui.identifier_type 
-- FROM users u JOIN user_identifiers ui ON u.id = ui.user_id 
-- LIMIT 10;  -- Verify data migration
