# Multi-Identity User Management - Implementation Plan

**Issue:** #52  
**Status:** Spec Phase  
**Estimated Effort:** 2 days  
**Complexity:** Medium  

---

## Executive Summary

Implement support for associating multiple external identifiers (email, Slack ID, Telegram handle, etc.) to a single MUXI user, enabling context and memory carryover across communication channels.

### Current State
- Users identified by single `external_user_id` (string)
- Same person using different channels = separate users
- Fragmented memories, duplicate credentials, no context carryover

### Target State
- Users can have multiple identifiers linked to one MUXI account
- All identifiers resolve to same internal user
- Memories, credentials, and context shared across all channels
- Transparent to end users, simple API for developers

---

## Architecture Overview

### Identity Model

```
Developer provides: "alice@company.com" or "U12345" or "@alice_telegram"
                            ↓
              UserIdentifierService resolves
                            ↓
      MUXI finds/creates user: {id: 123, public_id: "usr_xyz123"}
                            ↓
      Stores identifier → user mapping in user_identifiers
                            ↓
              RequestContext populated with:
              - internal_user_id: 123 (for DB queries)
              - muxi_user_id: "usr_xyz123" (MUXI's canonical ID)
              - user_id: "alice@company.com" (what dev provided)
```

### Key Components

1. **Database Schema**: `user_identifiers` table for many-to-one mapping
2. **Resolution Helper**: Simple utility function for identifier resolution
3. **RequestContext**: Enhanced with three user ID types
4. **KV Cache**: FAISS-backed cache for fast resolution
5. **API Endpoint**: Single association endpoint
6. **Code Deletion**: Remove ~500 lines of redundant user lookup code

---

## Database Schema Changes

### Current Schema

```sql
-- users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(21) NOT NULL UNIQUE,
    external_user_id VARCHAR(255) NOT NULL,  -- TO BE REMOVED
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(external_user_id, formation_id)
);
```

### New Schema

```sql
-- users table (simplified)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(21) NOT NULL UNIQUE,
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_public_id ON users(public_id);
CREATE INDEX idx_users_formation_id ON users(formation_id);

-- user_identifiers table (NEW)
CREATE TABLE user_identifiers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(50),  -- Optional: 'email', 'slack', 'telegram', etc.
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, formation_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_user_identifiers_lookup ON user_identifiers(identifier, formation_id);
CREATE INDEX idx_user_identifiers_user_id ON user_identifiers(user_id);
```

### Migration Strategy

**Single-step migration:**
```sql
-- Step 1: Create new table
CREATE TABLE user_identifiers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(50),
    formation_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, formation_id)
);

-- Step 2: Migrate all existing external_user_id values
INSERT INTO user_identifiers (user_id, identifier, formation_id, created_at)
SELECT id, external_user_id, formation_id, created_at 
FROM users;

-- Step 3: Drop external_user_id column (after code deployment)
ALTER TABLE users DROP COLUMN external_user_id;
```

**That's it!** Simple, safe, reversible.

---

## Enhanced RequestContext

### Current

```python
@dataclass
class RequestContext:
    id: str
    formation_id: Optional[str] = None
    user_id: Optional[str] = None  # Developer's identifier (string)
    session_id: Optional[str] = None
```

### Enhanced

```python
@dataclass
class RequestContext:
    id: str
    status: str = "processing"
    started: float = field(default_factory=lambda: time.time() * 1000)
    formation_id: Optional[str] = None
    
    # User identity (three aspects)
    internal_user_id: Optional[int] = None      # Database ID (for queries) - NEVER exposed
    muxi_user_id: Optional[str] = None          # MUXI's canonical public_id (e.g., "usr_abc123")
    user_id: Optional[str] = None               # What developer provided (e.g., "alice@email.com")
    
    session_id: Optional[str] = None
    tokens: TokenUsage = field(default_factory=TokenUsage)
    _parent_events: Set[str] = field(default_factory=set, init=False)
```

### Usage Pattern

**Before (80+ locations doing this):**
```python
# Every method does DB lookup
async def add(self, content, external_user_id, ...):
    user = await self._get_or_create_user(session, external_user_id)  # DB query!
    memory = await Memory.create(session, user_id=user.id, ...)
```

