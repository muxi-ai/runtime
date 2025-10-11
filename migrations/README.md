# Database Schema

This directory contains the authoritative database schemas for MUXI Runtime.

## Schema Files (SINGLE SOURCE OF TRUTH)

- **`init_schema.sql`** - PostgreSQL schema with pgvector support
- **`init_schema_sqlite.sql`** - SQLite schema with FTS5 support

## PostgreSQL Setup

```bash
# Terminate connections and recreate database
docker exec muxi-e2e-test psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'muxi_test' AND pid <> pg_backend_pid();"
docker exec muxi-e2e-test psql -U postgres -c "DROP DATABASE IF EXISTS muxi_test;"
docker exec muxi-e2e-test psql -U postgres -c "CREATE DATABASE muxi_test OWNER muxi;"

# Create vector extension (requires superuser)
docker exec muxi-e2e-test psql -U postgres muxi_test -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Load schema
docker exec -i muxi-e2e-test psql -U muxi muxi_test < migrations/init_schema.sql
```

## SQLite Setup

```bash
# Create new database with schema
sqlite3 muxi.db < migrations/init_schema_sqlite.sql

# Or for existing database (will skip existing tables)
sqlite3 existing.db < migrations/init_schema_sqlite.sql
```

## Schema Overview

### Core Tables
- **users** - Multi-user support with formation isolation
- **memories** - Vector embeddings and text content for semantic search
- **credentials** - Encrypted credential storage per user/service
- **scheduled_jobs** - Recurring and one-time job scheduling
- **scheduled_job_audit** - Audit trail for job lifecycle events

### SQLite-Specific Tables
- **collections** - Collection management (SQLite uses explicit table)
- **memories_fts** - FTS5 virtual table for full-text search

### PostgreSQL-Specific Features
- pgvector extension for vector similarity search
- GIN indexes for full-text search
- IVFFlat indexes for fast vector search
- nanoid() function for generating unique IDs

### SQLite-Specific Features
- FTS5 virtual tables for full-text search
- Triggers to sync FTS index with memories table
- BLOB storage for vector embeddings
- JSON stored as TEXT

## Key Differences

| Feature | PostgreSQL | SQLite |
|---------|-----------|--------|
| Auto-increment | SERIAL | INTEGER PRIMARY KEY AUTOINCREMENT |
| JSON | JSONB | TEXT (JSON strings) |
| Boolean | BOOLEAN | INTEGER (0/1) |
| Vectors | vector(1536) | BLOB |
| Full-text | GIN indexes | FTS5 virtual tables |
| ID generation | nanoid() function | Application code |
| Foreign keys | Always enforced | PRAGMA foreign_keys = ON required |

## Notes

- These schemas are the **SINGLE SOURCE OF TRUTH** - no migration history
- Both schemas create identical logical structures with DB-appropriate types
- All tables include proper indexes for performance
- Schemas are idempotent - safe to run multiple times (uses IF NOT EXISTS)
- Always backup your database before schema changes in production