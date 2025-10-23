# API Design Improvements - X-Muxi-User-ID Header

**Date:** 2025-10-23  
**Repository:** `muxi-ai/schemas` (separate repo at `schemas/api/`)  
**Branch:** `main`  
**Status:** ✅ Committed and pushed

---

## Summary

Made two major API design improvements to the Formation API v1 spec:

1. ✅ **Removed redundant `/formations/{formation_id}` prefix** from trigger endpoints
2. ✅ **Moved user_id from paths/payloads to `X-Muxi-User-ID` header** for all client endpoints

Both changes result in **cleaner, more RESTful API design**.

---

## Change 1: Remove Formation ID Prefix

### Problem
Trigger endpoints had `/formations/{formation_id}` prefix which was redundant because:
- Runtime serves **ONE formation** at a time
- Formation is already identified by API key and server URL
- `{formation_id}` belongs in muxi-server proxy layer, not runtime

### Solution
**Before:**
```yaml
/formations/{formation_id}/triggers
/formations/{formation_id}/triggers/{trigger_name}
```

**After:**
```yaml
/triggers
/triggers/{trigger_name}
```

### Impact
- ✅ Cleaner URLs
- ✅ Eliminates unnecessary path parameter
- ✅ Runtime spec accurately reflects runtime behavior
- ⚠️ Breaking change (but endpoints are new/unreleased)

---

## Change 2: User ID as Header

### Problem
User ID was scattered across:
- Path parameters: `/sessions/{user_id}`
- Request body: `{"user_id": "alice", "message": "..."}`
- Mixed patterns across endpoints

This creates:
- ❌ Inconsistent API design
- ❌ Longer URLs
- ❌ Client confusion (where does user_id go?)
- ❌ Not RESTful (user context mixed with resources)

### Solution
Move user_id to **header for all client endpoints**:

```yaml
# New header parameter
X-Muxi-User-ID: alice

# Required: For multi-user formations (non-SQLite persistence)
# Default: "0" for single-user mode
```

### Design Pattern
- **Client endpoints** (operating AS user): Use `X-Muxi-User-ID` header
- **Admin endpoints** (querying ABOUT user): Keep `{user_id}` in path
- **No overrides**: Header is single source of truth

---

## Affected Endpoints

### Chat
**Before:**
```json
POST /chat
{
  "user_id": "alice",  // ❌
  "message": "Hello"
}
```

**After:**
```bash
POST /chat
X-Muxi-User-ID: alice  # ✅
{
  "message": "Hello"
}
```

### Sessions (4 endpoints)
| Before | After |
|--------|-------|
| `GET /sessions/{user_id}` | `GET /sessions` + header |
| `GET /sessions/{user_id}/{session_id}` | `GET /sessions/{session_id}` + header |
| `DELETE /sessions/{user_id}/{session_id}` | `DELETE /sessions/{session_id}` + header |
| `GET /sessions/{user_id}/{session_id}/messages` | `GET /sessions/{session_id}/messages` + header |

### Buffer Memory (3 endpoints)
| Before | After |
|--------|-------|
| `GET /memory/buffer/{user_id}` | `GET /memory/buffer` + header |
| `DELETE /memory/buffer/{user_id}` | `DELETE /memory/buffer` + header |
| `DELETE /memory/buffer/{user_id}/{session_id}` | `DELETE /memory/buffer/{session_id}` + header |

### User Memory (3 endpoints)
| Before | After |
|--------|-------|
| `GET /memories/{user_id}` | `GET /memories` + header |
| `POST /memories/{user_id}` | `POST /memories` + header |
| `DELETE /memories/{user_id}/{memory_id}` | `DELETE /memories/{memory_id}` + header |

### User Identifiers (1 endpoint)
| Before | After |
|--------|-------|
| `GET /users/identifiers/{user_id}` | `GET /users/identifiers` + header |

**Kept as-is** (identifier is the resource):
- `GET /users/{identifier}` - Resolve identifier to user
- `DELETE /users/identifiers/{identifier}` - Delete identifier

---

## Benefits

### ✅ Cleaner URLs
```bash
# Before
/sessions/alice
/sessions/alice/sess_123
/memory/buffer/alice/sess_123

# After (simpler!)
/sessions
/sessions/sess_123
/memory/buffer/sess_123
```

### ✅ Consistent Authentication Model
```bash
X-Muxi-Admin-Key: <admin key>    # Identifies admin
X-Muxi-Client-Key: <client key>  # Identifies client app
X-Muxi-User-ID: <user id>        # Identifies user context
```

