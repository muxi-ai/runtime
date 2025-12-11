# Multi-Identity User Management

MUXI Runtime's multi-identity system enables sophisticated user management where a single user can be identified by multiple external identifiers (email, Slack ID, GitHub username, etc.) while maintaining complete data isolation and consistency.

## Overview

The multi-identity system solves a common problem in modern applications: users interact through multiple platforms (chat, email, API), each with its own ID scheme. MUXI automatically links these identities to a single user profile, ensuring consistent memory, preferences, and context across all interactions.

## Features

- **Multiple Identifiers Per User**: Link email, Slack ID, GitHub username, etc. to one user
- **Automatic Resolution**: Fast identifier-to-user resolution with KV caching
- **Formation Isolation**: Each formation maintains its own user namespace
- **Backward Compatible**: Single-user mode still works with identifier "0"
- **Database Agnostic**: Works with both SQLite and PostgreSQL
- **Type Hints**: Optional identifier types (email, slack, github, etc.)

## Architecture

### Database Schema

The system uses two core tables:

#### `users` Table
Stores the core user entity:

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- Internal user ID (FK for all data)
    public_id VARCHAR(255) NOT NULL,       -- External MUXI user ID (usr_xxxx)
    formation_id VARCHAR(255) NOT NULL,    -- Formation isolation
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP,
    UNIQUE(public_id, formation_id)
);
```

#### `user_identifiers` Table
Maps external identifiers to users:

```sql
CREATE TABLE user_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,                 -- FK to users.id
    identifier VARCHAR(255) NOT NULL,         -- External ID (email, Slack ID, etc.)
    identifier_type VARCHAR(50),              -- Optional type hint
    formation_id VARCHAR(255) NOT NULL,       -- Formation isolation
    created_at TIMESTAMP NOT NULL,
    UNIQUE(identifier, formation_id),         -- One identifier per formation
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX idx_user_identifiers_user ON user_identifiers(user_id);
```

### Key Design Principles

1. **Internal vs External IDs**:
   - `users.id` (integer): Internal FK for all user data (fast)
   - `users.public_id` (string): External MUXI ID (usr_xxxx) for API responses
   - `user_identifiers.identifier` (string): Developer-provided external IDs

2. **Formation Isolation**:
   - Each formation maintains separate user namespaces
   - Same email can map to different users in different formations

3. **Many-to-One Mapping**:
   - Multiple identifiers → One user
   - One identifier → One user (per formation)

## User Resolution Flow

### Fast Path (Cache Hit)

```
Developer calls: overlord.chat("Hello", user_id="alice@email.com")
     ↓
Check KV cache: "user_id:formation_abc:alice@email.com"
     ↓
Cache hit: "123:usr_abc123"
     ↓
Return: (internal_id=123, muxi_id="usr_abc123")
```

### Slow Path (Cache Miss - Existing User)

```
Cache miss
     ↓
Query: SELECT u.id, u.public_id
       FROM user_identifiers ui
       JOIN users u ON ui.user_id = u.id
       WHERE ui.identifier = 'alice@email.com'
       AND ui.formation_id = 'formation_abc'
     ↓
Found: (123, "usr_abc123")
     ↓
Cache result for 1 hour
     ↓
Return: (123, "usr_abc123")
```

### Slow Path (Cache Miss - New User)

```
Cache miss → Query → Not found
     ↓
Create new user:
  - Generate public_id: usr_abc123
  - Insert into users table
  - Get auto-increment id: 123
     ↓
Create identifier:
  - Insert into user_identifiers
  - Link to user_id: 123
     ↓
Cache result for 1 hour
     ↓
Return: (123, "usr_abc123")
```

## API Usage

### Basic Usage (Single Identifier)

```python
from muxi.formation import Formation

# Initialize formation
formation = Formation("formation.afs")

# User identified by email
response = await formation.chat(
    message="What's my name?",
    user_id="alice@email.com"
)
```

### Advanced: Multiple Identifiers

Use the `associate_user_identifiers()` function to link multiple identifiers:

```python
from muxi.utils.user_resolution import associate_user_identifiers

