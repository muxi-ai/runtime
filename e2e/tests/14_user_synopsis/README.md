# Test Group 14: User Synopsis

This test group validates the user synopsis feature - a two-tier LLM-synthesized user context caching system.

## Overview

User synopsis automatically generates cached summaries of user context (identity, preferences, activities) for injection into enhanced messages.

## Test Files

- `test_14a1_synopsis_enabled.py` - Tests synopsis when enabled (default behavior)
  - Synopsis generation and caching
  - Cache invalidation on context changes
  - Empty state handling
  - Multi-user isolation

## Formations

- `formations/formation-synopsis/` - Default formation with synopsis enabled

## Configuration

The synopsis system is configured in `formation.afs`:

```yaml
memory:
  persistent:
    user_synopsis:
      enabled: true      # Enable/disable synopsis (default: true)
      cache_ttl: 3600    # Cache TTL in seconds (default: 3600 = 1 hour)
```

## Features Tested

1. **Synopsis Generation**: Verifies synopsis appears in enhanced messages
2. **Caching**: Confirms proper cache hits and reuse
3. **Invalidation**: Tests cache invalidation on context updates
4. **Configuration**: Validates `enabled` and `cache_ttl` settings
5. **Empty State**: Ensures clean behavior when no user data exists
6. **Multi-User**: Tests isolation between different users

## Dependencies

- PostgreSQL database (for persistent memory)
- Multi-user mode enabled
- Extraction model configured (for LLM synthesis)

## Running Tests

```bash
# Run all user synopsis tests
bash .claude/scripts/test-and-log.sh e2e/tests/14_user_synopsis/

# Run specific test
bash .claude/scripts/test-and-log.sh e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py
```

## Documentation

See [docs/user-synopsis.md](../../../docs/user-synopsis.md) for complete feature documentation.
