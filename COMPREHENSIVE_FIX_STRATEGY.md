# Comprehensive Events Audit - Fix Strategy

## Overall Status

**Total Events**: 1,261
**Already Fixed**: 3 (Chunk 1 level changes)
**Remaining Issues**: 449 (35.6%)

## Fix Priorities by Impact

### PRIORITY 1: Critical Misclassifications (157 events)

#### Category A: ErrorEvents.WARNING → Specific Types (33 events in Chunk 3)
**Pattern**: ErrorEvents.WARNING being used as event type instead of proper ErrorEvent subtypes
**Files Affected**: knowledge/base.py, extractor.py, buffer_manager.py, overlord.py, sops.py, etc.
**Action**: Replace with specific error types based on context
**Examples**:
- `ErrorEvents.WARNING` → `ErrorEvents.KNOWLEDGE_SOURCE_MISSING`
- `ErrorEvents.WARNING` → `ErrorEvents.MARKITDOWN_INITIALIZATION_FAILED`
- `ErrorEvents.WARNING` → `ErrorEvents.METADATA_PERSISTENCE_FAILED`
- `ErrorEvents.WARNING` → `ErrorEvents.PDF_THUMBNAIL_GENERATION_FAILED`

#### Category B: ErrorEvents.RETRY_ATTEMPTED → Specific Types (81 events in Chunk 3)
**Pattern**: Using RETRY_ATTEMPTED when no retry is happening
**Files Affected**: knowledge/handler.py, cache_manager.py, discovery.py, document.py, etc.
**Action**: Replace with actual error type based on what failed
**Examples**:
- Line with knowledge handler error → `ErrorEvents.KNOWLEDGE_SOURCE_ADD_FAILED`
- Line with cache error → `ErrorEvents.A2A_CACHE_ERROR`
- Line with discovery error → `ErrorEvents.A2A_DISCOVERY_FAILED`

#### Category C: ErrorEvents.INTERNAL_ERROR → Specific Types (158 events Chunk 2-3)
**Pattern**: Using generic INTERNAL_ERROR when specific types exist
**Action**: Map to specific error types
**Examples**:
- Memory errors → `ErrorEvents.MEMORY_OPERATION_FAILED`
- LLM errors → `ErrorEvents.LLM_INVOCATION_FAILED`
- Knowledge errors → `ErrorEvents.KNOWLEDGE_SEARCH_FAILED`
- Embeddings → `ErrorEvents.EMBEDDINGS_GENERATION_FAILED`

### PRIORITY 2: Event Type Misuse (51 events)

#### Category D: Misused ServerEvents.SERVER_STARTED (35 events in Chunk 3)
**Pattern**: ServerEvents.SERVER_STARTED used for debug traces (not actually server start)
**Files Affected**: overlord.py (6460, 6477, 2579, 2622, 5462, etc.)
**Action**: REMOVE these events entirely
**Rationale**: These are internal debug traces, not server startup events

#### Category E: Misused SystemEvents.INITIALIZING (10 events in Chunk 5)
**Pattern**: SystemEvents.INITIALIZING used for redundant messages
**Files Affected**: initialization.py
**Action**: REMOVE redundant initialization events
**Rationale**: Already tracked in InitEventFormatter

### PRIORITY 3: Level Adjustments (24 events)

#### Category F: INFO → DEBUG for Granular Steps (16 events)
**Pattern**: Step-by-step execution tracing at INFO level
**Action**: Change level from INFO to DEBUG
**Examples**: NEEDS_REVIEW events flagged for DEBUG level
**Already Done**: 3 events in Chunk 1

#### Category G: Generic Event Type Improvements (24 events)
**Pattern**: Using generic types (OPERATION_COMPLETED, GENERIC_ERROR, etc.)
**Action**: Replace with specific event types or consolidate
**Examples**: OPERATION_COMPLETED → specific operation type

### PRIORITY 4: Description Improvements (32 events)

#### Category H: Missing/Malformed Descriptions (32 events)
**Pattern**: f-string prefixes, CSV extraction errors
**Action**: Verify descriptions in code and update CSV
**Status**: Most are CSV extraction bugs, not code issues

## Implementation Plan

### Phase 1: Code Analysis and Mapping (2 hours)

1. For each file with ErrorEvents.WARNING:
   - Read code context
   - Determine appropriate ErrorEvent subtype
   - Create mapping

2. For each RETRY_ATTEMPTED usage:
   - Verify no retry is happening
   - Determine actual error type
   - Create mapping

3. For INTERNAL_ERROR usage:
   - Categorize by context (memory, llm, embeddings, etc.)
   - Map to specific types
   - Create replacement rules

### Phase 2: Systematic Code Fixes (3-4 hours)

1. **Fix ErrorEvents.WARNING** (33 events)
   - Update event type in source code
   - Ensure level is appropriate
   - Verify descriptions

2. **Fix ErrorEvents.RETRY_ATTEMPTED** (81 events)
   - Replace with specific types based on mapping
   - Update all occurrences
   - Verify no "no retry" events remain

3. **Fix ErrorEvents.INTERNAL_ERROR** (158 events)
   - Apply category-based replacements
   - Verify specific types exist in enum
   - Update all usage sites

4. **Remove misused events** (45 events)
   - Remove ServerEvents.SERVER_STARTED misuse
   - Remove redundant INITIALIZING events
   - Verify no legitimate events removed

5. **Fix level issues** (24 events)
   - Change INFO → DEBUG for granular tracing
   - Verify DEBUG is appropriate level
   - Ensure descriptions still make sense

### Phase 3: Verification and Testing (1-2 hours)

1. Run Python script to regenerate CSV from code
2. Compare new CSV to recommendations
3. Spot-check sample of fixed events with code context
4. Verify no regressions in "OK" events

### Phase 4: Documentation and Reporting (1 hour)

1. Create final comprehensive audit report
2. Document all changes made
3. Generate corrected CSV
4. Create commit with all fixes

## Risk Assessment

**LOW RISK**: 
- Level changes (INFO ↔ DEBUG)
- Removing obviously misused events
- Adding missing descriptions

**MEDIUM RISK**:
- Replacing INTERNAL_ERROR (need to verify specific types exist)
- Replacing RETRY_ATTEMPTED (need correct mapping)

**HIGH RISK**:
- None identified (these are event type/metadata changes, not behavior changes)

## Success Criteria

1. ✓ All 449 problematic events addressed
2. ✓ No new issues introduced in "OK" events
3. ✓ All descriptions verified and improved
4. ✓ Final CSV shows 100% "OK - No issues" or "KEEP" status
5. ✓ Zero unknown/unmapped error types
6. ✓ All code changes compile and pass linting

## Estimated Effort

**Total**: 6-8 hours for complete implementation
- Analysis and mapping: 2 hours
- Code fixes: 3-4 hours
- Verification: 1-2 hours
- Documentation: 1 hour

## Next Steps

1. Proceed with Phase 1 analysis (create complete mappings)
2. Apply Phase 2 fixes systematically
3. Run comprehensive verification
4. Generate final report and corrected CSV
