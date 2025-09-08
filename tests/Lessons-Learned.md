# Lessons Learned from MUXI Runtime Testing

## Day 10: Streaming Events Implementation

### Date: 2025-09-08

### Test Area: Streaming & Thinking Visibility

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

#### Remaining Work

- Integration with actual processing pipeline events
- LLM rephrasing implementation (Phase 2)
- Thinking visibility from agent processing
- Progress indicators from workflow decomposition

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