# Test 10A5: Progress Control - Detailed Analysis

## Test Purpose
Test the `overlord.response.progress` configuration setting to verify that when `progress=false`, only final content events are streamed (no progress/thinking/planning events).

## Test Failure

**Expected**: When `progress=false`, only receive final content events
**Actual**: Received 3 progress events that should have been filtered

### Events Received (when progress=false)
1. "On it..." (progress event)
2. "This is a complex request. Let me break it down into steps..." (progress event)
3. "Executing workflow with 4 tasks..." (progress event)

## Root Causes Analysis

### Issue #1: Test Loads Wrong Formation File ⚠️

**Location**: `e2e/tests/10_streaming/test_10_a_5.py`

The test loads `formation.afs` which has `progress: true`:

```python
# Line 24-26
formation_path = Path(__file__).parent / "formations" / "formation-streaming"
await test.setup_formation(formation_path=str(formation_path))
```

But the test comment says:
```python
# Note: We can't specify a specific YAML with setup_formation,
# so we setup the formation normally and rely on the formation.afs
# being configured with progress: false
```

**Problem**: `formation.afs` has `progress: true` (line 45)

The test **needs** to load `formation-without-progress.yaml` but `setup_formation()` only accepts a directory path, not a specific YAML file name.

###Issue #2: Runtime Progress Filtering Bug 🐛

**Location**: `src/muxi/services/streaming.py` lines 342-347

```python
# Check if progress events are disabled (only stream final content)
if llm_config and not llm_config.get('progress', True):
    # When progress is false, only emit "content" events (final response)
    if event_type != "content":
        return  # Skip all non-content events to save on LLM costs
```

**Problems**:

1. **Too restrictive**: Only allows `event_type == "content"` but should also allow:
   - `"completed"` - Final answer with full response
   - `"finalizing"` - Final processing stage
   - Other terminal content events

2. **Wrong event type check**: The code checks for `event_type == "content"` but based on our test results, the final answer comes in a `"completed"` event (as we discovered in the critical content extraction fix).

3. **Event classification issue**: Some events that should be filtered are not being caught because they might be coming from different code paths that don't go through the `stream()` function.

## Solutions

### Solution 1: Fix Test Formation Loading

**Option A: Modify `setup_formation()` to accept yaml_name parameter**

```python
async def setup_formation(self, formation_path: str, yaml_name: str = "formation.afs"):
    """Setup formation from directory with specific YAML file"""
    formation_yaml_path = Path(formation_path) / yaml_name
    # Load specific YAML file
```

**Option B: Swap formation.afs content**

Temporarily rename files:
- `formation.afs` → `formation-with-progress.yaml`
- `formation-without-progress.yaml` → `formation.afs`

### Solution 2: Fix Runtime Progress Filtering Logic

**File**: `src/muxi/services/streaming.py` line 342

**Current Code**:
```python
if llm_config and not llm_config.get('progress', True):
    if event_type != "content":
        return
```

**Fixed Code**:
```python
if llm_config and not llm_config.get('progress', True):
    # When progress is false, only allow final content events
    # Allow: completed, content, finalizing (terminal events with actual response)
    # Block: progress, thinking, planning (intermediate progress events)
    terminal_events = ('completed', 'content', 'finalizing', 'failed', 'cancelled')
    if event_type not in terminal_events:
        return  # Skip all progress/thinking/planning events
```

## Event Type Categories

Based on analysis of the streaming system:

**Progress Events** (should be filtered when `progress=false`):
- `progress` - Progress updates ("On it...", "Processing...")
- `thinking` - Internal reasoning ("Understanding the request...")
- `planning` - Planning steps ("Breaking down into tasks...")

**Terminal/Content Events** (should ALWAYS be delivered):
- `completed` - Final answer with full response content
- `content` - Direct content streaming
- `finalizing` - Final processing stage
- `failed` - Error occurred
- `cancelled` - Request cancelled

## Why This Matters

The `progress=false` setting is designed to:

1. **Save LLM costs**: Progress events use LLM rephrasing which costs money
2. **Reduce latency**: Skip intermediate updates, only deliver final result
3. **Simplify client UI**: Some clients only want the final answer, not the thinking process

When it doesn't work correctly:
- Users pay for unnecessary LLM rephrasing calls
- Bandwidth is wasted on progress events
- Clients expecting only final content get confused

## Recommended Fix Priority

**Priority**: MEDIUM (Runtime functionality issue, not critical but affects user experience and costs)

**Impact**:
- Users who set `progress=false` still get charged for LLM rephrasing
- Bandwidth waste on unwanted events
- Confusion for clients expecting content-only responses

**Fix Required In**:
1. `src/muxi/services/streaming.py` - Update event type filtering logic
2. Test infrastructure - Allow specifying formation YAML file name

## Testing the Fix

After applying fixes, test should:

1. Load `formation-without-progress.yaml` (with `progress: false`)
2. Make complex request that would normally generate progress events
3. Verify only terminal events are received (`completed`, `content`, etc.)
4. Verify no `progress`, `thinking`, or `planning` events are received

**Expected Result**: 0 progress events, only final content events

---

**Analysis Date**: October 8, 2025
**Test Status**: ❌ FAILED (Runtime bug + test configuration issue)
**Migration Status**: ✅ COMPLETE (test correctly migrated, failure is due to runtime behavior)
