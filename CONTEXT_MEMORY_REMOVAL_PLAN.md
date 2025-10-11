# Context Memory Legacy Code Removal Plan

**Date:** 2025-10-11  
**Branch:** TBD (create from `user-synopsis`)  
**Status:** Planning Phase  
**Risk Level:** Medium (requires careful testing)

---

## Executive Summary

The legacy `context_memory` collection and its associated APIs were part of an old extraction system that has been superseded by the modern extraction system using rich collections (`user_identity`, `preferences`, `activities`, `relationships`, `work_projects`). 

**Current State:**
- Modern extraction system populates rich collections automatically
- User synopsis feature queries rich collections (NOT context_memory)
- Legacy `context_memory` APIs exist but mostly store empty data
- No backward compatibility needed (confirmed with user)

**Goal:** Remove all legacy context_memory code to reduce complexity and maintenance burden.

---

## Impact Analysis

### ✅ Safe to Remove

**Why it's safe:**
1. User synopsis doesn't use context_memory (uses rich collections)
2. Modern extraction doesn't write to context_memory (writes to rich collections)
3. Most users have empty context_memory collections
4. No external integrations depend on these APIs (internal-only)
5. User explicitly doesn't want backward compatibility

### ⚠️ What Needs Updating

**Tests:**
- `e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py` - Uses `add_user_context()` for test setup
- `tests/unit/test_user_synopsis.py` - Uses `add_user_context()` in invalidation test

**Documentation:**
- `docs/request-lifecycle.md` - References `get_user_context()` in pseudocode
- `docs/user-synopsis.md` - Mentions context_memory deprecation (should be removed entirely)

**Legacy Code:**
- `src/muxi/services/memory/extractor.py` - Has cleanup code that queries context_memory
- `src/muxi/services/memory/memobase.py` - Implements the core context_memory methods
- `src/muxi/formation/memory/user_context.py` - Wraps Memobase methods
- `src/muxi/formation/overlord/overlord.py` - Proxies to user_context_manager

---

## Detailed Removal Plan

### Phase 1: Code Mapping & Analysis ✅

**Files Containing Context Memory Code:**

1. **Core Implementation**
   - `src/muxi/services/memory/context_memory.py` - ContextMemory class (simple deque-based memory)
   - `src/muxi/services/memory/memobase.py` - Context memory collection methods
   - `src/muxi/services/memory/__init__.py` - Exports ContextMemory

2. **Wrapper Layer**
   - `src/muxi/formation/memory/user_context.py` - UserContextManager methods
   - `src/muxi/formation/overlord/overlord.py` - Proxy methods

3. **Legacy Usage**
   - `src/muxi/services/memory/extractor.py` - Old cleanup code (lines 210-236)

4. **Tests**
   - `e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py` - Test setup (lines 41, 113)
   - `tests/unit/test_user_synopsis.py` - Cache invalidation test (line 179)

5. **Documentation**
   - `docs/request-lifecycle.md` - Pseudocode example (line 425)
   - `docs/user-synopsis.md` - Deprecation mention
   - `e2e/results/20250930/14_user_synopsis.md` - Test report mentions

**Constants to Remove:**
- `CONTEXT_MEMORY_COLLECTION = "context_memory"` (memobase.py:53)
- `CONTEXT_MEMORY_TYPE = "context_memory"` (memobase.py:54)

**Methods to Remove:**

From `memobase.py`:
- `add_user_context()` (lines 599-720)
- `get_user_context()` (lines 721-858)
- `clear_user_context()` (lines 969-1087)
- `import_user_context_memory()` (lines 860-968)
- `update_user_context_memory()` (lines 1088-1189)

From `user_context.py`:
- `get_user_context()` (lines 30-68)
- `add_user_context()` (lines 70-136)
- `clear_user_context()` (lines 137-220)

From `overlord.py`:
- `get_user_context()` (lines 3701-3727)
- `add_user_context()` (lines 3741-3775)
- `clear_user_context()` (lines 3777-3799)