# Link email, Slack, and GitHub to one user
result = await associate_user_identifiers(
    identifiers=[
        "alice@email.com",
        {"identifier": "U12345ABC", "type": "slack"},
        ("alice_gh", "github")
    ],
    muxi_user_id=None,  # Create new user
    formation_id="formation_abc",
    db_manager=formation._overlord.db_manager,
    kv_cache=formation._overlord.kv_cache
)

print(f"MUXI User ID: {result['muxi_user_id']}")
print(f"New identifiers: {result['new_identifiers']}")
```

### Resolution Function

For custom integrations, use the resolution function directly:

```python
from muxi.utils.user_resolution import resolve_user_identifier

# Resolve any identifier to user IDs
internal_id, muxi_id = await resolve_user_identifier(
    identifier="alice@email.com",
    formation_id="formation_abc",
    db_manager=db_manager,
    kv_cache=kv_cache
)

# Use internal_id for database queries
memories = await long_term_memory.search(
    query="preferences",
    user_id=internal_id
)
```

### Input Formats

The `associate_user_identifiers()` function accepts flexible input:

```python
identifiers = [
    "simple@email.com",                          # Plain string
    {"identifier": "U123", "type": "slack"},     # Dict with type
    ("alice_tg", "telegram")                     # Tuple (identifier, type)
]
```

## Configuration

### Single-User Mode (Default)

SQLite deployments automatically use identifier "0":

```yaml
# formation.afs (or .yaml)
memory:
  provider: sqlite
  database: "./data/muxi.db"
```

All operations internally use `user_id="0"`, maintaining backward compatibility.

### Multi-User Mode

PostgreSQL deployments enable full multi-identity:

```yaml
# formation.afs (or .yaml)
memory:
  provider: postgres
  host: localhost
  port: 5432
  database: muxi_db
  user: muxi_user
  password: ${POSTGRES_PASSWORD}
```

Each unique identifier creates/resolves to the appropriate user.

## Migration Guide

### From Legacy Single-User

If upgrading from a version without multi-identity support:

1. **Database Migration**: Run automatically on first startup
   ```
   [INFO] Running migration: 004_multi_identity.py
   [INFO] Migration complete
   ```

2. **Code Changes**: None required!
   - SQLite mode: Uses identifier "0" automatically
   - Existing `user_id` parameters work unchanged

3. **New Functionality**: Add multi-user support when ready
   - Switch to PostgreSQL
   - Start using different `user_id` values
   - Optionally link multiple identifiers per user

### Migrating Existing Data

If you have existing user data with custom IDs:

```python
# Map old IDs to new identifiers
old_users = [
    {"old_id": "user123", "email": "alice@email.com"},
    {"old_id": "user456", "email": "bob@email.com"},
]

for user in old_users:
    # Associate old ID with new identifier
    await associate_user_identifiers(
        identifiers=[user["old_id"], user["email"]],
        muxi_user_id=None,  # Create new user
        formation_id=formation_id,
        db_manager=db_manager,
        kv_cache=kv_cache
    )
```

## Performance Optimization

### KV Cache Strategy

- **Cache Key Format**: `user_id:{formation_id}:{identifier}`
- **Cache Value Format**: `{internal_id}:{muxi_id}`
- **TTL**: 1 hour (3600 seconds)
- **Invalidation**: Automatic on identifier association

### Query Optimization

All user-related queries use indexed lookups:

```python
# Fast: Uses idx_user_identifiers_lookup
SELECT u.id FROM user_identifiers ui
JOIN users u ON ui.user_id = u.id
WHERE ui.identifier = ? AND ui.formation_id = ?

# Fast: Uses idx_user_identifiers_user
SELECT identifier FROM user_identifiers
WHERE user_id = ?
```

### Best Practices

1. **Use KV Cache**: Always provide `kv_cache` to resolution functions
2. **Batch Operations**: Use `associate_user_identifiers()` to link multiple IDs at once
3. **Identifier Types**: Provide type hints for better observability
4. **Formation Isolation**: Don't share user data across formations

## Common Patterns

### Pattern 1: Email + Social Logins

Link email and OAuth identities:

```python
# User signs up with email
await resolve_user_identifier("alice@email.com", formation_id, db_manager, kv_cache)

