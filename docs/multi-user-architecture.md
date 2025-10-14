# Multi-User Architecture in MUXI Runtime

## Overview

MUXI Runtime implements a sophisticated multi-identity architecture that provides complete data isolation between users while maintaining a consistent interface across both single-user (SQLite) and multi-user (PostgreSQL) deployments.

**📚 For detailed documentation, see [Multi-Identity Feature Guide](features/multi-identity.md)**

This document provides a high-level architectural overview. For implementation details, API usage, and examples, refer to the comprehensive guide above.

## User ID Management Flow

### 1. External vs Internal User IDs

When calling `overlord.chat()` or any user-specific operation:

```python
# Developer provides their external user ID
response = await overlord.chat("Hello", user_id="alice-123")
```

The system follows this flow:

1. **Receive External ID**: The `user_id` parameter is the developer's external identifier
2. **Hash for Lookup**: Calculate hash of external_user_id for efficient lookup
3. **Find/Create User**:
   - Query: `SELECT id FROM users WHERE external_user_id_hash = ?`
   - If not found, create new user record
4. **Use Internal ID**: All subsequent operations use the internal `users.id`

### 2. Database Schema

The `users` table structure is **identical** for both SQLite and PostgreSQL:

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,           -- Internal ID used as FK in all other tables
    external_user_id TEXT NOT NULL,   -- Developer's provided ID
    external_user_id_hash TEXT NOT NULL, -- Hash for fast lookups
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP
);

CREATE INDEX idx_users_external_hash ON users(external_user_id_hash);
```

### 3. Single-User Mode (SQLite)

For SQLite deployments, we maintain the same structure but with a single default user:

```sql
-- On initialization, create default user
INSERT INTO users (id, external_user_id, external_user_id_hash, created_at)
VALUES (1, '0', hash('0'), CURRENT_TIMESTAMP);
```

- All operations use `user_id='0'` by default
- Same queries and code paths as PostgreSQL
- No branching logic needed

### 4. Multi-User Mode (PostgreSQL)

Example flow with multiple users:

```
Developer A: overlord.chat("Hello", user_id="alice-123")
Developer B: overlord.chat("Hi", user_id="bob-456")

Users table:
| id | external_user_id | external_user_id_hash |
|----|------------------|----------------------|
| 1  | alice-123        | a3f5b8...           |
| 2  | bob-456          | 7d9e2c...           |

Memories table:
| id | user_id | content |
|----|---------|---------|
| 1  | 1       | Hello   |  <- Alice's memory
| 2  | 2       | Hi      |  <- Bob's memory
```

## Implementation Requirements

### All Tables Must Use Internal User ID

Every table that needs user isolation must:
- Have a `user_id` column that references `users.id`
- **Never** store the external_user_id directly
- Always join through the users table when needed

Example tables:
- `memories` - user_id FK
- `conversations` - user_id FK
- `collections` - user_id FK
- `knowledge_items` - user_id FK

### Query Patterns

```python
# Bad - Don't do this
db.query("SELECT * FROM memories WHERE user_id = ?", external_user_id)

# Good - Always resolve to internal ID first
user = get_or_create_user(external_user_id)
db.query("SELECT * FROM memories WHERE user_id = ?", user.id)
```

## Benefits

1. **Performance**: Integer FKs are faster than string lookups
2. **Consistency**: Same code works for both SQLite and PostgreSQL
3. **Security**: Internal IDs don't leak external system information
4. **Flexibility**: Can change external ID mapping without affecting data
5. **Simplicity**: No database-specific branching in application code

## Migration Path

This architecture makes it easy to migrate from SQLite to PostgreSQL:
1. Export SQLite data
2. Import to PostgreSQL
3. Update connection string
4. System continues working with full multi-user support

## Implementation Overview

The multi-identity system provides:

- **Multi-Identity Support**: One user can have multiple identifiers (email, Slack, GitHub, etc.)
- **Database Schema**: `users` and `user_identifiers` tables with proper foreign keys
- **User Resolution**: Fast KV-cached identifier-to-user resolution
- **Formation Isolation**: Each formation maintains separate user namespaces
- **Backward Compatible**: Single-user mode (SQLite) uses identifier "0"
- **Database Agnostic**: Works with both SQLite and PostgreSQL
- **Input Validation**: Fail-fast validation for identifiers and formation_id
- **Transaction Safety**: Successful creates preserved on partial failures
- **Observability**: Full event tracking for monitoring

### Database Schema

```sql
-- Core user entity
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id VARCHAR(255) NOT NULL,         -- usr_xxxx
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    UNIQUE(public_id, formation_id)
);

-- External identifier mapping (one-to-many)
CREATE TABLE user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                -- FK to users.id
    identifier VARCHAR(255) NOT NULL,        -- alice@email.com, U123, etc.
    identifier_type VARCHAR(50),             -- email, slack, github, etc.
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    UNIQUE(identifier, formation_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX idx_user_identifiers_user ON user_identifiers(user_id);
```

### Key Design Decisions

1. **Indexed Identifiers**: Direct indexed lookups are faster than hash-based lookups
2. **Separate Identifiers Table**: Supports multiple identifiers per user (one-to-many)
3. **Dual IDs**: Internal integer ID for performance, public string ID (usr_xxxx) for API
4. **Type Hints**: Optional `identifier_type` field for better observability
5. **Clean Schema**: No redundant external_user_id column in users table

### Service Integration

Core services use user resolution:

- **Long-Term Memory**: `_resolve_user_id_async()` and `_resolve_user_id_sync()` methods
- **Credential Resolver**: `_resolve_user_id()` with db_manager integration
- **Scheduler**: User resolution for job associations and audit trails
- **Chat Orchestrator**: User resolution for context and synopsis

### Migration Guide

See [Multi-Identity Feature Guide](features/multi-identity.md#migration-guide) for:
- Migrating from legacy single-user
- Mapping old user IDs to new identifiers
- Zero-downtime migration strategies
