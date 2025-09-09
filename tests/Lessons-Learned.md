# Lessons Learned from MUXI Runtime Testing

## Day 10: Streaming Events Implementation

### Date: 2025-01-09 (Updated)

### Test Area: Streaming & Thinking Visibility

#### Phase 2: Workflow Streaming Integration

1. **Workflow Streaming Gaps**
   - **Problem**: Streaming events stopped when workflow decomposition triggered
   - **Root Cause**: `_process_with_workflow` returned final result directly without streaming
   - **Solution**: Check if streaming enabled and emit events during workflow execution
   - **Impact**: Full streaming support for complex requests with task decomposition

2. **Message Format Exposure**
   - **Problem**: Event 3 showed raw message format "=== CURRENT REQUEST ==="
   - **Solution**: Extract actual user message before emitting streaming events
   ```python
   if "=== CURRENT REQUEST ===" in message:
       _, _, user_message = message.partition("\n")
       user_message = user_message.strip()
   ```
   - **Lesson**: Always sanitize internal formats before user-facing emissions

3. **Final Response Missing**
   - **Problem**: Stream ended without showing actual answer to user's question
   - **Root Cause**: "completed" event terminated stream before content delivered
   - **Solution**: Include actual response content in "completed" event
   - **Impact**: Users now see the final answer, not just progress updates

4. **Event Verbosity Reduction**
   - **Problem**: 11-12 events too verbose for simple requests
   - **Solution**: Commented out redundant events (3, 5, 7, 10)
   - **Current Flow**: 6-7 meaningful events (acknowledgment → thinking → planning → workflow → synthesis → completed)
   - **Optimization**: skip_rephrase flag for instant events saves LLM tokens

5. **Test Hanging Issues**
   - **Problem**: Tests wouldn't shut down properly after completion
   - **Solution**: Use `os._exit()` in finally block of main
   ```python
   finally:
       if formation:
           await formation.kill_overlord()
           formation.shutdown()
       os._exit(0 if success else 1)
   ```
   - **Impact**: All 6 tests now exit cleanly without hanging

#### Critical Debugging Lessons

1. **Context Propagation in Background Tasks**
   - **Problem**: RequestContext lost when using `asyncio.create_task()` - contextvars don't auto-propagate
   - **Root Cause**: Import path error (`..observability.context` vs `.observability.context`) and attribute mismatch (`request_context.request_id` vs `request_context.id`)
   - **Solution**: Explicitly set context in background task:
   ```python
   async def delayed_process():
       from ...services.observability.context import set_request_context, RequestContext
       request_context = RequestContext(id=request_id, user_id=user_id, ...)
       set_request_context(request_context)
   ```
   - **Impact**: Fixed both streaming AND observability event emission

2. **Generator Function Constraints**
   - **Problem**: SyntaxError when mixing `yield` and `return` with value in async generator
   - **Misconception**: Assumed Python 3 doesn't allow both (it does, but not with return values)
   - **Solution**: Separate generator logic into `_create_stream_generator()` method
   - **Lesson**: Don't make assumptions about language limitations - test first

3. **Persona LLM Hanging Issue**
   - **Problem**: Persona application hanging when called with streaming enabled
   - **Root Cause**: LLM returning async generator instead of complete response
   - **Solution**: Force `stream=False` in all persona LLM calls
   - **Impact**: Prevents request hanging, ensures proper response formatting

4. **Import Path Resolution**
   - **Problem**: ModuleNotFoundError for `muxi.observability` 
   - **Root Cause**: Incorrect relative import (`from ...observability import` vs `from ... import observability`)
   - **Solution**: Fixed import paths in 4 files (http_sse.py, streamable.py, extractor.py, processor.py)
   - **Lesson**: Always verify import paths before assuming context issues

5. **Attribute Access Errors**
   - **Problem**: AttributeError for `overlord.persona`
   - **Solution**: Use `getattr(self, '_default_persona', None)` instead
   - **Lesson**: Check actual attribute names in codebase before accessing

#### Key Lessons

1. **Subscription Timing Coordination**
   - **Problem**: Events emitted before subscription established
   - **Solution**: Add 1-second delay before processing: `await asyncio.sleep(1.0)`
   - **Impact**: Ensures subscription ready before events start flowing