# Later links GitHub
await associate_user_identifiers(
    identifiers=["alice@email.com", ("github_123", "github")],
    muxi_user_id="usr_existing",  # Link to existing user
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)

# Both identifiers now resolve to same user
```

### Pattern 2: Slack Integration

Map Slack user IDs to email:

```python
# Slack event arrives
slack_user_id = event["user"]  # U12345ABC

# Resolve to internal user
internal_id, muxi_id = await resolve_user_identifier(
    identifier=slack_user_id,
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache,
    identifier_type="slack"
)

# Use for memory operations
response = await formation.chat(
    message=event["text"],
    user_id=slack_user_id  # MUXI handles resolution
)
```

### Pattern 3: API Key to User Mapping

Link API keys to users:

```python
# Generate API key for user
api_key = generate_api_key()

await associate_user_identifiers(
    identifiers=[
        "alice@email.com",
        (api_key, "api_key")
    ],
    muxi_user_id="usr_alice",
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)

# API requests use API key
response = await formation.chat(
    message="Query",
    user_id=api_key  # Resolves to Alice
)
```

## Error Handling

### Identifier Conflicts

If you try to link an identifier that belongs to a different user:

```python
try:
    await associate_user_identifiers(
        identifiers=["alice@email.com"],  # Already linked to user A
        muxi_user_id="usr_bob",           # Trying to link to user B
        formation_id=formation_id,
        db_manager=db_manager,
        kv_cache=kv_cache
    )
except IntegrityError as e:
    print(f"Conflict: {e}")
    # Identifier conflicts detected: [{'identifier': 'alice@email.com', ...}]
```

### Invalid Inputs

The system validates inputs and fails fast:

```python
try:
    await resolve_user_identifier(
        identifier="",  # Empty string
        formation_id=formation_id,
        db_manager=db_manager,
        kv_cache=kv_cache
    )
except ValueError as e:
    print(f"Validation error: {e}")
    # identifier must be a non-empty string, got: str = ''
```

## Observability

The system emits observability events for monitoring:

### Cache Events

```python
# Cache hit
{
    "event_type": "user_identifier.cache_hit",
    "level": "debug",
    "data": {
        "identifier": "alice@email.com",
        "cached_value": "123:usr_abc123"
    }
}

