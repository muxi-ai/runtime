# MUXI Runtime Technical Context

This document outlines the technical context of the MUXI Runtime, including technologies used, development setup, constraints, and dependencies.

## Recent Technical Improvements (July-October 2025)

### Code Quality & Security Improvements (October 26, 2025)
- **HTTP Semantics Compliance**: Fixed GET endpoint side effects
  - Split user identifier endpoints: GET (lookup only) vs POST (resolution with creation)
  - Added `create_if_missing` parameter for explicit control over user creation
- **Timezone Handling**: Fixed audit log timestamp filtering
  - Replaced string comparison with proper datetime comparison
  - UTC normalization for both naive and aware datetimes
  - Handles multiple ISO format variations (Z suffix, timezone offsets)
- **Input Validation**: Enhanced security across multiple endpoints
  - Path traversal prevention in SOP endpoints (regex validation)
  - Safe string indexing to prevent IndexError on empty input
- **Concurrency Warnings**: Clarified atomic operations
  - Renamed `atomic_update_yaml` → `update_yaml` (more accurate naming)
  - Added prominent warnings about read-modify-write race conditions
  - Provided locking examples (FileLock) for safe concurrent access
- **Test Coverage**: Added 19 new tests for validation and edge cases
- **Code Quality**: Zero ruff linting errors across codebase

### Multi-Identity User Management (October 2025)
- **Database Schema**: Two-table design for one-to-many identifier mapping
  - `users` table: Core entity with auto-increment ID, public_id (usr_xxxx), formation_id
  - `user_identifiers` table: External identifier mapping with user_id FK, identifier, identifier_type
  - Optimized indexes: `(identifier, formation_id)` for lookups, `user_id` for joins
  - Cascading deletes: Remove identifiers when user deleted
- **User Resolution**: Fast identifier-to-user mapping with KV caching
  - `resolve_user_identifier()`: Main resolution with auto-creation (~5ms cache hits, ~50ms DB)
  - `associate_user_identifiers()`: Batch identifier association with conflict detection
  - Cache strategy: `user_id:{formation_id}:{identifier}` → `{internal_id}:{muxi_id}`, 1hr TTL
  - Transaction safety: Individual commits preserve successful creates on partial failures
- **Service Integration**: Resolution integrated across all user-scoped services
  - Long-Term Memory: `_resolve_user_id_async/sync()` for memory operations
  - Credential Resolver: `_resolve_user_id()` for credential lookups
  - Scheduler: User resolution for job associations and audit trails
  - Chat Orchestrator: User resolution for context and synopsis injection
- **Input Validation**: Fail-fast validation for robustness
  - Identifier and formation_id: Must be non-empty strings (ValueError on failure)
  - Clear error messages showing type and value for debugging
- **Security Improvements**: Security analysis correctly scoped
  - Only credential/ambiguous_credential clarifications bypass security checks
  - Redirect clarifications undergo normal security analysis
  - Fixed observability enum references to prevent AttributeErrors

### LLM Response Caching (October 2025)
- **OneLLM Integration**: Built-in semantic similarity caching via `init_cache()`
- **Configuration**: Formation YAML `llm.settings.caching` with 7 tunable parameters
- **Cost Savings**: 70%+ reduction on repeated/similar queries through semantic matching
- **Similarity Threshold**: Configurable `p` value (default 0.95) for cache hit precision
- **Cache Management**: Automatic LRU eviction, TTL expiration (default 24hr)
- **Stream-Aware**: Configurable chunking strategies (sentences/words) for streaming responses
- **Performance**: Sub-millisecond cache lookups, minimal memory overhead
- **Observability**: Clean logging with filtered OneLLM internal warnings
- **Module-Level Init**: Universal coverage through LLM service initialization

### User Synopsis System (October 2025)
- **Two-Tier Caching**: Identity (permanent) + Context (TTL-based) for optimal cost/freshness
- **Collections**: user_identity, relationships, work_projects (Tier 1); preferences, activities (Tier 2)
- **LLM Synthesis**: Type-specific prompts for identity vs context generation
- **Cache Keys**: Internal users.id (integer) for efficiency and consistency
- **Performance**: ~85% cost reduction via intelligent caching strategy
- **Query Optimization**: Direct get_recent_memories() instead of semantic search
- **Integration**: Automatic injection into enhanced messages via chat_orchestrator

