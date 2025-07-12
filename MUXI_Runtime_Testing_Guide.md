# MUXI Runtime Testing Guide

## Overview

This guide documents key learnings and patterns discovered while implementing the comprehensive test suite for MUXI Runtime. It covers practical solutions to common issues and best practices for writing reliable tests.

## Key Testing Patterns

### 1. Formation Loading and Event Loop Management

**Problem**: MUXI Runtime uses asyncio internally, which can conflict with pytest-asyncio's event loop when loading formations.

**Solution**: Use ThreadPoolExecutor to isolate formation loading in a separate thread:

```python
from concurrent.futures import ThreadPoolExecutor

def test_formation_loading():
    def run_test():
        formation = Formation()
        formation.load("path/to/formation.yaml")
        overlord = formation.start_overlord()

        # Use asyncio.run() for each chat call
        response = asyncio.run(overlord.chat("Hello"))

        formation.stop_overlord()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
```

**Why `asyncio.run()` instead of `await`?**
- When running in a thread (not an async context), you need `asyncio.run()` to create a new event loop for each async call
- `await` only works inside an `async def` function
- This is a test-specific pattern to avoid event loop conflicts

### 2. Formation Configuration Requirements

**Problem**: Formations require specific fields to pass validation.

**Required fields for any formation:**
```yaml
schema: "1.0.0"  # Not schema_version
id: "unique-formation-id"
description: "What this formation does"

llm:
  api_keys:
    provider: "key-or-secret-reference"
  models:
    - text: "provider/model-name"  # Must specify capability (text, embedding, etc.)

agents:
  - id: "agent-id"
    name: "Agent Name"
    description: "What this agent does"  # Required field
    model: "provider/model-name"
    specialty: "general"
    system_message: "Agent instructions"
```

### 3. Memory Configuration Patterns

**Buffer Memory Only:**
```yaml
memory:
  buffer:
    size: 10  # Number of messages to keep
  working:
    max_memory_mb: 10  # Even if not using working memory, may need this
```

**SQLite Persistence:**
```yaml
memory:
  persistent:
    provider: "sqlite"
    config:
      database_url: "sqlite:///path/to/db.db"
```

**PostgreSQL Multi-User:**
```yaml
memory:
  persistent:
    provider: "postgresql"
    config:
      connection_string: "postgresql://user:pass@host/db"
```

### 4. Testing Memory Systems

**Buffer Overflow Testing:**
```python
# Send more messages than buffer size
for i in range(buffer_size + 5):
    asyncio.run(overlord.chat(f"Message {i}"))

# Verify old messages are forgotten (FIFO)
response = asyncio.run(overlord.chat("What was message 0?"))
assert "message 0" not in response.lower()
```

**Multi-User Isolation:**
```python
# Always specify user_id for multi-user formations
asyncio.run(overlord.chat("I'm Alice", user_id="user1"))
asyncio.run(overlord.chat("I'm Bob", user_id="user2"))

# Verify isolation
response1 = asyncio.run(overlord.chat("What's my name?", user_id="user1"))
assert "alice" in response1.lower() and "bob" not in response1.lower()
```

### 5. Real LLM Configuration for Testing

**IMPORTANT: Always use real LLM providers for testing, not mocks!**

Mock providers don't test actual integration points and miss critical behaviors like:
- Real embedding quality for vector search
- Actual API error handling
- True performance characteristics
- Authentication and rate limiting

**Correct configuration:**
```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"  # Use real API keys from secrets
  models:
    - text: "openai/gpt-4o-mini"           # Real text model
    - embedding: "openai/text-embedding-3-small"  # Real embedding model
```

**For vector search testing:**
- Real embeddings are crucial for testing relevance
- Mock embeddings will give poor search results (30-50% relevance)
- Real embeddings with normalization achieve 100% relevance

### 6. Common Pitfalls and Solutions

**Pitfall 1: Missing agent description**
```yaml
# ❌ Wrong
agents:
  - id: "agent"
    name: "Agent"
    model: "test/mock"

# ✅ Correct
agents:
  - id: "agent"
    name: "Agent"
    description: "Test agent"  # Required!
    model: "test/mock"
```

