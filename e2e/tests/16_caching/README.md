# Test Area 16: LLM Response Caching

Tests for the OneLLM-powered intelligent response caching system.

## Overview

This test area validates that LLM response caching works correctly with different configurations:
- Default enabled caching (production settings)
- Explicitly disabled caching (development mode)
- Custom cache parameters (tuned settings)

## Test Groups

### Group 16A: Cache Configuration

Tests cache initialization and configuration handling.

#### Test 16A1: Cache Enabled by Default
**File**: `test_16a1_cache_enabled.py`
**Formation**: `formations/formation-cache-enabled/`

Tests that:
- Formation loads successfully with default caching
- Caching doesn't break normal operation
- System responds correctly to multiple similar requests

**Expected Results**: All tests pass, system works normally with caching enabled.

#### Test 16A2: Cache Explicitly Disabled
**File**: `test_16a2_cache_disabled.py`
**Formation**: `formations/formation-cache-disabled/`

Tests that:
- Caching can be disabled via `enabled: false`
- System works correctly without caching
- Multiple requests work as expected

**Expected Results**: All tests pass, system works normally with caching disabled.

#### Test 16A3: Custom Cache Parameters
**File**: `test_16a3_cache_custom.py`
**Formation**: `formations/formation-cache-custom/`

Tests that:
- Custom cache parameters are loaded correctly
- Formation starts with custom settings
- System works with tuned cache parameters:
  - `max_entries: 100` (smaller cache)
  - `p: 0.90` (looser similarity matching)
  - `stream_chunk_strategy: "words"`
  - `stream_chunk_length: 5`
  - `ttl: 60` (1 minute)

**Expected Results**: All tests pass, custom parameters are applied correctly.

## Running Tests

### Run all caching tests:
```bash
cd /Users/ran/Projects/muxi/code/runtime
python e2e/tests/16_caching/test_16a1_cache_enabled.py
python e2e/tests/16_caching/test_16a2_cache_disabled.py
python e2e/tests/16_caching/test_16a3_cache_custom.py
```

### Or run via test script:
```bash
bash e2e/scripts/run-tests.sh 16_caching
```

## Test Formations

All test formations use:
- `openai/gpt-4o-mini` for cost efficiency
- Simple single agent setup
- Minimal buffer memory (size: 5)
- No vector search (for speed)

### Formation: cache-enabled
Default caching settings (production configuration).

### Formation: cache-disabled
Caching explicitly disabled for development mode testing.

### Formation: cache-custom
Custom cache parameters for testing configuration flexibility.

## Implementation Details

### What We Test

1. **Configuration Loading**: Verify cache config is parsed correctly
2. **Initialization**: Ensure OneLLM cache initializes without errors
3. **Operation**: Validate system works with caching enabled/disabled
4. **Parameter Application**: Confirm custom parameters are used

### What We Don't Test

1. **Actual Cache Hits**: OneLLM handles caching internally, we can't easily verify from outside
2. **Performance Gains**: Would require load testing infrastructure
3. **TTL Expiration**: Would require waiting (60s minimum)
4. **Semantic Matching**: Would require complex similarity analysis

### Limitations

- Cache behavior is internal to OneLLM
- We verify configuration and operation, not actual cache effectiveness
- Tests focus on "doesn't break" rather than "improves performance"

## Success Criteria

All tests should pass, demonstrating:
- ✅ Default caching works transparently
- ✅ Caching can be disabled for development
- ✅ Custom parameters are applied correctly
- ✅ No breaking changes to existing functionality

## Related Documentation

- [LLM Caching Documentation](../../../docs/features/llm-caching.md)
- [Formation Schema](../../../schemas/formation/README.md#llm-response-caching-settings)
- [Implementation Summary](../../../docs/LLM_CACHING_IMPLEMENTATION.md)