### SOP System Simplification & Refactoring (August 2025)
- **Architecture**: Direct pass to task decomposer (no manual parsing)
- **Module Location**: Moved from `overlord.sops` to `workflow.sops` for better architectural alignment
- **Performance**: 40-80% improvement through intelligent optimization
- **Code Reduction**: 72% less code (1000+ → ~800 lines)
- **Execution Modes**: Template (strict) and Guide (flexible)
- **Discovery**: FAISS-based semantic search for SOP matching

### Advanced Async Operations (September 2025)
- **Request Lifecycle Management**: Ultra-simplified two-tier storage using existing buffer memory
- **Memory Leak Prevention**: 48-hour TTL with automatic cleanup via proven FIFO system
- **Status Tracking**: `get_request_status()` API for monitoring active/completed requests
- **Cancellation Support**: `cancel_request()` with asyncio.Task cancellation
- **Webhook Resilience**: Retry logic with graceful degradation, independent of core processing
- **Conflict Resolution**: Async mode overrides streaming with transparent logging
- **Production Architecture**: Only 2 code locations modified, leveraging existing infrastructure

### Resilience Integration
- **User-Friendly Errors**: Context-aware error messages instead of generic failures
- **Recovery Strategies**: Automatic retry with exponential backoff
- **Circuit Breakers**: Prevent cascading failures in multi-agent workflows
- **Graceful Degradation**: Fallback responses when services unavailable

### Synthesis Enhancement
- **Conversational Awareness**: LLM-intelligent response style detection
- **Language Agnostic**: No keyword matching, pure LLM understanding
- **Context-Appropriate**: Natural responses for greetings, confirmations for tasks

### Response Formats Implementation (September 2025)
- **Multi-Format Support**: JSON, Markdown, Plain Text, and HTML response formats
- **LLM-Based Formatting**: Persona-level format instructions for natural language understanding
- **HTML Validation**: BeautifulSoup4 integration for tag validation and structure fixing
- **Post-Processing Pipeline**: JSON wrapping and format-specific enhancements
- **Streaming Compatible**: All formats work seamlessly with existing streaming architecture
- **Configuration Driven**: Format selection via `overlord.response.format` in formation YAML

### Enhanced Token Tracking & Database Compatibility (September 2025)
- **Array-Based Token Structure**: Self-documenting 6-field format `[total, input, output, total_cached, input_cached, output_cached]`
- **Cache Token Support**: Ready for OneLLM cache token data with automatic total calculation
- **Multi-Model Tracking**: Per-model breakdown with real-time accumulation across operations
- **Backward Compatibility**: Legacy `total_tokens` and `breakdown_legacy` properties preserved
- **Performance Optimization**: 25% smaller payload than object-based approach
- **SQLAlchemy 2.0+ Compatibility**: Fixed pgvector extension creation with proper `text()` wrapper
- **Production Ready**: Clean PostgreSQL initialization without false error warnings

### MCP Warning Suppression
- **Clean Logs**: Suppressed third-party MCP server warnings
- **Better UX**: Cleaner output without verbose validation warnings
- **Smart Suppression**: Only during connection, preserves important errors

## Core Technologies

MUXI Runtime is built using modern Python technologies with a focus on production reliability and performance.

### Programming Languages

- **Python 3.10+**: Primary language for the runtime engine
- **YAML**: Declarative formation configuration language
- **SQL**: Database interactions (PostgreSQL/SQLite)

### Key Libraries and Frameworks

#### Core Runtime
- **Pydantic**: Data validation and configuration management
- **PyYAML**: Formation parsing and validation
- **Python-dotenv**: Environment variable management
- **Anyio**: Async I/O abstraction

#### LLM Integration
- **OneLLM 0.20251013.0+**: Provider-agnostic LLM interface with built-in caching (OpenAI, Anthropic, Google, etc.)
- **Sentence-transformers**: Embedding generation for vector search

#### Memory Systems
- **SQLAlchemy[asyncio]**: Async ORM for persistent memory
- **FAISS-cpu**: Vector similarity search for buffer memory
- **FAISSx**: Distributed FAISS for remote vector operations
- **PGVector**: PostgreSQL vector extension
- **SQLite-vec**: SQLite vector extension for local deployments