**After (resolve once at entry):**
```python
# At entry point - resolve once
async def process_request(self, user_id: str, ...):
    # Resolve identifier to internal IDs (cached)
    internal_id, muxi_id = await resolve_user_identifier(
        identifier=user_id,
        formation_id=self.formation_id,
        db_manager=self.db_manager,
        kv_cache=self.kv
    )
    
    # Set context once
    ctx = RequestContext(
        id=request_id,
        internal_user_id=internal_id,  # For queries
        muxi_user_id=muxi_id,          # For observability
        user_id=user_id,               # What dev provided
        ...
    )
    set_request_context(ctx)
    
    # All downstream methods use context (no parameters!)
    await self.long_term_memory.add(content=memory)
```

**In downstream methods:**
```python
# Simple - no user parameter, no DB lookup!
async def add(self, content, ...):
    ctx = get_current_request_context()
    memory = await Memory.create(
        session,
        user_id=ctx.internal_user_id,  # Integer from context
        ...
    )
    
    # Observability uses canonical ID
    observability.observe(
        data={
            "muxi_user_id": ctx.muxi_user_id,  # Canonical (for correlation)
            "user_id": ctx.user_id              # Channel-specific (optional)
        }
    )
```

**Net result:** Delete `_get_or_create_user()` from 80+ locations!

---

## User Resolution Helper

### Simple Utility Function (Not a Service Class!)

**Location:** `src/muxi/utils/user_resolution.py`

```python
async def resolve_user_identifier(
    identifier: str,
    formation_id: str,
    db_manager,
    kv_cache,
    identifier_type: Optional[str] = None
) -> Tuple[int, str]:
    """
    Resolve any identifier to (internal_user_id, muxi_user_id).
    
    Simple utility function with KV caching. No class needed.
    
    Args:
        identifier: Developer-provided ID (email, Slack ID, etc.)
        formation_id: Formation ID
        db_manager: Database manager
        kv_cache: KV cache instance
        identifier_type: Optional type hint (for new users)
    
    Returns:
        (internal_user_id: int, muxi_user_id: str)
        
    Example:
        >>> await resolve_user_identifier("alice@email.com", "form_123", db, kv)
        (123, "usr_abc123")
    """
    cache_key = f"user_id:{formation_id}:{identifier}"
    
    # Step 1: Check cache
    if cached_value := await kv_cache.get(cache_key):
        internal_id_str, muxi_id = cached_value.split(":", 1)
        observability.observe(
            event_type=observability.SystemEvents.CACHE_HIT,
            data={"cache_type": "user_identifier", "identifier": identifier}
        )
        return (int(internal_id_str), muxi_id)
    
    # Step 2: Database lookup
    observability.observe(
        event_type=observability.SystemEvents.CACHE_MISS,
        data={"cache_type": "user_identifier", "identifier": identifier}
    )
    
    async with db_manager.get_async_session() as session:
        # Check user_identifiers table
        result = await session.execute(
            select(User.id, User.public_id)
            .join(UserIdentifier, User.id == UserIdentifier.user_id)
            .where(
                UserIdentifier.identifier == identifier,
                UserIdentifier.formation_id == formation_id
            )
        )
        
        if row := result.first():
            internal_id, muxi_id = row
        else:
            # Create new user + identifier
            new_user = await User.create(
                session,
                public_id=get_default_nanoid(),
                formation_id=formation_id
            )
            
            await UserIdentifier.create(
                session,
                user_id=new_user.id,
                identifier=identifier,
                identifier_type=identifier_type,
                formation_id=formation_id
            )
            
            await session.commit()
            internal_id, muxi_id = new_user.id, new_user.public_id
    
    # Step 3: Cache result
    await kv_cache.set(
        cache_key,
        f"{internal_id}:{muxi_id}",
        ttl=3600  # 1 hour
    )
    
    return (internal_id, muxi_id)
```

**Why a function instead of a class:**
- Only ~50 lines
- Stateless operation
- No complex lifecycle
- Easier to test
- Less overhead

