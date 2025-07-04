# Database Migrations

This directory contains database migration scripts for MUXI Runtime.

## Running Migrations

### For Credential Indexes

```bash
# Check existing indexes
python migrations/add_credential_indexes.py check "postgresql://user@localhost/database"

# Run migration to add indexes
python migrations/add_credential_indexes.py migrate "postgresql://user@localhost/database"

# For SQLite
python migrations/add_credential_indexes.py migrate "path/to/database.db"
```

## Migration Scripts

- `add_credential_indexes.py` - Adds performance indexes to the credentials table
  - `idx_credentials_user_service` - Composite index on (user_id, service, formation_id_hash)
  - `idx_credentials_user_formation` - Composite index on (user_id, formation_id_hash)
  - `idx_credentials_service_lower` - Index on lowercase service name for case-insensitive lookups

## Notes

- All migrations support both PostgreSQL and SQLite
- Migrations are idempotent - safe to run multiple times
- Always backup your database before running migrations in production