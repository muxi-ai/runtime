# Formation API E2E Tests

This directory contains end-to-end tests for the Formation API endpoints.

## Test Coverage

### 19a: Audit Logging (`test_19a1_audit_logging.py`)
- Test audit log retrieval (GET /v1/audit)
- Test audit log filtering (action, resource_type, since)
- Test audit log clearing (DELETE /v1/audit)
- Test confirmation requirement
- Test JSONL format and human-readable messages

### 19b: SOP Endpoints (`test_19b1_sop_endpoints.py`)
- Test SOP listing (GET /v1/sops)
- Test SOP details retrieval (GET /v1/sops/{sop_name})
- Test with no SOPs configured
- Test 404 for non-existent SOPs
- Test read-only access

### 19c: Scheduler Persistence (`test_19c1_scheduler_persistence.py`)
- Test 422 response for SQLite/no persistent memory
- Test error message format
- Test error.data field structure
- Test with PostgreSQL (should succeed)

## Running Tests

```bash
# Run all API tests
bash .claude/scripts/test-and-log.sh e2e/tests/19_api/

# Run specific test
bash .claude/scripts/test-and-log.sh e2e/tests/19_api/test_19a1_audit_logging.py

# Run all tests in category
bash .claude/scripts/test-and-log.sh e2e/tests/19_api/test_19a*.py
```

## Test Formation

All tests use the `formation-api` formation which includes:
- Single assistant agent
- Server enabled with API keys
- Buffer memory only (no persistent memory for some tests)
- OpenAI GPT-4o-mini model

## Authentication

Tests use predefined API keys:
- Admin key: `test-admin-key-123`
- Client key: `test-client-key-456`

## Notes

- Tests verify exact response format per OpenAPI spec
- Tests check object types and event types
- Tests validate error responses and status codes
- Tests use real HTTP requests to verify API server functionality
