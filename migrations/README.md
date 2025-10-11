# Database Migrations

This directory contains database migration scripts for MUXI Runtime.

## Quick Setup for E2E Tests (Recommended)

Use the complete schema dump instead of running migrations:

```bash
# Drop and recreate test database
docker exec muxi-e2e-test psql -U muxi -c "DROP DATABASE IF EXISTS muxi_test;"
docker exec muxi-e2e-test psql -U muxi -c "CREATE DATABASE muxi_test;"

# Load complete schema (much faster than migrations)
docker exec -i muxi-e2e-test psql -U muxi muxi_test < migrations/schema.sql
```

This ensures consistent schema and is **much faster** than running all migrations.

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