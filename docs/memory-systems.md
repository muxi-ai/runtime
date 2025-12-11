# MUXI Runtime Memory Systems

## Overview

MUXI Runtime provides a sophisticated multi-tier memory architecture designed for AI agents to maintain context, learn from interactions, and provide personalized experiences. The memory system supports both single-user and multi-user deployments with seamless scaling.

## Architecture

### Three-Tier Memory System

```
┌────────────────────────────────────────────────────┐
│                    Buffer Memory                   │
│  (Working, Fast Access, Recent Context)         │
└────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────┐
│                   Working Memory                   │
│  (Medium-term, Vector Search, FIFO Management)     │
└────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────┐
│                  Persistent Memory                 │
│  (Long-term, Database-backed, Multi-user Support)  │
└────────────────────────────────────────────────────┘
```

### 1. Buffer Memory
- **Purpose**: Immediate conversation context
- **Capacity**: Configurable (typically 10-50 messages)
- **Features**:
  - Fast in-memory storage
  - Optional vector search capabilities
  - Automatic overflow to working memory
  - Support for both local and remote modes

### 2. Working Memory
- **Purpose**: Extended context with intelligent management
- **Features**:
  - FIFO (First-In-First-Out) cleanup when memory limits exceeded
  - Vector search using embeddings
  - Configurable memory limits (MB)
  - Automatic context extraction

### 3. Persistent Memory
- **Purpose**: Long-term storage and multi-user support
- **Backends**:
  - SQLite (single-user, local deployments)
  - PostgreSQL (multi-user, production deployments)
- **Features**:
  - User isolation
  - Collection-based organization
  - Vector search with embeddings
  - Metadata support

## Configuration

### Basic Memory Configuration

```yaml
memory:
  # Buffer memory configuration
  buffer:
    size: 50                   # Number of messages to keep
    multiplier: 10             # Total capacity multiplier
    vector_search: true        # Enable semantic search
    mode: "local"              # "local" or "remote"

  # Working memory configuration
  working:
    max_memory_mb: 10          # Memory limit in MB
    fifo_interval_min: 5       # FIFO cleanup interval
    vector_dimension: 1536     # Embedding dimension

  # Persistent memory configuration
  persistent:
    provider: "postgresql"     # "sqlite" or "postgresql"
    connection_string: "${{ secrets.POSTGRES_URI }}"
    embedding_model: "openai/text-embedding-3-small"
```

### Provider-Specific Configurations

#### SQLite (Single-User)
```yaml
persistent:
  provider: "sqlite"
  connection_string: "sqlite:///path/to/database.db"
  # Use ":memory:" for in-memory database
```

#### PostgreSQL (Multi-User)
```yaml
persistent:
  provider: "postgresql"
  connection_string: "${{ secrets.POSTGRES_URI }}"
  # Format: postgresql://user:password@host:port/database
```

#### Remote Buffer with FAISSx
```yaml
buffer:
  mode: "remote"
  remote_config:
    host: "faissx-server.example.com"
    port: 65432
    api_key: "${{ secrets.FAISSX_API_KEY }}"  # Optional
```

## Memory Operations

### Automatic Memory Management

MUXI automatically manages memory during conversations:

1. **Message Storage**: All messages are stored in buffer memory
2. **Context Building**: Important information is extracted and stored
3. **FIFO Cleanup**: Oldest messages removed when limits exceeded
4. **Vector Search**: Semantic search finds relevant past context

### Developer APIs

#### remember_user_info

Store user properties and context programmatically:

```python
# Store structured data
await overlord.remember_user_info(
    user_id="user_123",
    properties={
        "plan": "pro",
        "preferences": {
            "language": "python",
            "style": "concise"
        }
    }
)

# Store natural language context
await overlord.remember_user_info(
    user_id="user_123",
    properties="I'm a software engineer working on AI projects"
)
```

#### Direct Memory Access

```python
# Add to persistent memory
await overlord.persistent_memory.add(
    user_id="user_123",
    content="Important information to remember",
    metadata={"type": "user_preference"}
)

# Search memories
results = await overlord.persistent_memory.search(
    user_id="user_123",
    query="python projects",
    limit=5
)
```

## Advanced Features