From `extractor.py`:
- `_purge_user_extracted_data()` (lines 205-236) - Entire method

**Files to Delete:**
- `src/muxi/services/memory/context_memory.py` - Entire file (128 lines)

---

### Phase 2: Test Updates (Priority: HIGH)

#### Update Synopsis E2E Test

**File:** `e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py`

**Current Approach (WRONG):**
```python
await overlord.add_user_context(
    user_id=user_id,
    knowledge={
        "name": "Alice Johnson",
        "role": "Senior Software Engineer",
        "team": "Platform Engineering",
    },
    source="test_setup"
)
```

**New Approach (CORRECT):**
```python
# Directly add memories to rich collections
await overlord.long_term_memory.add(
    text="name: Alice Johnson",
    collection="user_identity",
    external_user_id=user_id,
    metadata={"source": "test_setup", "type": "identity"}
)
await overlord.long_term_memory.add(
    text="role: Senior Software Engineer",
    collection="user_identity",
    external_user_id=user_id,
    metadata={"source": "test_setup", "type": "identity"}
)
await overlord.long_term_memory.add(
    text="team: Platform Engineering",
    collection="relationships",
    external_user_id=user_id,
    metadata={"source": "test_setup", "type": "team"}
)
```

**Rationale:** This tests the actual data path that synopsis uses (rich collections), not the legacy API.

**Lines to Update:**
- Line 41-49: Test 1 setup
- Line 113-121: Test 4 cache invalidation setup

---

#### Update Synopsis Unit Test

**File:** `tests/unit/test_user_synopsis.py`

**Current Code (line 179-183):**
```python
await manager.add_user_context(
    "test_user",
    {"name": "Test User"},
    source="test"
)
```

**New Approach:**
This test is checking cache invalidation. We need to trigger invalidation via extraction, not the legacy API.

**Option 1: Mock the invalidation directly**
```python
# Directly test invalidation method
await manager.invalidate_identity_synopsis_cache("test_user")
```

**Option 2: Trigger via extraction (more realistic)**
```python
# Simulate extraction updating identity collection
# This would naturally trigger cache invalidation
mock_overlord.long_term_memory.add = AsyncMock()
# Call extraction coordinator which triggers invalidation
```

**Recommended:** Option 1 (simpler, more focused unit test)

**Lines to Update:**
- Line 179-183: Change to direct invalidation call

---

### Phase 3: Code Removal (Priority: HIGH)

#### Step 1: Remove from `memobase.py`

**Remove Methods:**
```python
# Lines 599-720
async def add_user_context(...) -> List[str]:
    # 122 lines of legacy code

# Lines 721-858  
async def get_user_context(...) -> Dict[str, Any]:
    # 138 lines of legacy code

# Lines 969-1087
async def clear_user_context(...) -> bool:
    # 119 lines of legacy code

# Lines 860-968
async def import_user_context_memory(...) -> List[str]:
    # 109 lines of legacy code

# Lines 1088-1189
async def update_user_context_memory(...) -> List[str]:
    # 102 lines of legacy code
```

**Remove Constants:**
```python
# Lines 53-54
CONTEXT_MEMORY_COLLECTION = "context_memory"
CONTEXT_MEMORY_TYPE = "context_memory"
```

**Total Removal:** ~590 lines

**Side Effects:** None - these methods are self-contained

---

#### Step 2: Remove from `user_context.py`

**Remove Methods:**
```python
# Lines 30-68
async def get_user_context(...) -> Dict[str, Any]:
    # Just a wrapper calling memobase.get_user_context()

# Lines 70-136
async def add_user_context(...) -> Dict[str, Any]:
    # Wrapper + cache invalidation logic

# Lines 137-220
async def clear_user_context(...) -> bool:
    # Wrapper + cache invalidation logic
```

**Total Removal:** ~160 lines

**⚠️ CRITICAL:** These methods also invalidate synopsis cache!

