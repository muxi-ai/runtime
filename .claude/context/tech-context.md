# MUXI Runtime Technical Context

This document outlines the technical context of the MUXI Runtime, including technologies used, development setup, constraints, and dependencies.

## Recent Technical Improvements (July-September 2025)

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
- **OneLLM**: Provider-agnostic LLM interface (OpenAI, Anthropic, Google, etc.)
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
pytest tests/e2e/1_foundation/  # Foundation tests
pytest tests/e2e/2_memory/  # Memory systems
pytest tests/e2e/3_multimodal/  # Multimodal processing
pytest tests/e2e/4_mcp/  # MCP integration
pytest tests/e2e/5_artifacts/  # File generation
pytest tests/e2e/6_knowledge/  # Knowledge system
pytest tests/e2e/7_orchestration/  # Workflow orchestration (7A) and comprehensive A2A communication (7B)
pytest tests/e2e/8_clarification/  # Intelligent clarification flows

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
python -m muxi.cli serve --formation my-formation.yaml
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
CMD ["muxi", "serve", "--formation", "/config/formation.yaml"]
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
from muxi import Formation

# Load and start runtime
formation = Formation()
await formation.load("path/to/formation.yaml")
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
from muxi.observability import EventStream

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
- OneLLM 0.1.0+

### Memory & Search
- FAISS-cpu 1.10.0+
- PGVector 0.3.6+
- SQLite-vec 0.1.6+
- NumPy 1.24.0+

### Document Processing
- MarkItDown 0.1.0+
- Sentence-transformers 2.2.0+
- spaCy 3.8.0+

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