### 1. Automatic Context Extraction

MUXI automatically extracts and stores:
- User names and identities
- Project details and preferences
- Important facts and relationships
- Task-specific context

### 2. Smart Buffer with Vector Search

The buffer memory supports semantic search:
- Find related messages by meaning
- Retrieve context based on similarity
- Fallback to recency when needed

### 3. FIFO Memory Management

Prevents unbounded memory growth:
- Configurable memory limits (MB)
- Automatic cleanup intervals
- Preserves most recent/relevant content

### 4. Multi-User Isolation

Complete separation between users:
- Individual memory spaces
- No cross-contamination
- Secure user isolation

## Memory Schemas

### Collections Table (PostgreSQL)
```sql
CREATE TABLE collections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Memories Table (PostgreSQL)
```sql
CREATE TABLE memories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    collection_id INTEGER REFERENCES collections(id),
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Best Practices

### 1. Memory Sizing
- **Buffer**: ~50 messages for immediate context
- **Working**: 10% of RAM for extended conversations
- **Persistent**: Unlimited (database constrained)

### 2. Embedding Models
- Use `openai/text-embedding-3-small` for best performance
- Ensure vector dimensions match (typically 1536)
- Enable normalization for cosine similarity

### 3. User Context
- Use `remember_user_info` for explicitly remembering structured user data
- Store preferences and settings as metadata
- Leverage automatic context extraction

### 4. Performance Optimization
- Enable vector indexing for large datasets
- Use connection pooling for databases
- Configure appropriate FIFO intervals

## Troubleshooting

### Common Issues

1. **Memory Overflow**
   - Increase `max_memory_mb` in working memory
   - Reduce FIFO interval for faster cleanup
   - Check buffer size configuration

2. **Search Not Finding Content**
   - Verify embedding model is configured
   - Check vector dimensions match
   - Ensure content has embeddings

3. **User Isolation Issues**
   - Verify multi-user backend (PostgreSQL)
   - Check user_id is provided consistently
   - Review collection configurations

### Debug Commands

```bash
# Check memory configuration
cat formation.afs | grep -A 20 "memory:"

# Test database connection
psql $POSTGRES_URI -c "SELECT 1"

# Verify embeddings
python -c "from muxi.services.llm import LLM;
llm = LLM('openai/text-embedding-3-small');
print(len(llm.embed('test')))"
```

## Example Formations

### Minimal Memory Setup
```yaml
memory:
  buffer:
    size: 10
```

### Production Multi-User Setup
```yaml
memory:
  buffer:
    size: 50
    vector_search: true

  working:
    max_memory_mb: 100
    fifo_interval_min: 10

  persistent:
    provider: "postgresql"
    connection_string: "${{ secrets.POSTGRES_URI }}"
    embedding_model: "openai/text-embedding-3-small"
```

### High-Performance Setup with FAISSx
```yaml
memory:
  buffer:
    size: 20
    mode: "remote"
    remote_config:
      host: "faissx.internal"
      port: 65432

  persistent:
    provider: "postgresql"
    connection_string: "${{ secrets.POSTGRES_URI }}"

  working:
    max_memory_mb: 500
    vector_dimension: 1536
```

## Integration with Agents

Agents automatically use the configured memory systems:

```yaml
agents:
  - id: "assistant"
    name: "AI Assistant"
    system_message: |
      You have access to conversation history and user context.
      Use memories to provide personalized responses.
      Remember important information shared by users.
```

The memory system integrates seamlessly, requiring no special configuration in agent definitions.

## Security Considerations

1. **User Isolation**: Always use PostgreSQL for multi-user deployments
2. **Encryption**: Use encrypted connections for remote services
3. **API Keys**: Store credentials using the secrets system
4. **Access Control**: Implement proper user authentication

## Performance Metrics

Based on testing:
- **Buffer Search**: <10ms for 50 messages
- **Vector Search**: <50ms for 10k memories
- **FIFO Cleanup**: <100ms for 1000 messages
- **Embedding Generation**: ~200ms per message

## Future Enhancements

Planned improvements:
- Hierarchical memory organization
- Cross-user memory sharing (with permissions)
- Memory compression algorithms
- Advanced embedding models
- Real-time memory synchronization