### Association Helper

#### `associate_user_identifiers()`

```python
async def associate_user_identifiers(
    identifiers: List[Union[str, Tuple[str, str], Dict[str, str]]],
    muxi_user_id: Optional[str],
    formation_id: str,
    db_manager,
    kv_cache
) -> Dict[str, Any]:
    """
    Associate multiple identifiers to the same user.
    
    Simple function - no class needed. Supports flexible input formats.
    
    Args:
        identifiers: List of identifiers. Supports:
            - Strings: ["alice@email.com", "U12345"]
            - Tuples: [("alice@email.com", "email"), ("U12345", "slack")]
            - Dicts: [{"identifier": "...", "type": "..."}]
        muxi_user_id: MUXI user ID to associate to
        formation_id: Formation ID
        db_manager: Database manager
        kv_cache: KV cache for invalidation
    
    Returns:
        {
            "muxi_user_id": "usr_abc123",
            "identifiers_associated": 3,
            "new_identifiers": ["U12345"],
            "existing_identifiers": ["alice@email.com"]
        }
    """
    # Implementation details same as before...
    # ~100 lines for normalization, conflict detection, association
```

**Total code:** ~150 lines for both functions (not 200+ for a service class!)

---

## Caching Strategy

### Single-Tier KV Cache with FAISS

**Why Single-Tier:**
- L1 (in-memory) cache without TTL = memory leak risk
- FAISS-backed KV store is fast enough (~1-2ms)
- Simpler architecture, easier to reason about
- Shared across all workers automatically
- Persists across restarts

**Cache Architecture:**
```python
# Use existing FAISS-backed KV cache with dedicated namespace
cache_key = f"user_identifier:{formation_id}:{identifier}"
value = f"{internal_user_id}:{muxi_user_id}"
ttl = 3600  # 1 hour
```

### Performance Characteristics

| Metric | Without Cache | With Cache | Improvement |
|--------|--------------|------------|-------------|
| **Cache Hit (FAISS KV)** | - | ~1-2ms | - |
| **DB Query (JOIN)** | ~5-10ms | ~5-10ms | - |
| **Expected Hit Rate** | 0% | 95%+ | - |
| **Expected Miss Rate** | 100% | <5% | - |
| **Overall Avg Latency** | 5-10ms | ~1-2ms | **3-5x faster** |

**Notes:**
- FAISS-backed KV is fast enough for this use case
- No memory leak risk (TTL handled by KV store)
- Simpler code, fewer moving parts
- Shared across workers (consistent view)

### Cache Invalidation

Invalidate when:
- New identifier associated to user
- User deleted
- Manual cache clear

```python
async def invalidate_cache(self, identifier: str):
    """Invalidate cache for identifier"""
    cache_key = f"user_identifier:{self.formation_id}:{identifier}"
    await self.kv.delete(cache_key)
```

---

## API Design

### Developer API

#### POST `/users/identifiers` (Associate Identifiers)

**Request:**
```json
{
  "muxi_user_id": "usr_abc123",  // Optional
  "identifiers": [
    "alice@company.com",
    {"identifier": "U12345", "type": "slack"},
    ["@alice_tg", "telegram"]
  ]
}
```

**Response:**
```json
{
  "muxi_user_id": "usr_abc123",
  "identifiers_associated": 3,
  "new_identifiers": ["U12345", "@alice_tg"],
  "existing_identifiers": ["alice@company.com"]
}
```

**Error Cases:**
- `409 Conflict`: Identifier already linked to different user
- `400 Bad Request`: Invalid input format
- `404 Not Found`: muxi_user_id not found

#### GET `/users/{muxi_user_id}/identifiers` (List Identifiers)

**Response:**
```json
{
  "muxi_user_id": "usr_abc123",
  "identifiers": [
    {
      "identifier": "alice@company.com",
      "type": "email",
      "created_at": "2025-01-15T10:30:00Z"
    },
    {
      "identifier": "U12345",
      "type": "slack",
      "created_at": "2025-01-20T14:22:00Z"
    }
  ]
}
```