**Pitfall 2: Using schema_version instead of schema**
```yaml
# ❌ Wrong
schema_version: "1.0.0"

# ✅ Correct
schema: "1.0.0"
```

**Pitfall 3: Model without capabilities**
```yaml
# ❌ Wrong
models:
  - name: "test/mock"
    provider: "test"

# ✅ Correct
models:
  - text: "test/mock"  # Specify capability
```

### 7. Testing Async Operations

For operations that need cleanup:
```python
def test_with_cleanup():
    def run_test():
        formation = Formation()
        formation.load("formation.yaml")
        overlord = formation.start_overlord()

        try:
            # Your test code here
            response = asyncio.run(overlord.chat("Test"))
            assert response is not None
        finally:
            # Always cleanup
            formation.stop_overlord()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
```

### 8. Testing Persistence

When testing persistence across restarts:
```python
def test_persistence():
    def run_test():
        formation = Formation()
        formation.load("formation.yaml")

        # First session
        overlord = formation.start_overlord()
        asyncio.run(overlord.chat("Remember this"))
        formation.stop_overlord()

        # Second session - same formation
        overlord = formation.start_overlord()
        response = asyncio.run(overlord.chat("What did I say?"))
        assert "remember" in response.lower()
        formation.stop_overlord()
```

### 9. External Service Dependencies

**IMPORTANT: Use real external services, not mocks!**

Required services for comprehensive testing:

1. **FAISSx Servers** (for vector search):
   - Port 45678: FAISSx without authentication
   - Port 65432: FAISSx with authentication
   - Both require real tenant IDs from secrets

2. **PostgreSQL Database** (for multi-user tests):
   - Real instance with proper user isolation
   - Test with multiple concurrent users

3. **A2A Registry Server** (for agent communication):
   - Real registry for cross-formation communication

Always document these requirements in your test docstrings.

### 10. Performance Considerations

- Use ThreadPoolExecutor with `max_workers=1` to avoid parallel formation conflicts
- Each `asyncio.run()` creates a new event loop - this is intentional for test isolation
- For production code, use proper async patterns with `await`

## Important Test Considerations

### Memory Buffer Behavior
When testing buffer memory, be aware that:
- LLMs have their own context window that may retain information beyond the buffer
- The buffer controls what's sent to the LLM, but the LLM may remember from its own context
- For true buffer overflow testing, you may need to:
  - Send enough messages to exceed both buffer AND LLM context
  - Or test the actual buffer contents rather than LLM responses
  - Or use more specific queries that test exact message recall

### Test Timeouts
Some tests may take longer due to:
- Multiple LLM API calls
- MCP server initialization
- Database operations

Consider using longer timeouts for complex tests (especially with real LLMs).

## Advanced Memory Testing Patterns

### Buffer Memory Modes

MUXI supports two buffer memory modes that behave differently:

**Local Buffer Mode:**
```yaml
memory:
  buffer:
    enabled: true
    size: 10
    vector_search: true
    mode: "local"  # In-memory FAISS index
```

**Remote Buffer Mode:**
```yaml
memory:
  buffer:
    enabled: true
    size: 10
    vector_search: true
    mode: "remote"
    max_memory_mb: 512  # Required for remote mode
    remote:
      url: "tcp://localhost:45678"
      tenant: "${{ secrets.FAISSX_TENANT_ID }}"
```

### Vector Search Optimization

For optimal vector search results:

1. **Always use real embeddings** (not mocks)
2. **Embedding normalization is built into ShortTermMemory**
3. **No special models needed** - standard OpenAI embeddings work great

Example of testing vector search relevance:
```python
# Add diverse content
asyncio.run(overlord.chat("I love machine learning"))
asyncio.run(overlord.chat("JavaScript is for web dev"))
asyncio.run(overlord.chat("Databases need good design"))

# Search for ML content
response = asyncio.run(overlord.chat("What have I said about AI?"))
# Should find the ML-related message with high relevance
```

### Multi-User FAISSx Testing

