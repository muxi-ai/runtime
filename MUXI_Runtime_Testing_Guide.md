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

## Summary

The key insight is that MUXI Runtime's test suite uses a specific pattern to avoid event loop conflicts:
1. Run formation operations in a thread
2. Use `asyncio.run()` for each async operation
3. This is **test-specific** - production code should use normal async/await patterns

This approach ensures reliable, isolated tests while working around the complexities of testing async code that manages its own event loops.