#### Document Processing
- **MarkItDown[all]**: Convert various file formats to Markdown
  - PDF, Word, Excel, PowerPoint, images, audio, video
  - HTML, XML, ZIP archives
- **PyPDF2**: PDF document processing
- **Python-docx**: Word document processing
- **Pillow**: Image processing
- **NLTK/spaCy**: Natural language processing for text chunking

#### Communication & Protocols
- **MCP**: Model Context Protocol implementation (1.9.0+) with agent isolation
- **A2A-SDK**: Google's Agent-to-Agent communication SDK with registry integration
- **HTTPX**: Async HTTP client with SSE support for external A2A communication
- **WebSockets**: Real-time bidirectional communication
- **FastAPI/Uvicorn**: API server components with OpenAPI spec compliance
- **Jinja2**: Template rendering for webhook triggers with event data interpolation
- **A2A Registry**: Agent discovery and registration system with service ID precedence

#### Observability
- **Rich**: Terminal formatting and progress bars
- **Custom event streaming**: 10 formatters, 4 transports

### Databases & Storage

#### Primary Options
- **PostgreSQL 13+**: Production multi-user deployments
  - With pgvector extension for vector similarity
  - Connection pooling for performance
  - Multi-tenant isolation via Memobase

- **SQLite**: Local/single-user deployments
  - With sqlite-vec for vector operations
  - File-based for easy backup
  - Lower resource requirements

#### Vector Stores
- **FAISS**: In-memory vector search (buffer memory)
- **FAISSx**: Distributed vector service
- **pgvector**: PostgreSQL vector extension
- **sqlite-vec**: SQLite vector extension

## System Architecture

### Core Components

1. **Formation Engine**
   - YAML parser and validator
   - Environment variable substitution
   - Schema validation
   - Hot reload support

2. **Overlord Orchestrator**
   - Central message routing
   - Intent detection
   - SOP coordination
   - Memory management
   - Agent lifecycle

3. **Agent Framework**
   - Base agent class
   - Specialized implementations
   - Knowledge base integration
   - Tool execution

4. **Memory Systems**
   - Buffer memory (FIFO + vector)
   - Persistent memory (PostgreSQL/SQLite)
   - Multi-user isolation (Memobase)
   - Semantic search capabilities

5. **Service Layer**
   - MCP service (tool integration with agent isolation)
   - Multimodal service (file processing with MarkItDown)
   - A2A service (internal/external agent communication with registry)
   - Scheduler service (natural language task scheduling)
   - Observability (comprehensive event streaming)

## Development Setup

### Environment Requirements

```bash
# Python version
Python 3.10+ (3.11 recommended)

# Database
PostgreSQL 13+ with pgvector extension (production)
# OR
SQLite 3.35+ with sqlite-vec (development)

# System dependencies
python3-dev
build-essential
```

### Installation Process

```bash
# Clone repository
git clone https://github.com/muxi-ai/runtime
cd runtime

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev]"

# Download spaCy language model
python -m spacy download en_core_web_sm
```

### Environment Configuration

```bash
# Copy example environment
cp .env.example .env

# Edit with your configuration
vim .env
```

Key environment variables:
```bash
# LLM API Keys (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...

# Database Configuration
# For PostgreSQL (production)
DATABASE_URL=postgresql://user:pass@localhost:5432/muxi
# For SQLite (development)
DATABASE_URL=sqlite:///muxi.db

# Optional Services
FAISSX_URL=http://localhost:8000  # Distributed vector store
MCP_WEATHER_API_KEY=...           # Weather tool
MCP_SEARCH_API_KEY=...            # Search tool

# Performance Tuning
MAX_WORKERS=4
MEMORY_BUFFER_SIZE=20
VECTOR_DIMENSION=1536
EMBEDDING_BATCH_SIZE=100
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test suites
pytest e2e/tests/1_foundation/  # Foundation tests
pytest e2e/tests/2_memory/  # Memory systems
pytest e2e/tests/3_multimodal/  # Multimodal processing
pytest e2e/tests/4_mcp/  # MCP integration
pytest e2e/tests/5_artifacts/  # File generation
pytest e2e/tests/6_knowledge/  # Knowledge system
pytest e2e/tests/7_orchestration/  # Workflow orchestration (7A) and comprehensive A2A communication (7B)
pytest e2e/tests/8_clarification/  # Intelligent clarification flows

# Run with coverage
pytest --cov=muxi --cov-report=html

# Run with real services (no mocks)
export OPENAI_API_KEY="your-key"
pytest -v
```