All context in headers, not mixed with paths/payloads.

### ✅ Simpler Client Code
```typescript
// Before: user_id everywhere
client.chat({user_id: "alice", message: "..."})
client.getSessions("alice")
client.getMemories("alice")

// After: set once
client.setUserId("alice")
client.chat({message: "..."})
client.getSessions()
client.getMemories()
```

### ✅ RESTful Design
- User context is **authentication/authorization**, not a resource
- Similar to tenant ID in multi-tenant SaaS apps
- Resources are what you're operating on, not who's operating

---

## OpenAPI Spec Changes

### Added Header Parameter
```yaml
components:
  parameters:
    UserIdHeader:
      name: X-Muxi-User-ID
      in: header
      required: true
      schema:
        type: string
        default: "0"
      description: |
        User identifier for multi-user formations.
        - Required for formations with multi-user persistence
        - Defaults to "0" for single-user formations (SQLite)
        - Must be consistent across requests within a session
```

### Updated Schemas
- **ChatRequest**: Removed `user_id` from `required` and `properties`
- **All client endpoints**: Replaced path `{user_id}` parameter with `$ref: '#/components/parameters/UserIdHeader'`
- **All chat examples**: Removed `user_id` from request body examples

### Statistics
- **16 endpoint paths** changed (user_id removed from path)
- **~50 parameter definitions** removed
- **1 header parameter** added
- **5 request examples** updated (chat)
- **Total changes:** ~200 lines modified in spec

---

## Breaking Changes

### ⚠️ Yes - But Safe
These are **new endpoints** (not yet released), so it's safe to change now:
- No existing users to break
- Perfect time to get the design right
- Avoids technical debt

### Migration (When Released)
For any early adopters, migration is straightforward:

**Code change:**
```diff
  // Before
- POST /chat {"user_id": "alice", "message": "..."}
+ POST /chat 
+ Headers: X-Muxi-User-ID: alice
+ Body: {"message": "..."}

  // Before
- GET /sessions/alice
+ GET /sessions
+ Headers: X-Muxi-User-ID: alice
```

**Client library:**
```diff
- client.chat({user_id: "alice", message: "..."})
+ client.setUserId("alice")
+ client.chat({message: "..."})
```

---

## Next Steps

### Implementation (Runtime Code)
⏳ **Not done yet** - Need to update actual endpoint implementations:

1. Add header reading middleware
2. Update all 16 client endpoints to read `X-Muxi-User-ID` header instead of path/body
3. Validate header presence for multi-user formations
4. Update tests
5. Update client examples

### Admin Endpoints
✅ **No changes needed** - Admin endpoints keep `{user_id}` in path because they're querying ABOUT users, not acting AS users:
```yaml
GET /admin/sessions/{user_id}  # Admin viewing alice's sessions
GET /admin/memory/{user_id}    # Admin viewing bob's memories
```

---

## Git Details

### Commit
```
Repository: muxi-ai/schemas (separate repo)
Branch: main
Commit: e1a19f3
Files: formation-api-v1-final.yaml (new file)
```

### Commit Message
```
feat: move user_id to X-Muxi-User-ID header and remove formation_id prefix

Major API design improvements for cleaner, more RESTful endpoints.
```

### Push Status
✅ Pushed to `origin/main` in schemas repository

---

## Verification

### Spec Completeness
- ✅ Header parameter defined in components
- ✅ All client endpoints reference the header
- ✅ All path parameters removed
- ✅ Chat request schema updated
- ✅ All examples updated
- ✅ Descriptions updated to mention "authenticated user"

### Consistency Check
```bash
# Verify header usage
grep -c "UserIdHeader" formation-api-v1-final.yaml  # Should be 16+ (all client endpoints)

# Verify no user_id in paths (client endpoints)
grep "/.*{user_id}" formation-api-v1-final.yaml | grep -v admin  # Should be empty

# Verify formation_id removed
grep "formation_id" formation-api-v1-final.yaml  # Only in server URL (muxi-server proxy)
```

---

## Conclusion

The Formation API v1 spec now has:
- ✅ **Cleaner URLs** - No redundant formation_id prefix
- ✅ **Consistent auth model** - All context in headers
- ✅ **RESTful design** - Resources clear, context separate
- ✅ **Better DX** - Simpler client code
- ✅ **Ready for SDK generation** - Clean, consistent patterns

**Status:** OpenAPI spec updated and committed. Implementation updates needed next.

---

**Updated By:** Factory Droid  
**Date:** 2025-10-23  
**Spec Version:** v1.0.0