# Cache miss
{
    "event_type": "user_identifier.cache_miss",
    "level": "debug",
    "data": {
        "identifier": "alice@email.com"
    }
}
```

### User Creation

```python
{
    "event_type": "user_identifier.created",
    "level": "info",
    "data": {
        "identifier": "alice@email.com",
        "internal_user_id": 123,
        "muxi_user_id": "usr_abc123",
        "formation_id": "formation_abc"
    }
}
```

### Association Events

```python
{
    "event_type": "user_identifier.associated",
    "level": "info",
    "data": {
        "muxi_user_id": "usr_abc123",
        "identifiers_associated": 2,
        "new_identifiers": ["slack_u123", "github_alice"],
        "existing_identifiers": ["alice@email.com"]
    }
}
```

## Troubleshooting

### Issue: User Not Found

**Symptom**: Operations fail with "User not found" errors

**Cause**: Identifier hasn't been created yet

**Solution**: Call `resolve_user_identifier()` first to create the user:

```python
# This automatically creates user if not found
internal_id, muxi_id = await resolve_user_identifier(
    identifier="new_user@email.com",
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)
```

### Issue: Cache Not Invalidating

**Symptom**: Changes to identifiers not reflected immediately

**Cause**: KV cache has stale data

**Solution**: The system automatically invalidates cache on writes. If issues persist:

```python
# Manual cache invalidation
cache_key = f"user_id:{formation_id}:{identifier}"
await kv_cache.delete(cache_key)
```

### Issue: Identifier Already Exists

**Symptom**: `IntegrityError` when associating identifiers

**Cause**: Trying to link an identifier to a different user

**Solution**: Check existing associations first:

```python
# Find who owns the identifier
internal_id, muxi_id = await resolve_user_identifier(
    identifier="disputed@email.com",
    formation_id=formation_id,
    db_manager=db_manager,
    kv_cache=kv_cache
)
print(f"Identifier belongs to: {muxi_id}")
```

### Issue: Performance Degradation

**Symptom**: Slow user resolution

**Diagnostics**:
1. Check KV cache is configured and healthy
2. Verify database indexes exist:
   ```sql
   SHOW INDEX FROM user_identifiers;
   ```
3. Monitor cache hit rate in observability events

**Solution**:
- Ensure KV cache is not None
- Check cache TTL is appropriate (default: 1 hour)
- Consider increasing cache size if hit rate is low

## Security Considerations

### Formation Isolation

User identities are isolated per formation. The same email in different formations creates different users:

```
Formation A: alice@email.com → User 123
Formation B: alice@email.com → User 456
```

This is intentional - each formation is a separate namespace.

### Internal ID Exposure

Never expose `users.id` (internal ID) to external systems. Always use:
- `users.public_id` (usr_xxxx) for MUXI system IDs
- Original `identifier` for external system IDs

### Identifier Validation

The system validates all identifiers:
- Must be non-empty strings
- Automatically trimmed of whitespace
- Case-sensitive (email case preserved)

## Implementation Details

### Core Functions

Located in `src/muxi/utils/user_resolution.py`:

- `resolve_user_identifier()`: Main resolution function with caching
- `associate_user_identifiers()`: Link multiple identifiers to one user

### Integration Points

Services that use user resolution:

1. **Long-Term Memory** (`src/muxi/services/memory/long_term.py`)
   - Automatic resolution in `_resolve_user_id_async()`
   - Memory operations use internal user ID

2. **Credential Resolver** (`src/muxi/formation/credentials/resolver.py`)
   - Resolves user for credential lookups
   - `_resolve_user_id()` method

3. **Scheduler** (`src/muxi/services/scheduler/manager.py`)
   - Resolves user for job associations
   - Audit trail uses internal user ID

4. **Chat Orchestrator** (`src/muxi/formation/overlord/chat_orchestrator.py`)
   - Resolves user for chat context
   - User synopsis integration

### Database Models

Located in `src/muxi/services/memory/long_term.py`:

```python
class User(Base, AsyncModelMixin):
    """Core user entity."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    public_id = Column(String(255), nullable=False)
    formation_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)

class UserIdentifier(Base, AsyncModelMixin):
    """External identifier mapping."""
    __tablename__ = "user_identifiers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    identifier = Column(String(255), nullable=False)
    identifier_type = Column(String(50))
    formation_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False)
```

## Testing

### E2E Tests

Comprehensive tests in `e2e/tests/17_multiple_identities/`:

- `test_multi_identity_basic.py`: Basic resolution and association
- `test_multi_identity_integration.py`: Full integration scenarios
- Memory tests verify user isolation

### Running Tests

```bash
# Run all multi-identity tests
pytest e2e/tests/17_multiple_identities/ -v

# Run with coverage
pytest e2e/tests/17_multiple_identities/ --cov=src/muxi/utils/user_resolution -v

# Run specific test
pytest e2e/tests/17_multiple_identities/test_multi_identity_basic.py::test_resolve_creates_user -v
```

## Future Enhancements

Planned improvements:

1. **Identity Merging**: API to merge two users into one
2. **Identifier Deletion**: Remove identifiers while preserving user
3. **Identifier Verification**: Email/phone verification workflows
4. **Audit Trail**: Track all identifier changes
5. **Admin API**: List/manage user identifiers

## Related Documentation

- [Multi-User Architecture](../multi-user-architecture.md) - High-level architecture
- [Memory Systems](../memory-systems.md) - How memory uses user IDs
- [User Credentials](../user-credentials.md) - Credential management per user
- [User Synopsis](../user-synopsis.md) - User context summarization

## Support

For issues or questions:
- GitHub Issues: https://github.com/muxi-ai/muxi-runtime/issues
- Documentation: https://docs.muxi.ai
- Community: https://discord.gg/muxi
