# Streaming and Workflow Investigation Findings

## Latest Update: 2025-01-09

### What We Accomplished Today

1. **Fixed Workflow Streaming**: 
   - Workflow execution now properly emits streaming events
   - Added streaming support in `_process_with_workflow` method
   - Final response content is now included in the "completed" event

2. **Reduced Event Verbosity**:
   - Commented out 4 redundant events (Events 3, 5, 7, 10)
   - Reduced event flow from 11-12 events to ~6-7 meaningful events
   - Events removed:
     - Event 3: Duplicate thinking (overlord.py:5910-5917)
     - Event 5: Duplicate planning (decomposer.py:209-218) 
     - Event 7: Task start too granular (executor.py:689-698)
     - Event 10: Uninformative finalizing (overlord.py:7948-7954, 6740-6750)

3. **Improved User Experience**:
   - Event 1 now shows randomized acknowledgment messages for variety
   - Added `skip_rephrase` flag to prevent LLM rephrasing of certain events
   - Final content events ("completed", "content", "finalizing") bypass rephrasing
   - Fixed message extraction to avoid showing internal formatting

4. **Fixed Critical Issues**:
   - Streaming manager now terminates on "completed", "failed", or "cancelled" events
   - Fixed import error in decomposer.py (kept import, commented only the call)
   - Fixed line length linting issue in streaming.py
   - Fixed test hanging issue with `os._exit()` in finally block

5. **Test Suite Updates**:
   - Updated all 5 existing 10a tests with proper shutdown pattern
   - Created new test_10a6_clarification_streaming.py for clarification flow
   - All tests now properly exit without hanging

### Current Event Flow (After Optimization)

1. **Event 1**: "Request received, processing..." (instant, randomized, no rephrasing)
2. **Event 2**: Initial thinking (rephrased)
3. **Event 4**: Workflow planning (rephrased)
4. **Event 6**: Workflow start (rephrased)
5. **Event 8**: Task planning (if present, rephrased)
6. **Event 9**: Synthesis (rephrased)
7. **Event 11**: Completed with actual answer (not rephrased, contains full response)

### Key Technical Implementation Details

#### Message Extraction (overlord.py:5189-5214)
- Extract actual user message from formatted request to avoid exposing "=== CURRENT REQUEST ==="
- Only runs when streaming is enabled (optimization)
- Uses message.partition() to cleanly extract user content

#### Streaming Event Emission Pattern
```python
if stream and self.streaming_manager:
    await self.streaming_manager.emit(EventType.PROGRESS, {
        "stage": "stage_name",
        "message": "User-friendly message",
        "metadata": {"skip_rephrase": True}  # Optional
    })
```

#### Terminal Event Handling (streaming.py:86-91)
- Stream disconnects on: "completed", "failed", "cancelled"
- "completed" event includes actual response content
- "finalizing" event used for progress before final content

#### Skip Rephrasing Logic (streaming.py:279-281)
- Events with metadata["skip_rephrase"] = True bypass LLM rephrasing
- Applied to Event 1 (acknowledgment) and final content events
- Saves tokens and reduces latency

#### Randomized Acknowledgments (chat_orchestrator.py:80-91)
- 10 different phrases for variety
- Selected randomly for each request
- Emitted with skip_rephrase=True

### Files Modified

- `/src/muxi/formation/overlord/overlord.py` - Main streaming fixes
- `/src/muxi/formation/overlord/chat_orchestrator.py` - Randomized Event 1
- `/src/muxi/services/streaming.py` - Terminal events, skip_rephrase support
- `/src/muxi/formation/workflow/decomposer.py` - Fixed import, commented Event 5
- `/src/muxi/formation/workflow/executor.py` - Commented Event 7
- All test files in `/tests/e2e/10_streaming/` - Fixed hanging issue

### TODO for Tomorrow

1. **Run all 10a tests** to ensure they pass:
   - test_10a1_basic_streaming.py
   - test_10a2_complex_streaming.py
   - test_10a3_rephrasing_quality.py
   - test_10a4_streaming_control.py
   - test_10a5_progress_control.py
   - test_10a6_clarification_streaming.py (new)

2. **Move to Step 2**: Implement async request streaming support
   - Currently only sync requests support streaming
   - Need to add streaming support for async/webhook requests
   - See "Proposed Solutions" section below

### Known Issues to Address

1. **gpt-5-nano timeout behavior**:
   - Model takes longer to respond (30+ seconds)
   - Creates perception of hanging
   - Solution: Extended timeout tests work, consider adaptive timeouts

2. **Workflow trigger sensitivity**:
   - gpt-5-nano generates higher complexity scores
   - Triggers workflows for simple questions
   - Solution: Model-specific complexity thresholds

