-- =====================================================================
-- Migration: Add user_identifiers table for multi-identity support
-- =====================================================================
-- This migration enables multiple external identifiers (email, Slack ID,
-- Telegram handle, etc.) to map to a single MUXI user.
--
-- Changes:
-- 1. Create user_identifiers table for many-to-one identifier mapping
-- 2. Migrate existing external_user_id data to user_identifiers
-- 3. Drop external_user_id column from users table
--
-- To apply:
--   psql -U muxi -d muxi_test < migrations/add_user_identifiers.sql
-- =====================================================================

BEGIN;

-- Step 1: Create user_identifiers table
CREATE TABLE IF NOT EXISTS user_identifiers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(50),  -- Optional: 'email', 'slack', 'telegram', etc.
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

-- Step 3: Drop external_user_id column and related constraints/indexes
-- First drop the unique constraint
ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_user_formation_external_id;

-- Drop the index
DROP INDEX IF EXISTS idx_users_external_user_id;

-- Finally drop the column
ALTER TABLE users DROP COLUMN IF EXISTS external_user_id;

COMMIT;

-- Verification queries (run after migration):
-- SELECT COUNT(*) FROM user_identifiers;  -- Should match original user count
-- SELECT u.id, u.public_id, ui.identifier, ui.identifier_type 
-- FROM users u JOIN user_identifiers ui ON u.id = ui.user_id 
-- LIMIT 10;  -- Verify data migration