**Cache Invalidation Code to Preserve:**
The `add_user_context()` and `clear_user_context()` methods have this code:

```python
# Invalidate synopsis caches after context update
try:
    internal_user_id = await self.overlord.long_term_memory.get_user_id(user_id)
    if internal_user_id:
        # Invalidate both identity and context synopsis
        await self.overlord.buffer_memory.kv_delete(
            internal_user_id, namespace="user_synopsis_identity"
        )
        await self.overlord.buffer_memory.kv_delete(
            internal_user_id, namespace="user_synopsis_context"
        )
except Exception:
    pass  # Cache invalidation failure is non-critical
```

**Solution:** This is ALREADY DUPLICATED in the synopsis feature itself!
- Identity cache invalidation happens in `extractor.py:_process_extraction_results()` (automatic)
- Manual invalidation available via `invalidate_identity_synopsis_cache()` (explicit)
- Context cache uses TTL (auto-expires, no manual invalidation needed)

**Conclusion:** Safe to remove, invalidation is handled elsewhere.

---

#### Step 3: Remove from `overlord.py`

**Remove Proxy Methods:**
```python
# Lines 3701-3727
async def get_user_context(...) -> Dict[str, Any]:
    # Just calls self.user_context_manager.get_user_context()

# Lines 3741-3775
async def add_user_context(...) -> List[str]:
    # Just calls self.user_context_manager.add_user_context()

# Lines 3777-3799
async def clear_user_context(...) -> bool:
    # Just calls self.user_context_manager.clear_user_context()
```

**Total Removal:** ~76 lines

**Side Effects:** None - just proxy methods

---

#### Step 4: Remove from `extractor.py`

**Remove Method:**
```python
# Lines 205-236
async def _purge_user_extracted_data(self, user_id: Any) -> bool:
    # Queries context_memory to find auto-extracted entries
    # Deletes them via clear_user_context()
    # Total: 32 lines
```

**Analysis:**
- This was for cleaning up OLD extraction data stored in context_memory
- Modern extraction stores in rich collections
- This method is likely never called anymore (need to verify)

**Check for callers:**
```bash
grep -r "_purge_user_extracted_data" src/
```

**If no callers:** Delete entire method  
**If has callers:** Keep shell of method, return True immediately

---

#### Step 5: Delete `context_memory.py`

**File:** `src/muxi/services/memory/context_memory.py` (128 lines)

**Analysis:**
- Implements `ContextMemory` class (simple deque-based memory)
- NOT the same as "context_memory collection" in Memobase
- This is a standalone memory implementation

**Check Usage:**
```bash
grep -r "ContextMemory" src/ --exclude-dir=__pycache__
```

**Result:** Only imported in `__init__.py`, never used elsewhere

**Decision:** Safe to delete

**Update `__init__.py`:**
```python
# Remove line 67
from .context_memory import ContextMemory

# Remove from __all__ (line ~72)
"ContextMemory",
```

---

### Phase 4: Documentation Updates (Priority: MEDIUM)

#### Update `docs/request-lifecycle.md`

**Current (line 425):**
```python
user_context = await long_term_memory.get_user_context(
    user_id=user_id,
    include_preferences=True,
)
```

**New:**
```python
# Get user synopsis for enhanced messages
user_synopsis = await overlord.get_user_synopsis(
    external_user_id=user_id
)
```

**Rationale:** Show the modern approach (synopsis), not legacy API.

---

#### Update `docs/user-synopsis.md`

**Remove Section:**
- "Future Enhancements > Context_memory Deprecation" (if still present)

**Update Section:**
- "Memory Sources" - Remove any references to context_memory collection
- Clarify that ONLY rich collections are used

**Current Text (check if present):**
```markdown
### Rich Collections vs Legacy context_memory

**Old Approach (Deprecated):**
- Queried `context_memory_{user_id}` collection
- Sparse, manually-populated data
```