### Future Enhancement (Documented as TODO)

- Stream LLM rephrasing tokens as they arrive instead of waiting for complete response
- Would make system feel more responsive for longer messages
- Added as TODO comment in streaming.py:147-152

---

## Original Investigation Date: 2025-09-09

## Executive Summary
Streaming events stop being emitted when workflow execution is triggered, regardless of sync/async mode. This affects user experience as they lose visibility into what the system is doing during complex task decomposition and execution.

## Key Findings

### 1. Root Cause Identified
- **Issue**: Streaming events stop when workflow execution is triggered
- **NOT the issue**: Model choice (gpt-5-nano vs gpt-4o-mini)
- **NOT the issue**: Async vs sync mode
- **Actual issue**: Workflow execution itself breaks streaming

### 2. Evidence
- Test with gpt-4o-mini: Gets all 9 streaming events (no workflow triggered)
- Test with gpt-5-nano: Gets only 3 events (workflow triggered due to high complexity score)
- Test with hardcoded complexity=2.0: Gets all 9 events (workflow bypassed)
- When workflow triggers: Streaming stops, only initial events received

### 3. Model Behavior Differences
- **gpt-5-nano (reasoning model)**:
  - Generates higher complexity scores (5.0 for simple questions)
  - More likely to trigger workflow decomposition
  - Better at task analysis but triggers unnecessary workflows

- **gpt-4o-mini**:
  - Generates lower complexity scores (2.0 for same questions)
  - Less likely to trigger workflows
  - Direct agent routing works, streaming continues

### 4. Configuration Issues
- `use_async=False` parameter IS respected (workflow runs synchronously when set)
- Webhook responses lack request_id for proper tracking (when async is used)
- Estimation is too high for simple questions (30+ seconds)

## Technical Details

### Streaming Architecture
```
User Request → Overlord → Complexity Analysis →
  ├─ Low Complexity (< threshold) → Direct Agent → ✅ Streaming Works
  └─ High Complexity (>= threshold) → Workflow Execution → ❌ Streaming Breaks
```

### Problem Areas in Code

1. **Workflow Execution** (`overlord.py`)
   - `_process_with_workflow()` doesn't maintain streaming context
   - Returns final result directly instead of continuing stream
   - Missing streaming event emissions during workflow

2. **Complexity Analysis** (`request_analyzer.py`)
   - gpt-5-nano consistently overestimates complexity
   - No streaming events during analysis phase
   - Threshold (4.0) may be too low for reasoning models

3. **Async Handling** (`chat_orchestrator.py`)
   - Webhook responses don't include request_id
   - Stream generation pattern differs from sync

## Proposed Solutions

### 1. Fix Workflow Streaming (Priority 1) ✅ COMPLETED
- Add streaming event emissions in `_process_with_workflow()`
- Maintain streaming context through workflow execution
- Emit progress events during task execution

### 2. Support Async Streaming (Priority 2) - TOMORROW
- Include request_id in webhook responses
- Implement SSE/WebSocket for async streaming
- Maintain event buffer for async retrieval

### 3. Tune Complexity Analysis (Priority 3)
- Adjust thresholds based on model type
- Add model-specific complexity adjustments
- Consider bypass for simple questions

### 4. Add Streaming Configuration
- Allow disabling workflow for streaming-critical paths
- Add streaming priority mode
- Configure event verbosity levels

## Test Results

### Working Scenario (gpt-4o-mini)
```
✅ 9 streaming events received
✅ Complete response delivered
✅ User sees progress throughout
```

### Broken Scenario (gpt-5-nano with workflow)
```
❌ Only 3 streaming events received
❌ Long silence during workflow execution
✅ Final response eventually delivered (after delay)
```

### Fixed with Hardcoded Complexity
```
✅ 9 streaming events when complexity=2.0
✅ Workflow bypassed
✅ Streaming continues normally
```

## Recommendations

1. **Immediate**: Fix workflow streaming to maintain events
2. **Short-term**: Add model-specific complexity tuning
3. **Long-term**: Implement proper async streaming infrastructure
4. **Configuration**: Add streaming mode flags to control behavior

## Files to Review

- `/src/muxi/formation/overlord/overlord.py` - Main orchestration
- `/src/muxi/formation/overlord/chat_orchestrator.py` - Stream generation
- `/src/muxi/formation/workflow/executor.py` - Workflow execution
- `/src/muxi/services/streaming.py` - Streaming service
- `/src/muxi/formation/overlord/request_analyzer.py` - Complexity scoring

## Next Steps

1. ✅ Implement streaming events in workflow execution (COMPLETED)
2. Test with various complexity levels (TOMORROW)
3. Add configuration for streaming behavior (FUTURE)
4. Document streaming architecture (FUTURE)