2. **Event Format Standardization**
   - **Problem**: Tests expected string chunks but streaming returns dict events
   - **Solution**: Standardized dict format with metadata:
   ```python
   {
       'request_id': 'req_xxx',
       'type': 'progress',
       'content': 'Event message',
       'timestamp': 1234567890.123
   }
   ```
   - **Impact**: Consistent event handling across all tests

3. **Stream Termination Pattern**
   - **Problem**: Subscriptions hanging indefinitely
   - **Solution**: Emit `completed` event and disable streaming:
   ```python
   if event.get("type") == "completed":
       self.disable_streaming(request_id)
       return
   ```
   - **Impact**: Clean subscription termination

4. **Debugging Approach**
   - **Lesson**: Use surgical debugging rather than refactoring
   - **Process**: Add debug prints → trace execution → identify exact failure point
   - **Example**: "WHERE does it fail?" led to discovering import and attribute issues

#### Technical Achievements

- ✅ All 9 streaming event types working (thinking, planning, progress, content, completed)
- ✅ Context propagation fixed for both streaming and observability
- ✅ Import errors resolved across multiple modules
- ✅ Persona application no longer hangs
- ✅ All 5 tests in 10A group passing

#### Key Improvements Implemented

- ✅ Workflow streaming integration complete
- ✅ LLM rephrasing with skip_rephrase optimization
- ✅ Message extraction for clean event content
- ✅ Randomized acknowledgment messages (10 variations)
- ✅ Terminal event handling (completed/failed/cancelled)
- ✅ Test suite with 6 comprehensive tests including clarification flow

#### Remaining Work

- Async request streaming support (webhooks)
- Streaming token-by-token for rephrasing (currently waits for full response)
- Model-specific complexity thresholds for workflow triggers
- Adaptive timeouts based on model response times

---

## Previous Days

### Day 9: Async Operations
- Webhook delivery with retry logic
- Async threshold configuration
- Conflict resolution between async and streaming modes

### Day 8: Clarification System
- Multi-turn clarification support
- Context preservation across clarifications
- Request ID hierarchy for tracking

### Day 7: Workflow Automation
- Task decomposition for complex requests
- Approval workflows for high-stakes operations
- Complexity scoring and routing

### Day 6: Knowledge Management
- Domain knowledge isolation
- Agent-specific knowledge bases
- Knowledge validation and updates

### Day 5: File Generation
- Secure file creation with validation
- Multi-format support (PDF, CSV, JSON, etc.)
- Directory traversal protection

### Day 4: MCP Integration
- Tool discovery and registration
- Security filtering for code execution
- Multi-server coordination

### Day 3: Multimodal Processing
- Large file handling (>100MB)
- Intelligent chunking strategies
- Format-specific processing pipelines

### Day 2: Memory Systems
- Three-tier memory architecture
- Vector search integration
- Multi-user isolation

### Day 1: Foundation
- Formation loading and validation
- Agent initialization
- Basic chat functionality

---

## Common Patterns

### Testing Best Practices
1. **No Mocks**: Test against real services only
2. **Focus Testing**: Test the specific feature, not unrelated capabilities
3. **Event-Driven**: Use event streams for observability
4. **Timeout Protection**: Always use timeouts for async operations
5. **Clean State**: Proper cleanup between tests

### Architecture Patterns
1. **Formation-First**: Configuration drives behavior
2. **Fail Fast**: Critical errors stop execution immediately
3. **Graceful Degradation**: Optional features fail silently
4. **Event Streaming**: Real-time visibility into processing
5. **Context Preservation**: Request context flows through all layers

### Security Principles
1. **Input Validation**: Always validate user inputs
2. **Path Traversal Protection**: Absolute paths only
3. **Secret Management**: Never log or expose secrets
4. **User Isolation**: Multi-user data separation
5. **Code Filtering**: MCP code execution safety

---

## Future Considerations

1. **Performance Optimization**
   - Cache model instances
   - Optimize vector search
   - Reduce context switching overhead

2. **Enhanced Streaming**
   - Binary streaming for large files
   - Compression for network efficiency
   - Adaptive chunking based on client bandwidth

3. **Improved Observability**
   - Distributed tracing integration
   - Performance metrics collection
   - Error aggregation and reporting

4. **Advanced Features**
   - Model capability validation
   - Sophisticated fallback chains
   - Configuration migration tools