**New Text:**
```markdown
### Memory Collections

Synopsis queries the following automatically-populated collections:
- Identity Tier: user_identity, relationships, work_projects
- Context Tier: preferences, activities

No manual population needed - extraction system handles it automatically.
```

---

#### Update `e2e/results/20250930/14_user_synopsis.md`

**Action:** Add note documenting the removal

**New Section (at bottom):**
```markdown
## Post-Release Updates

### October 2025: Legacy Context Memory Removal

**Removed:**
- Legacy `add_user_context()`, `get_user_context()`, `clear_user_context()` APIs
- `context_memory` collection support
- `ContextMemory` class (unused simple deque implementation)
- ~850 lines of dead code

**Rationale:**
- Synopsis uses rich collections (user_identity, preferences, etc.)
- Modern extraction populates rich collections automatically
- Legacy APIs were from old extraction system
- No backward compatibility needed

**Impact:**
- Cleaner codebase
- No functionality lost (synopsis already using rich collections)
- Tests updated to use modern approach
```

---

### Phase 5: Testing Strategy (Priority: CRITICAL)

#### Unit Tests

**Run:**
```bash
pytest tests/unit/test_user_synopsis.py -v
```

**Expected:**
- All 11 tests should pass
- Cache invalidation test updated to use direct invalidation

**If failures:** Check that cache invalidation logic is preserved.

---

#### E2E Tests

**Run Synopsis Test:**
```bash
python3 e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py
```

**Expected:**
- All 4 test cases pass
- Synopsis generation works with rich collections
- Cache invalidation verified

**If failures:** Check that test setup properly populates rich collections.

---

#### Regression Tests

**Critical Memory Tests:**
```bash
# Basic conversation (uses synopsis)
pytest e2e/tests/2_memory/test_2a1_basic_conversation_context.py -v

# PostgreSQL multi-user (uses synopsis) 
pytest e2e/tests/2_memory/test_2c1_postgresql_user_isolation.py -v

# SQLite persistence
pytest e2e/tests/2_memory/test_2b1_sqlite_persistence.py -v
```

**Expected:** All pass, no regressions

**Why these tests:**
- test_2a1: Uses buffer memory + synopsis feature
- test_2c1: Multi-user + synopsis (CRITICAL - this was the big win)
- test_2b1: Ensures extraction to rich collections still works

---

#### Integration Smoke Test

**Manual Test:**
```python
from muxi import Formation
import asyncio

async def test_synopsis():
    formation = Formation()
    await formation.load("test-formation.yaml")
    overlord = await formation.start_overlord()
    
    # Test 1: Add via extraction (modern way)
    response1 = await overlord.chat(
        "My name is John and I'm a developer",
        user_id="test_user",
        stream=False
    )
    
    await asyncio.sleep(5)  # Wait for extraction
    
    # Test 2: Verify synopsis includes extracted info
    synopsis = await overlord.get_user_synopsis("test_user")
    print(f"Synopsis: {synopsis}")
    assert "john" in synopsis.lower() or "developer" in synopsis.lower()
    
    # Test 3: Verify it's in enhanced message
    response2 = await overlord.chat(
        "What's my name?",
        user_id="test_user",
        stream=False
    )
    
    content = response2.content if hasattr(response2, "content") else str(response2)
    assert "john" in content.lower()
    
    print("✅ All manual tests passed!")

asyncio.run(test_synopsis())
```

**Expected:** All assertions pass, synopsis works end-to-end.

---

### Phase 6: Commit Strategy

**Commit 1: Test Updates**
```
fix: update synopsis tests to use rich collections instead of legacy API

- Update test_14a1 to populate user_identity/relationships directly
- Update test_user_synopsis to use direct invalidation
- Tests now reflect actual data path synopsis uses

This prepares for removing legacy context_memory APIs.
```

**Commit 2: Documentation Updates**
```
docs: update docs to reflect modern synopsis approach

- Update request-lifecycle.md to use get_user_synopsis()
- Update user-synopsis.md to clarify rich collections usage
- Remove context_memory deprecation notes (now fully removed)
```