## Technical Constraints

### Performance Considerations

1. **Response Times**
   - Target: <2s for simple queries
   - Complex workflows: <30s with streaming
   - Formation loading: <2s
   - Knowledge indexing: Depends on file count/size

2. **Memory Usage**
   - Runtime overhead: ~200MB base
   - Per conversation: ~1MB (buffer memory)
   - Vector embeddings: ~4KB per chunk
   - Growth rate: <100MB per 100 conversations

3. **Concurrency**
   - Async I/O throughout
   - Non-blocking LLM calls
   - Parallel tool execution
   - Database connection pooling

4. **Database Performance**
   - PostgreSQL: Better for concurrent users
   - SQLite: Single writer limitation
   - Vector search: O(log n) with indexes
   - Batch operations preferred

### Scalability Limits

1. **Single Instance**
   - Users: 1,000+ concurrent
   - Agents: 50+ per formation
   - Memory: 10GB recommended
   - CPU: 4+ cores recommended

2. **Database Limits**
   - PostgreSQL: Practically unlimited
   - SQLite: 281 TB theoretical limit
   - Vector dimensions: 2000 (pgvector)
   - Concurrent writes: 1 (SQLite)

3. **External Dependencies**
   - LLM rate limits apply
   - MCP server availability
   - Network latency impacts

## Deployment Patterns

### Development
```bash
# Simple local deployment
python -m muxi.cli serve --formation my-formation.afs
```

### Production
```bash
# With PostgreSQL and monitoring
DATABASE_URL=postgresql://... \
OBSERVABILITY_ENABLED=true \
python -m muxi.cli serve \
  --formation production.yaml \
  --workers 4
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install muxi-runtime
CMD ["muxi", "serve", "--formation", "/config/formation.afs"]
```

## Security Considerations

1. **Credential Management**
   - User-level encryption
   - Isolated credential stores
   - Environment variable security
   - No credentials in formations

2. **Sandboxing**
   - File generation sandboxed
   - Limited resource access
   - No network in sandbox
   - Temporary file cleanup

3. **Data Isolation**
   - User memory partitioning
   - Agent knowledge isolation
   - Session-based contexts
   - Audit logging

## Integration Points

### For MUXI Server
```python
from muxi.runtime import Formation

# Load and start runtime
formation = Formation()
await formation.load("path/to/formation.afs")
overlord = await formation.start_overlord()

# Handle requests
response = await overlord.chat(
    message="User input",
    user_id="user123",
    stream=True
)
```

### For Tool Developers
```yaml
# Add tools via MCP in formation
mcp:
  servers:
    - id: "custom-tools"
      type: "command"
      command: ["python", "-m", "my_mcp_server"]
```

### For Monitoring
```python
# Configure observability
from muxi.runtime.observability import EventStream

stream = EventStream(
    formatters=["datadog", "opentelemetry"],
    transports=["http://monitoring:8080"]
)
```

## Dependencies Summary

### Core Runtime
- Python 3.10+
- Pydantic 2.0+
- SQLAlchemy 2.0+ (async)
- OneLLM 0.20251013.0+ (with caching support)

### Memory & Search
- FAISS-cpu 1.10.0+
- PGVector 0.3.6+
- SQLite-vec 0.1.6+
- NumPy 1.24.0+

### Document Processing
- MarkItDown 0.1.0+
- Sentence-transformers 2.2.0+
- spaCy 3.8.0+
- BeautifulSoup4 4.12.0+ (HTML parsing and validation)

### Communication
- MCP 1.9.0+
- A2A-SDK 0.2+
- HTTPX 0.24.0+
- WebSockets 11.0.3+

### Development
- Pytest 7.0.0+
- Black (formatting)
- Flake8 (linting)
- Pyright (type checking)

This technical foundation enables MUXI Runtime to deliver production-ready AI agent execution with excellent performance, scalability, and maintainability.