When testing multi-user vector search:
```python
# Each user gets isolated vector space
asyncio.run(overlord.chat("I like Python", user_id="user1"))
asyncio.run(overlord.chat("I like Java", user_id="user2"))

# Searches are user-specific
response1 = asyncio.run(overlord.chat("What language do I like?", user_id="user1"))
assert "python" in response1.lower() and "java" not in response1.lower()
```

### Secrets Management

Always use encrypted secrets for API keys and credentials:
```yaml
llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
memory:
  buffer:
    remote:
      tenant: "${{ secrets.FAISSX_TENANT_ID }}"
```

Never hardcode credentials in test files!

## Advanced Multimodal Testing Patterns

### 11. Multimodal File Processing (Day 3 Insights)

Based on comprehensive testing of 36 multimodal scenarios, here are key patterns for testing multimodal capabilities:

**Provider-Agnostic Testing:**
```python
def test_multimodal_processing():
    def run_test():
        formation = Formation()
        formation.load("test-formations/formation-multimodal")
        overlord = formation.start_overlord()
        
        try:
            # Test with proper file structure
            file_path = Path("test-docs/sample.pdf")
            with open(file_path, "rb") as f:
                content = f.read()
            
            response = asyncio.run(overlord.chat(
                user_id="test_user",
                message="Analyze this document", 
                files=[{
                    "filename": file_path.name,
                    "content": content,
                    "content_type": "application/pdf",  # Critical: correct MIME type
                    "size": len(content),
                }],
            ))
            
            # Handle multiple response types
            if isinstance(response, dict) and "request_id" in response:
                print("✅ Async processing triggered")
                # Wait for webhook or check status
            elif hasattr(response, '__aiter__'):
                # Streaming response
                full_response = ""
                async for chunk in response:
                    full_response += chunk
                assert len(full_response) > 100
            else:
                # Direct response
                assert len(response) > 50
                
        finally:
            formation.stop_overlord()
```

**Provider Selection Patterns:**
- **OpenAI**: Best for audio transcription (Whisper), general text/vision
- **Google Gemini**: Excellent for video processing, complex visual analysis
- **Anthropic Claude**: Strong for document analysis, cross-modal reasoning

**File Size Considerations:**
```python
# Know provider limits
PROVIDER_LIMITS = {
    'openai': {'audio': 25_000_000},  # 25MB Whisper limit
    'google': {'video': 200_000_000}, # ~200MB practical limit
    'anthropic': {'image': 30_000_000} # ~30MB estimated
}

def test_large_file_handling():
    file_size = len(content)
    if file_size > PROVIDER_LIMITS.get(provider, {}).get(content_type, 0):
        # Expect chunking or appropriate error
        assert "chunk" in response.lower() or "limit" in response.lower()
```

### 12. Content Type and MIME Type Importance

**Critical for video processing:**
```python
# ❌ Wrong - will cause processing failures
files=[{
    "filename": "demo.mov",
    "content": video_content,
    "content_type": "video/mp4",  # Wrong MIME type for .mov
}]

# ✅ Correct - matches file format
files=[{
    "filename": "demo.mov", 
    "content": video_content,
    "content_type": "video/quicktime",  # Correct for .mov files
}]
```

### 13. Async Webhook Testing

**For large file processing:**
```python
def test_async_webhook_delivery():
    def run_test():
        # Large file that triggers async processing
        response = asyncio.run(overlord.chat(
            user_id="test_user",
            message="Process this large video",
            files=[large_video_file],
        ))

        # Should return task info for async processing
        assert isinstance(response, dict)
        assert "request_id" in response
        
        # For webhook testing, you'd need to mock or run webhook receiver
        
    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_test)
        future.result()
```

## Latest Testing Patterns (July 2025)

### 14. Chat Flow Testing with Real Services

**New Recommended Approach:** Focus on end-to-end chat flow testing with real LLM services instead of unit testing individual components.

**Key Principles:**
1. **No Mocks**: Always use real OpenAI, Anthropic, or other LLM providers
2. **Chat Flow Validation**: Test through `overlord.chat()` interface
3. **Detailed Response Documentation**: Capture user prompts and actual overlord responses
4. **Service Integration**: Validate MCP servers, memory systems, and agent routing