**Commit 3: Core Code Removal**
```
refactor: remove legacy context_memory APIs and dead code

Removed ~850 lines of dead code:
- add_user_context(), get_user_context(), clear_user_context() (memobase, user_context, overlord)
- import_user_context_memory(), update_user_context_memory() (memobase)
- _purge_user_extracted_data() (extractor - queried context_memory)
- ContextMemory class (unused simple deque implementation)
- CONTEXT_MEMORY_COLLECTION, CONTEXT_MEMORY_TYPE constants

Synopsis uses rich collections (user_identity, preferences, etc.)
Modern extraction populates rich collections automatically.
Legacy APIs were from old extraction system.
No backward compatibility needed per user confirmation.

All tests passing, no regressions.
```

**Total:** 3 commits, clean history

---

## Risk Assessment

### Low Risk ✅

1. **Synopsis Functionality**
   - Synopsis already uses rich collections
   - No dependency on context_memory APIs
   - Tests verify correct behavior

2. **Modern Extraction**
   - Writes to rich collections, not context_memory
   - No code path uses context_memory

3. **Isolation**
   - Code to remove is self-contained
   - No complex dependencies

### Medium Risk ⚠️

1. **Cache Invalidation**
   - Removed code has invalidation logic
   - **Mitigation:** Already duplicated in extractor.py (automatic)
   - **Mitigation:** Manual invalidation method exists

2. **Unknown External Usage**
   - Could external code call `add_user_context()`?
   - **Mitigation:** This is internal API, no public SDK exposure
   - **Mitigation:** User confirmed no backward compatibility needed

### High Risk ❌

*None identified*

---

## Rollback Plan

**If issues discovered after merge:**

1. **Immediate:**
   - Revert commit 3 (core removal)
   - Keep commits 1-2 (test/doc updates)
   - Investigate root cause

2. **Short-term:**
   - Add deprecation warnings instead of removal
   - Create migration guide for any external users
   - Plan gradual removal

3. **Long-term:**
   - If truly needed, implement minimal shim layer
   - But prefer educating users to use rich collections directly

---

## Success Criteria

**Merge Ready When:**

✅ All unit tests passing (11/11)  
✅ Synopsis E2E test passing (4/4 test cases)  
✅ Memory regression tests passing (test_2a1, test_2c1, test_2b1)  
✅ No grep matches for removed method calls  
✅ Documentation updated and accurate  
✅ Clean commit history with clear messages  
✅ Code review approved  

---

## Timeline Estimate

**Phase 1 (Analysis):** ✅ Complete (this document)  
**Phase 2 (Test Updates):** 1-2 hours  
**Phase 3 (Code Removal):** 2-3 hours  
**Phase 4 (Documentation):** 1 hour  
**Phase 5 (Testing):** 2-3 hours  
**Phase 6 (Commit & Review):** 1 hour  

**Total:** 7-10 hours of focused work

---

## Open Questions

1. **Q:** Does `_purge_user_extracted_data()` have any callers?
   **A:** Need to grep codebase - likely none

2. **Q:** Are there any external integrations using these APIs?
   **A:** No - internal APIs only, no SDK exposure

3. **Q:** Should we add deprecation warnings first?
   **A:** No - user wants direct removal, no backward compatibility

4. **Q:** What about users with existing context_memory data?
   **A:** Irrelevant - synopsis doesn't query it, extraction doesn't write to it

---

## Approval

**Created By:** Claude (AI Assistant)  
**Reviewed By:** [Pending]  
**Approved By:** [Pending]  
**Start Date:** [Pending approval]

---

## Notes

- This is a straightforward cleanup of dead code
- Synopsis feature already works correctly without these APIs
- Main risk is missing some usage we didn't detect
- Comprehensive testing strategy mitigates this risk
- Clean commits allow easy rollback if needed

---

**Next Step:** Review this plan, get approval, execute phases 2-6.