#### DELETE `/users/{muxi_user_id}/identifiers/{identifier}` (Remove Identifier)

**Response:**
```json
{
  "message": "Identifier removed successfully",
  "remaining_identifiers": 2
}
```

**Error Cases:**
- `400 Bad Request`: Cannot remove last identifier
- `404 Not Found`: Identifier not found

---

## Implementation Phases (Simplified!)

### Phase 1: Database & Models (0.25 day)

**Tasks:**
- [ ] Create `user_identifiers` table (PostgreSQL + SQLite)
- [ ] Run single-step migration (INSERT + DROP COLUMN)
- [ ] Add `UserIdentifier` SQLAlchemy model
- [ ] Enhance `RequestContext` dataclass (add 2 fields)
- [ ] Update `init_schema.sql` and `init_schema_sqlite.sql` with final schema

**Files:**
- `migrations/add_user_identifiers.sql` (temporary - for testing)
- `migrations/add_user_identifiers_sqlite.sql` (temporary - for testing)
- `migrations/init_schema.sql` (final schema for fresh installs)
- `migrations/init_schema_sqlite.sql` (final schema for fresh installs)
- `src/muxi/services/memory/long_term.py` (UserIdentifier model)
- `src/muxi/datatypes/observability.py` (RequestContext)

**IMPORTANT NOTES:**

1. **Migration Development Workflow:**
   - Use `postgresql://muxi@localhost/muxi_test` for developing and testing migrations
   - Create migration scripts first (`add_user_identifiers.sql`)
   - Test thoroughly on PostgreSQL test database
   - Once working, update both init_schema files

2. **Final Schema Integration:**
   - After migrations work, update `migrations/init_schema.sql` (PostgreSQL)
   - Also update `migrations/init_schema_sqlite.sql` (SQLite)
   - This ensures new installs get the correct schema without running migrations
   - Keep migration scripts for existing deployments

3. **SQLite Compatibility:**
   - Everything must work on both PostgreSQL AND SQLite
   - SQLite is single-user mode (user_id is always "0")
   - SQLite should not error out, even though multi-identity is less useful
   - Test all code paths on both database backends

4. **Test Location:**
   - Create E2E tests in `e2e/tests/17_multiple_identities/`
   - Include tests for both PostgreSQL and SQLite
   - Test single-user mode (SQLite) and multi-user mode (PostgreSQL)

**Migration Script:**
```sql
-- Single migration - no multi-step
CREATE TABLE user_identifiers (...);
INSERT INTO user_identifiers (user_id, identifier, formation_id, created_at)
SELECT id, external_user_id, formation_id, created_at FROM users;
ALTER TABLE users DROP COLUMN external_user_id;
```

**Testing:**
- Run migration on test database
- Verify all existing users have identifiers
- Test rollback if needed

---

### Phase 2: Resolution Helper (0.25 day)

**Tasks:**
- [ ] Create `resolve_user_identifier()` function (~50 lines)
- [ ] Create `associate_user_identifiers()` function (~100 lines)
- [ ] Add KV caching logic
- [ ] Add observability events

**Files:**
- `src/muxi/utils/user_resolution.py` (new, ~150 lines total)

**Functions:**
```python
async def resolve_user_identifier(...) -> (int, str)  # ~50 lines
async def associate_user_identifiers(...) -> dict     # ~100 lines
```

**Testing:**
- Unit tests for resolution with cache
- Unit tests for association with normalization
- Unit tests for conflict detection

**Note:** No service class needed! Just simple utility functions.

---

### Phase 3: Entry Point Updates (0.25 day)

**Tasks:**
- [ ] Update `Overlord.process_request()` - call resolver, set context
- [ ] Update `SchedulerManager._get_or_create_user()` - same pattern
- [ ] Update WebSocket entry if needed

**Files:**
- `src/muxi/formation/overlord/overlord.py`
- `src/muxi/services/scheduler/manager.py`

