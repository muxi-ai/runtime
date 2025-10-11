# Database Migrations

This directory contains database migration scripts for MUXI Runtime.

## Quick Setup (Recommended)

Use the init schema instead of running individual migrations:

```bash
# Terminate connections and recreate database
docker exec muxi-e2e-test psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'muxi_test' AND pid <> pg_backend_pid();"
docker exec muxi-e2e-test psql -U postgres -c "DROP DATABASE IF EXISTS muxi_test;"
docker exec muxi-e2e-test psql -U postgres -c "CREATE DATABASE muxi_test OWNER muxi;"

# Create vector extension (requires superuser)
docker exec muxi-e2e-test psql -U postgres muxi_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Load init schema
docker exec -i muxi-e2e-test psql -U muxi muxi_test < migrations/init_schema.sql
```

The `init_schema.sql` file is the **SINGLE SOURCE OF TRUTH** for the database structure.

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