**Modern Test Structure:**
```python
async def test_agent_communication():
    """Test Group 1B: Agent Communication with real LLM validation"""
    formation = Formation()
    await formation.load("test-formations/formation-multi-agent/")
    overlord = await formation.start_overlord()
    
    # Test 1: Math Query Routing
    response = await overlord.chat("Calculate 2+2", user_id="test_user", stream=False)
    response_text = response.content if hasattr(response, 'content') else str(response)
    assert "4" in response_text  # Validate actual LLM response
    
    # Test 2: Research Query Routing  
    response = await overlord.chat(
        "What are the latest trends in renewable energy?", 
        user_id="test_user", 
        stream=False
    )
    response_text = response.content if hasattr(response, 'content') else str(response)
    assert len(response_text) > 50  # Substantive research response
    
    await formation.stop_overlord()
```

### 15. Test Report Generation

**Create detailed test reports** documenting user interactions:

```markdown
# Test Group 1B: Basic Agent Communication - Test Report

## Chat Interactions:

### ✅ Test 1B1: Single Agent Response
- 👤 **User**: "What can you help me with?"
- 🤖 **Overlord**: Successfully responded with helpful information
- **Validation**: Response contains help-related keywords

### ✅ Test 1B2: Agent Routing Validation  
- 👤 **User**: "Calculate 2+2"
- 🤖 **Overlord**: "2 + 2 equals 4."
- **Validation**: Math query properly routed to appropriate agent

## Technical Achievements:
- Agent specialization (Code Assistant, Research Specialist, General Assistant)
- Memory integration with conversation context
- Async processing for complex queries
```

### 16. Formation Testing Best Practices

**Directory vs File Formations:**
```python
# Test both formation types
single_agent_formation = "test-formations/formation-basic/"  # Directory
multi_agent_formation = "test-formations/formation-multi-agent/"  # Directory  
flattened_formation = "test-formations/formation-basic/formation-flattened.yaml"  # File
```

**Validation Testing:**
```python
# Test comprehensive error scenarios
invalid_formations = [
    "test-formations/invalid-formations/invalid-syntax.yaml",
    "test-formations/invalid-formations/invalid-not-yaml.txt", 
    "test-formations/invalid-formations/invalid-missing-keys.yaml",
    "test-formations/invalid-formations/invalid-schema.yaml",
    "test-formations/invalid-formations/invalid-values.yaml",
    "test-formations/invalid-formations/invalid-empty.yaml",
    "test-formations/invalid-formations/invalid-no-agents/",
    "test-formations/does-not-exist/"
]

for invalid_path in invalid_formations:
    with pytest.raises(Exception):  # ConfigurationValidationError, etc.
        await formation.load(invalid_path)
```

### 17. Memory Configuration Testing

**Remote vs Local Memory Validation:**
```python
# Remote memory requires specific fields
async def test_remote_memory_validation():
    formation = Formation()
    
    # Should fail - missing URL
    with pytest.raises(ConfigurationValidationError):
        await formation.load("test-formations/invalid-remote-no-url.yaml")
    
    # Should fail - missing tenant  
    with pytest.raises(ConfigurationValidationError):
        await formation.load("test-formations/invalid-remote-no-tenant.yaml")
        
    # Should fail - uses "auto" instead of explicit MB
    with pytest.raises(ConfigurationValidationError):
        await formation.load("test-formations/invalid-remote-auto-memory.yaml")
    
    # Should pass - valid remote config
    await formation.load("test-formations/valid-remote-memory.yaml")
```

### 18. Real Service Integration Requirements

**Required External Services:**
- **OpenAI API**: Real GPT-4o-mini and GPT-4o models for agent responses
- **MCP Servers**: Filesystem MCP server (npm package required)
- **Memory Systems**: Real buffer memory and long-term memory storage
- **Observability**: Complete event logging and request tracking

**Never Use Mocks For:**
- LLM responses (use real OpenAI, Anthropic, etc.)
- Agent routing decisions
- Memory storage and retrieval
- MCP tool discovery and invocation
- Formation loading and validation

This approach reveals real integration issues and validates actual user experience rather than mocked behavior.