**Pattern:**
```python
async def process_request(self, user_id: str, ...):
    # Import helper
    from ...utils.user_resolution import resolve_user_identifier
    
    # Resolve once
    internal_id, muxi_id = await resolve_user_identifier(
        identifier=user_id,
        formation_id=self.formation_id,
        db_manager=self.db_manager,
        kv_cache=self.kv
    )
    
    # Set context
    ctx = RequestContext(
        id=request_id,
        internal_user_id=internal_id,
        muxi_user_id=muxi_id,
        user_id=user_id,
        ...
    )
    set_request_context(ctx)
```

**Testing:**
- Integration tests for entry points
- Verify context is set correctly

---

### Phase 4: Code Deletion (0.5 day) 🎉

**This is where the magic happens - we DELETE more code than we add!**

**Tasks:**
- [ ] Delete `_get_or_create_user()` method (sync version)
- [ ] Delete `_get_or_create_user_async()` method (async version)
- [ ] Delete all calls to these methods (~80 locations)
- [ ] Remove `external_user_id` parameters from internal methods
- [ ] Update methods to use `ctx.internal_user_id` directly
- [ ] Remove JOINs with users table (not needed anymore!)
- [ ] Update observability to use `ctx.muxi_user_id`

**Files to Update (~50-80 locations):**
- `src/muxi/services/memory/long_term.py`
- `src/muxi/services/memory/memobase.py`
- `src/muxi/services/scheduler/manager.py`
- `src/muxi/formation/credentials/resolver.py`
- `src/muxi/formation/memory/*.py`
- `src/muxi/services/memory/extractor.py`

**Before (80+ locations):**
```python
async def add(self, content: str, external_user_id: str, ...):
    # DB lookup every time!
    user = await self._get_or_create_user(session, external_user_id)
    memory = await Memory.create(session, user_id=user.id, ...)
```

**After:**
```python
async def add(self, content: str, ...):  # No external_user_id param!
    ctx = get_current_request_context()
    
    # Direct integer lookup - no DB query!
    memory = await Memory.create(
        session,
        user_id=ctx.internal_user_id,  # Fast!
        ...
    )
    
    # Observability uses canonical ID
    observability.observe(
        data={
            "muxi_user_id": ctx.muxi_user_id,  # For correlation
            "user_id": ctx.user_id              # Optional channel context
        }
    )
```

**Net Effect:**
- ❌ Delete `_get_or_create_user()` methods (2 methods × ~30 lines = 60 lines)
- ❌ Delete 80+ calls to these methods
- ❌ Remove 80+ `external_user_id` parameters
- ❌ Remove JOINs with users table
- ✅ Use `ctx.internal_user_id` everywhere
- **Result: Delete ~500 lines of code!**

**Testing:**
- Run full test suite - verify no regressions
- Check memory operations still work
- Check credentials still resolve
- Check scheduler queries still work

---

### Phase 5: API Endpoint (0.25 day)

**Tasks:**
- [ ] Create `POST /users/identifiers` endpoint
- [ ] Add request/response models
- [ ] Call `associate_user_identifiers()` helper

**Files:**
- `src/muxi/formation/server/routes/admin/users.py` (new, ~50 lines)
- `src/muxi/datatypes/api.py` (request/response models)

**Simple Implementation:**
```python
@router.post("/users/identifiers")
async def associate_identifiers(request: AssociateIdentifiersRequest):
    from ...utils.user_resolution import associate_user_identifiers
    
    result = await associate_user_identifiers(
        identifiers=request.identifiers,
        muxi_user_id=request.muxi_user_id,
        formation_id=get_formation_id(),
        db_manager=get_db_manager(),
        kv_cache=get_kv_cache()
    )
    return result
```

**Testing:**
- Test all input formats
- Test conflict detection
- Test error cases

---

### Phase 6: Testing & Documentation (0.5 day)

**Tasks:**
- [ ] Create E2E test scenarios in `e2e/tests/17_multiple_identities/`
- [ ] Test on both PostgreSQL and SQLite backends
- [ ] Update formation examples
- [ ] Write developer documentation
- [ ] Update API documentation
- [ ] Add troubleshooting guide
- [ ] Update caching documentation

**E2E Test Scenarios (in `e2e/tests/17_multiple_identities/`):**

1. **Single Identity User**
   - User interacts via single channel
   - Verify memories persist
   - Verify credentials work

2. **Multi-Identity Association**
   - User interacts via email
   - Associate Slack ID
   - Verify context carries over
   - Verify memories accessible from both channels

3. **Progressive Discovery**
   - User starts with email
   - Add Slack ID after 10 interactions
   - Add Telegram ID after 20 interactions
   - Verify all interactions linked to same user

4. **Conflict Detection**
   - Try to link identifier already used by another user
   - Verify error returned
   - Verify no data corruption

5. **Cache Performance**
   - Make 1000 requests with same identifier
   - Verify L1 cache hit rate >90%
   - Verify average latency <1ms

**Files:**
- `e2e/tests/17_multiple_identities/` (new - both PostgreSQL and SQLite tests)
- `docs/features/multi-identity-users.md` (new)
- `examples/multi_identity_example.py` (new)
- `docs/features/caching.md` (update)

---

## File Changes Summary

### New Files
- `migrations/add_user_identifiers.sql` (~30 lines - temporary for migration)
- `migrations/add_user_identifiers_sqlite.sql` (~30 lines - temporary for migration)
- `src/muxi/utils/user_resolution.py` (~150 lines - TWO SIMPLE FUNCTIONS!)
- `src/muxi/formation/server/routes/admin/users.py` (~50 lines)
- `docs/features/multi-identity-users.md`
- `e2e/tests/17_multiple_identities/` (PostgreSQL + SQLite tests)

### Updated Init Schemas
- `migrations/init_schema.sql` (add user_identifiers table, remove external_user_id)
- `migrations/init_schema_sqlite.sql` (add user_identifiers table, remove external_user_id)

**Total New Code: ~300 lines**

### Deleted Code (Major Win!)
- `_get_or_create_user()` method (sync) - ~30 lines
- `_get_or_create_user_async()` method - ~30 lines
- 80+ calls to these methods
- 80+ `external_user_id` parameters
- JOINs with users table in queries

**Total Deleted: ~500 lines**

**Net Result: -200 lines of code!**

### Modified Files (Major Changes)
- `src/muxi/datatypes/observability.py` (+10 lines: RequestContext enhancement)
- `src/muxi/formation/overlord/overlord.py` (+5 lines: call resolver, set context)
- `src/muxi/services/memory/long_term.py` (-100 lines: remove user lookup code)
- `src/muxi/services/scheduler/manager.py` (-50 lines: same)
- `src/muxi/formation/credentials/resolver.py` (-50 lines: same)

### Modified Files (Minor Changes, ~50-80 locations)
- Remove `external_user_id` parameter
- Use `ctx.internal_user_id` instead
- Update observability to use `ctx.muxi_user_id`

**Pattern Change (repeated 80+ times):**
```diff
- async def add(self, content: str, external_user_id: str, ...):
-     user = await self._get_or_create_user(session, external_user_id)
-     memory = await Memory.create(session, user_id=user.id, ...)
+ async def add(self, content: str, ...):
+     ctx = get_current_request_context()
+     memory = await Memory.create(session, user_id=ctx.internal_user_id, ...)
```

---

## Testing Strategy

### Unit Tests
- [ ] UserIdentifierService.resolve_or_create()
- [ ] UserIdentifierService.associate_identifiers()
- [ ] UserIdentifierService cache behavior (KV cache)
- [ ] UserIdentifier model CRUD operations
- [ ] RequestContext properties
- [ ] Identifier normalization logic

### Integration Tests
- [ ] End-to-end identifier resolution
- [ ] Multi-identity association flow
- [ ] Cache invalidation on association
- [ ] Conflict detection
- [ ] Cross-service integration (memory, credentials, scheduler)

### E2E Tests
- [ ] Single identity user flow
- [ ] Multi-identity association flow
- [ ] Progressive discovery flow
- [ ] Conflict detection flow
- [ ] Cache performance test
- [ ] Load test (1000 req/s)

### Migration Tests
- [ ] Data migration from old schema
- [ ] Rollback procedures
- [ ] Data integrity verification
- [ ] Performance comparison (before/after)

---

## Performance Targets

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| **User Resolution Time** | 5-10ms | <1ms | 5-10x |
| **Cache Hit Rate** | 0% | >95% | ∞ |
| **Memory Overhead** | 0MB | ~1MB | +1MB |
| **Database Queries** | 100/s | 5/s | 20x reduction |

---

## Rollback Plan

### Rollback Triggers
- Data corruption detected
- Performance regression >50%
- Critical bugs in production
- Cache invalidation issues

### Rollback Procedure

**Step 1: Revert Code**
```bash
git revert <commit-range>
git push origin main
```

**Step 2: Revert Database**
```sql
-- Don't drop user_identifiers (data loss)
-- Instead, restore external_user_id column
ALTER TABLE users ADD COLUMN external_user_id VARCHAR(255);

-- Repopulate from user_identifiers (use first identifier)
UPDATE users u SET external_user_id = (
    SELECT identifier FROM user_identifiers ui
    WHERE ui.user_id = u.id
    ORDER BY created_at ASC
    LIMIT 1
);

-- Restore unique constraint
ALTER TABLE users ADD CONSTRAINT uq_user_formation_external_id 
    UNIQUE(external_user_id, formation_id);
```

**Step 3: Verify**
- Test user resolution works
- Verify no data loss
- Check application logs

---

## Risk Assessment

### High Risk Areas

1. **Data Migration**
   - Risk: Data loss during migration
   - Mitigation: Backup before migration, test on staging, rollback plan

2. **Cache Invalidation**
   - Risk: Stale cache causing incorrect user resolution
   - Mitigation: Conservative TTLs, explicit invalidation, monitoring

3. **Query Updates (80+ locations)**
   - Risk: Missing updates causing incorrect user isolation
   - Mitigation: Comprehensive grep, systematic review, extensive testing

4. **Performance Regression**
   - Risk: New cache layer adds latency
   - Mitigation: Benchmark before/after, two-tier cache, monitoring

### Medium Risk Areas

5. **API Conflicts**
   - Risk: Identifier already linked to different user
   - Mitigation: Conflict detection, clear error messages, transaction safety

6. **Cache Coherency**
   - Risk: Stale cache after identifier association
   - Mitigation: Explicit invalidation on write, reasonable TTL (1hr)

### Low Risk Areas

7. **RequestContext Enhancement**
   - Risk: Breaking existing code
   - Mitigation: Backward compatible property, gradual rollout

---

## Observability & Monitoring

### Metrics to Track

**Resolution Performance:**
- `user_identifier_resolution_time_ms` (histogram)
- `user_identifier_cache_hit_rate` (gauge)
- `user_identifier_cache_l1_hits` (counter)
- `user_identifier_cache_l2_hits` (counter)
- `user_identifier_cache_misses` (counter)

**Association Operations:**
- `user_identifiers_associated_total` (counter)
- `user_identifier_conflicts_total` (counter)
- `user_identifier_associations_per_user` (histogram)

**Cache Health:**
- `user_identifier_cache_l1_size` (gauge)
- `user_identifier_cache_evictions` (counter)
- `user_identifier_cache_invalidations` (counter)

### Alerts

**Critical:**
- Cache hit rate <50% (should be >95%)
- Resolution time >100ms (should be <1ms)
- High conflict rate (>1% of associations)

**Warning:**
- Cache hit rate <80%
- Resolution time >10ms
- L1 cache size approaching max

### Logging

```python
# Resolution events
observability.observe(
    event_type=observability.SystemEvents.USER_IDENTIFIER_RESOLVED,
    data={
        "identifier": identifier,
        "muxi_user_id": muxi_id,
        "cache_level": "l1|l2|db",
        "resolution_time_ms": duration
    }
)

# Association events
observability.observe(
    event_type=observability.SystemEvents.USER_IDENTIFIERS_ASSOCIATED,
    data={
        "muxi_user_id": muxi_id,
        "identifiers_added": count,
        "total_identifiers": total
    }
)
```

---

## Documentation Updates

### Developer Documentation

**New Files:**
- `docs/features/multi-identity-users.md` - Complete feature guide
- `docs/api/user-identifiers.md` - API reference
- `examples/multi_identity_example.py` - Usage examples

**Updated Files:**
- `docs/features/caching.md` - Add user identifier caching section
- `README.md` - Mention multi-identity support
- `CHANGELOG.md` - Add feature description

### API Documentation

**OpenAPI/Swagger:**
- Add `/users/identifiers` endpoints
- Add request/response schemas
- Add examples for each input format

### Internal Documentation

**Update:**
- Architecture diagrams (add UserIdentifierService)
- Database schema documentation
- RequestContext usage guide
- Performance tuning guide

---

## Success Criteria

### Functional Requirements
- ✅ Users can have multiple identifiers
- ✅ All identifiers resolve to same MUXI user
- ✅ Memories/credentials shared across identifiers
- ✅ Developers can associate identifiers via API
- ✅ Conflict detection prevents incorrect associations

### Performance Requirements
- ✅ User resolution <1ms (95th percentile)
- ✅ Cache hit rate >95%
- ✅ Database query reduction >90%
- ✅ Memory overhead <10MB

### Quality Requirements
- ✅ Zero data loss during migration
- ✅ 100% test coverage for new code
- ✅ No regressions in existing functionality
- ✅ API response times unchanged

### Developer Experience
- ✅ Simple API for common cases
- ✅ Clear error messages
- ✅ Comprehensive documentation
- ✅ Working examples provided

---

## Timeline

### Day 1
- **AM**: Phase 1 - Database & Models (0.25 day)
- **PM**: Phase 2 - Resolution Helper (0.25 day)

### Day 2
- **AM**: Phase 3 - Entry Point Updates (0.25 day)
- **AM**: Phase 4 - Code Deletion (0.5 day)
- **PM**: Phase 5 - API Endpoint (0.25 day)
- **PM**: Phase 6 - Testing & Documentation (0.5 day)

**Total: 2 days**

---

## Open Questions

1. **Should we auto-detect identifier type?**
   - Email: regex match
   - Slack: U[A-Z0-9]+ pattern
   - Telegram: @ prefix
   - Phone: +[0-9]+ pattern
   
   **Decision:** Optional auto-detection, but allow explicit type

2. **Should we allow removing the last identifier?**
   
   **Decision:** No - user must have at least one identifier

3. **Should we expose internal_user_id to developers?**
   
   **Decision:** No - only expose muxi_user_id (public_id)

4. **Should we add identifier verification flow?**
   - Email verification codes
   - Slack workspace verification
   
   **Decision:** Not in MVP - developers handle verification

5. **Should we support merging two MUXI users?**
   - User accidentally created twice
   - Want to merge memories/credentials
   
   **Decision:** Not in MVP - future enhancement

---

## Future Enhancements (Out of Scope)

1. **Identifier Verification**
   - Email verification codes
   - OAuth-based verification
   - Phone number verification

2. **User Merge**
   - Merge two MUXI users into one
   - Combine memories, credentials, jobs
   - Transfer all identifiers

3. **Identifier Priority**
   - Mark one identifier as "primary"
   - Use for notifications/display

4. **Identifier Metadata**
   - Last used timestamp
   - Verification status
   - Source (manual vs auto-detected)

5. **Batch Operations**
   - Bulk associate identifiers
   - Bulk remove identifiers
   - Export user data

6. **Analytics**
   - Most common identifier types
   - Average identifiers per user
   - Channel distribution

---

## References

- **Issue**: #52 - EPIC: Associate multiple identities to a single user
- **Related**: #83 - LLM Response Caching (caching patterns)
- **Database Schema**: `migrations/init_schema.sql`
- **Caching Docs**: `docs/features/caching.md`

---

## Approval Checklist

Before starting implementation:

- [ ] Architecture reviewed and approved
- [ ] Database schema validated
- [ ] API design approved
- [ ] Performance targets agreed
- [ ] Testing strategy confirmed
- [ ] Timeline approved
- [ ] Risk assessment reviewed
- [ ] Rollback plan documented

---

**Status:** ✅ Ready for Implementation  
**Next Step:** Create sub-tasks for each phase in GitHub
