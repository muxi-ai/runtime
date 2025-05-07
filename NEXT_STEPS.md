# Developer Tasks and Implementation Checklist

This document provides a detailed task tracker for developers working on the MUXI Framework. It contains specific implementation tasks, checklists, and tracks completed work. For the high-level strategic vision and roadmap, see the [docs/roadmap.md](docs/roadmap.md) file.

## Completed Work

Core components of the muxi framework now implemented:

1. **Model Context Protocol (MCP)**: Standardized communication with LLMs
   - [x] Fixed message handling to properly use role/content attributes
   - [x] Improved process_message and process_tool_call methods
   - [x] Standardized message structure for compatibility with all LLM providers
   - [x] Implemented centralized MCPService as a singleton pattern
   - [x] Added ToolParser for extracting tool calls from LLM responses
   - [x] Added configurable request timeouts at overlord, agent, and per-request levels
   - [x] Implemented thread-safe tool invocation with locks for concurrent access
   - [x] Created comprehensive documentation in `.cursor/rules/mcp_service.mdc`
   - [x] Added proper error handling with consistent patterns throughout MCP interactions
2. **Memory System**:
   - [x] Implemented FAISS-backed smart buffer memory with hybrid semantic+recency retrieval
   - [x] Added configurable recency bias parameter to balance semantic relevance with time
   - [x] Implemented graceful degradation to recency-only search when no model is available
   - [x] Improved metadata filtering capabilities for more targeted memory retrieval
   - [x] Added thread-safe operations for concurrent access to memory systems
   - [x] Created comprehensive documentation in `.cursor/rules/smart_buffer_memory.mdc`
   - [x] Long-term memory using PostgreSQL with pgvector
   - [x] Long-term memory using SQLite with sqlite-vec extension
   - [x] Added proper error handling and fallback mechanisms for vector extensions
   - [x] Memobase system for multi-user support with partitioned memories
   - [x] Domain knowledge system for user-specific structured information
   - [x] Robust database schema with optimized tables and indexes
   - [x] Migration system for schema version control
   - [x] Centralized memory management at overlord level
3. **MCP Server Integration**:
   - [x] MCP Handler for communication with external services
   - [x] Centralized MCPService for managing all MCP server communications
   - [x] MCP message processing
   - [x] Example MCP servers (Calculator, Web Search)
   - [x] Implement proper transport abstraction with factory pattern
   - [x] Support for HTTP+SSE transport
   - [x] Support for Command-line transport
   - [x] Implement reconnection with exponential backoff
   - [x] Implement cancellation support for in-progress operations
   - [x] Comprehensive error handling and diagnostics
   - [x] Integration with the official MCP Python SDK
   - [x] Make credentials optional for MCP servers that don't require them
4. **Agent Class**: Main interface combining LLM, memory, and MCP servers
   - [x] Agent-level knowledge base for specialized domain knowledge
   - [x] Dynamic embedding generation using the agent's model
   - [x] File-based knowledge sources with efficient caching
   - [x] Updated agent to use centralized MCPService singleton
   - [x] Removed direct MCP handler dependency in favor of the shared service
   - [x] Agent now delegates to overlord for all memory operations
5. **Overlord**: For managing multiple agents and their interactions
   - [x] Intelligent message routing with LLM-based agent selection
   - [x] Agent descriptions for specialized capabilities
   - [x] Automatic caching of routing decisions for performance
   - [x] Centralized memory management for all agents
   - [x] Centralized API key handling
   - [x] Enhanced support for multi-user environments
6. **Configuration System**: For loading and managing configuration
   - [x] Support for YAML and JSON configuration files
   - [x] Environment variable substitution in configurations
   - [x] Robust validation of configuration parameters
7. **Example Script**: To demonstrate how to use the framework
8. **Real-Time Communication**:
   - [x] WebSocket server for real-time agent interaction
   - [x] Proper message serialization for MCP messages
   - [x] Shared overlord instance between REST API and WebSocket server
   - [x] Resilient connection handling with automatic reconnection
   - [x] Comprehensive error handling
   - [x] Support for multi-user WebSocket connections
9. **API Improvements**:
   - [x] REST API for agent management and interaction
   - [x] Multi-user support endpoints
   - [x] Memory management endpoints including search and clear
   - [x] Comprehensive test coverage
10. **Command Line Interface**:
    - [x] Rich terminal-based interface for agent interaction
    - [x] Commands for chat, one-off messages, and server management
    - [x] Colored output with Markdown support
    - [x] Convenient launcher for API server and web UI
11. **Code Quality**:
    - [x] Resolved deprecation warnings for SQLAlchemy and FastAPI
    - [x] Standardized line length configuration across linting tools
    - [x] Improved VS Code integration with consistent formatting rules
    - [x] Fixed all test warnings and errors
    - [x] Implemented pytest.ini configuration to filter FAISS-related DeprecationWarnings
12. **Developer Tools**:
    - [x] MCP Server Generator with interactive CLI wizard
    - [x] Template-based code generation system
    - [x] Flattened template structure for simpler maintenance
13. **Architecture Evolution**:
    - [x] Restructured codebase into modular packages
    - [x] Created setup.py for each package with appropriate dependencies
    - [x] Implemented proper monorepo structure
    - [x] Created development installation scripts
    - [x] Fixed cross-package imports
    - [x] Completed migration from src/muxi to direct muxi directories
    - [x] Updated all import paths to reflect the new structure
    - [x] Created meta package for unified installation
    - [x] Updated all documentation to reflect new package structure
14. **Vector Database Support**:
    - [x] SQLite with sqlite-vec integration for local deployments
    - [x] Reorganized extensions directory structure
    - [x] Added proper Python package for easier installation
    - [x] Implemented automatic fallback from package to binary extensions
    - [x] Enhanced compatibility with various platforms and architectures

## Todo List

Things to do next to enhance the framework, ordered by priority:

### 1. Complete MUXI LLM Implementation

- [ ] Complete core MUXI LLM functionality
  - [ ] Standardized interface for all LLM providers
  - [ ] Support for streaming responses
  - [ ] Optimized token handling and counting
  - [ ] Automatic retries with exponential backoff
  - [ ] Comprehensive error handling with fallbacks
  - [ ] Model-specific parameter validation
  - [ ] Caching mechanism for identical requests
- [ ] Implement provider-specific adaptations
  - [ ] OpenAI (already implemented)
  - [ ] Anthropic
  - [ ] Gemini/VertexAI (Google)
  - [ ] xAI (Grok)
  - [ ] Azure OpenAI
  - [ ] HuggingFace
  - [ ] Openrouter
  - [ ] Local models (via Ollama)
  - [ ] Amazon Bedrock (Claude, Titan, etc.)
  - [ ] NVIDIA
- [ ] Create model router for fallback and cost optimization
  - [ ] Priority-based routing logic
  - [ ] Cost-aware model selection
  - [ ] Error-triggered fallback chains
  - [ ] Usage metrics and quotas

### 2. Replace Provider Model with MUXI LLM

- [ ] Refactor existing model providers to use MUXI LLM
- [ ] Update all code references to use the new MUXI LLM interfaces
- [ ] Create backward compatibility layer if needed
- [ ] Update documentation to reflect new model handling
- [ ] Test all existing functionality with new implementation
- [ ] Optimize performance for common operations

### 3. Multi-Modal Capabilities

Transform agents into omni agents capable of handling various media types:

#### Document Processing
- [ ] PDF processing and text extraction
- [ ] Support for Office documents (Word, Excel, etc.)
- [ ] OCR for scanned documents
- [ ] Document summarization tools

#### Image Processing
- [ ] Extend MCPMessage to support image attachments
- [ ] Create image preprocessing pipeline
  - [ ] Resize and optimize images for models
  - [ ] Format conversion utilities
  - [ ] Metadata extraction
- [ ] Integrate with vision-capable models
  - [ ] OpenAI GPT-4V
  - [ ] Anthropic Claude 3
  - [ ] Google Gemini
  - [ ] Local models with vision capabilities
- [ ] Update API endpoints to handle image uploads

#### Audio Processing
- [ ] Audio file handling and processing
  - [ ] Support various audio formats (MP3, WAV, etc.)
  - [ ] Audio normalization and enhancement
- [ ] Speech-to-text integration
  - [ ] OpenAI Whisper integration
  - [ ] Other speech recognition options
- [ ] Text-to-speech for agent responses
  - [ ] Voice selection options
  - [ ] Emotion/tone control
- [ ] Streaming audio capabilities
  - [ ] Design protocol for audio streaming via SSE/WebRTC
  - [ ] Implement real-time audio processing

### 4. Agent-to-Agent (A2A) Communication

Based on prd-a2a.md specifications:

- [ ] Implement the A2A protocol for inter-agent communication
  - [ ] Capability discovery mechanism
  - [ ] Task delegation between agents
  - [ ] Context sharing with proper isolation
  - [ ] Conversation lifecycle management
  - [ ] External agent integration
  - [ ] Security and authentication
- [ ] Enhance MCP Server Interface
  - [ ] SSE-based MCP server implementation
  - [ ] Automatic tool discovery from agent capabilities
  - [ ] NPX bridge package for non-SSE clients
  - [ ] Streaming response handling
  - [ ] Authentication shared with REST API

### 5. Implement Overlord Overlord

Based on prd-overlord-overlord.md specifications:

- [ ] Implement task decomposition mechanism
  - [ ] Automated parsing of complex requests into subtasks
  - [ ] Subtask dependency management
  - [ ] Task prioritization based on context and dependencies
- [ ] Create agent capability registry
  - [ ] Discovery and registration of agent capabilities
  - [ ] Capability-based routing for subtasks
  - [ ] Score-based agent selection
- [ ] Develop workflow management system
  - [ ] DAG construction for task workflows
  - [ ] Execution state tracking
  - [ ] Inter-task data passing
  - [ ] Result aggregation mechanism
- [ ] Add self-correction mechanism
  - [ ] Execution path monitoring
  - [ ] Error detection and recovery
  - [ ] Dynamic workflow adjustment
- [ ] Implement reasoning engine
  - [ ] Prompt engineering for effective task decomposition
  - [ ] Integration with high-quality reasoning models
  - [ ] Contextual adaptation of task execution
- [ ] Create A2A Integration
  - [ ] Leverage A2A capability discovery for orchestration
  - [ ] Delegate subtasks via A2A communication
  - [ ] Manage context across agent boundaries

### 6. REST API & Interface Implementation

Based on the prd-api-server.md specifications, implement the unified MUXI API Server:

- [x] Implement centralized MCPService as a singleton for MCP server interactions
- [ ] Implement unified API Server architecture
  - [ ] Core API server with shared components (auth, logging, rate limiting)
  - [ ] Configuration system with environment variable support
  - [ ] Structured error handling and response format
  - [ ] Consistent response structure across all endpoints
- [ ] Implement REST API endpoints
  - [ ] User/Interface endpoints for agent interaction
    - [ ] Agent chat endpoints (POST /api/v1/agents/{agent_id}/chat)
    - [ ] Overlord chat endpoints (POST /api/v1/chat)
    - [ ] Conversation history endpoints (GET /api/v1/conversations)
  - [ ] Developer/Management endpoints
    - [ ] Agent management (GET/POST/PATCH/DELETE /api/v1/agents)
    - [ ] Memory operations (GET/DELETE /api/v1/agents/{agent_id}/memory)
    - [ ] Context memory CRUD operations
    - [ ] MCP server management
    - [ ] Knowledge management
    - [ ] System information and monitoring
- [ ] Implement dual-key authentication system
  - [ ] User/Interface API keys for client access (sk_muxi_user_*)
  - [ ] Administrative API keys for system management (sk_muxi_admin_*)
  - [ ] Automatic key generation mechanism
  - [ ] Secure key storage and validation
- [ ] Add SSE streaming support
  - [ ] Stream agent responses in real-time
  - [ ] Event-based streaming format
  - [ ] Connection recovery mechanism
  - [ ] Tool call event streaming
- [ ] Implement MCP protocol support
  - [ ] Integrate FastMCP or similar library
  - [ ] Tool definition discovery and exposure
  - [ ] Request routing to appropriate agents
  - [ ] Streaming MCP responses
- [ ] Set up WebRTC signaling server for multi-modal
  - [ ] Session management endpoints
  - [ ] Signaling protocol implementation
  - [ ] Integration with agent message processing
- [ ] Add security features
  - [ ] CORS configuration
  - [ ] Security headers
  - [ ] Input validation
  - [ ] Rate limiting per endpoint and per key
- [ ] Create OpenAPI/Swagger documentation
  - [ ] Document all endpoints with examples
  - [ ] Create interactive API playground
  - [ ] Include authentication instructions

### 7. CLI Interfaces

- [ ] Enhance CLI interface
  - [ ] Add support for all API operations
  - [ ] Improve user experience with better formatting and colors
  - [ ] Add multi-modal interaction support
  - [ ] Implement configuration management commands
- [ ] Improve API server
  - [ ] Implement all endpoints described in the spec
  - [ ] Add comprehensive test coverage

### 8. Web UI

- [ ] Develop web interface
  - [ ] Create responsive UI for mobile and desktop
  - [ ] Implement real-time updates using SSE
  - [ ] Add support for multi-modal interactions
  - [ ] Build user-friendly configuration interface
  - [ ] Create agent management dashboard

### 9. MUXI as a Service

Based on prd-muxi-as-a-service.md specifications:

- [ ] Create Docker container with pre-configured MUXI
  - [ ] Pre-installed dependencies and optimized configuration
  - [ ] Environment variable configuration system
  - [ ] Volume mounting for persistent storage
  - [ ] Health checks and monitoring
- [ ] Implement unified YAML configuration
  - [ ] Configuration parser for application-level YAML
  - [ ] Schema validation for configuration files
  - [ ] Environment variable substitution
  - [ ] Default configuration templates
- [ ] Build persistence layer for configurations
  - [ ] Storage system for agent configurations
  - [ ] Change tracking and versioning
  - [ ] Backup and restore functionality
- [ ] Create language-agnostic APIs
  - [ ] RESTful API for configuration management
  - [ ] SDK generator for multiple languages
  - [ ] Real-time interface for interaction via SSE
  - [ ] MCP server interface for tool integration
- [ ] Implement CLI tooling
  - [ ] Agent management commands
  - [ ] Configuration validation
  - [ ] Remote server management
  - [ ] Authentication handling
- [ ] Build administrative web interface
  - [ ] Agent management dashboard
  - [ ] Configuration editor
  - [ ] Monitoring and analytics
  - [ ] User management

### 10. Language-Specific SDKs

- [ ] TypeScript/JavaScript SDK
- [ ] Language-specific SDKs
  - [ ] PHP
  - [ ] Go
  - [ ] Java/Kotlin
  - [ ] Rust
  - [ ] C#/.NET
  - [ ] Ruby
- [ ] Platform-specific SDKs
  - [ ] iOS Swift
  - [ ] Android Kotlin
  - [ ] Dart

## Implementation Roadmap

Based on current progress and updated priorities:

### Phase 1: Core Foundation & Multi-Modal
- [ ] Complete MUXI LLM Implementation with unified model interface
- [ ] Replace current provider model module with MUXI LLM
- [ ] Add multi-modal capabilities (image, audio, document processing)
- [ ] Create standardized retry mechanisms and error handling
- [ ] Support multiple LLM providers with consistent interfaces
- [ ] Implement cost-aware model routing and fallbacks

### Phase 2: Advanced Agent Capabilities
- [ ] Implement A2A Communication Protocol
- [ ] Create capability discovery mechanism
- [ ] Build context sharing with proper isolation
- [ ] Add security layer for inter-agent communication
- [ ] Develop task delegation system

### Phase 3: Enhanced Orchestration
- [ ] Transform overlord into "Overlord" system
- [ ] Implement automatic task decomposition
- [ ] Create capability-based agent selection
- [ ] Build workflow management for dependencies
- [ ] Develop self-correction mechanisms
- [ ] Integrate with A2A communication

### Phase 4: Interface & API Development
- [ ] Complete RESTful API implementation
- [ ] Implement SSE for streaming
- [ ] Create MCP server endpoints
- [ ] Add WebRTC support for multi-modal
- [ ] Enhance CLI interface
- [ ] Develop administrative Web UI
- [ ] Add authentication and security layers

### Phase 5: Service & SDK Development
- [ ] Create Docker-based MUXI as a Service
- [ ] Build unified YAML configuration system
- [ ] Develop language-agnostic SDK generators
- [ ] Add persistence for agent configurations
- [ ] Implement language-specific SDKs

## Contribution Guidelines

Guidelines for contributing to the framework:

1. **Code Style**: Follow PEP 8 guidelines
2. **Documentation**: Document all public functions, classes, and methods
3. **Testing**: Write tests for all new features
4. **Pull Requests**: Create a pull request with a clear description of changes
5. **Issues**: Use GitHub issues for bug reports and feature requests

## Example Scenarios

### Simple Agent with Configuration Files

This scenario demonstrates a complete workflow from installation to running an agent using the new configuration-based approach:

1. **Install the Framework**

   ```bash
   # Clone the repository
   git clone https://github.com/your-org/muxi.git
   cd muxi

   # Install dependencies
   pip install -e .
   ```

2. **Create a Configuration File**

   Create a file `configs/my_agent.yaml`:

   ```yaml
   name: my_assistant
   system_message: You are a helpful assistant with weather capabilities.
   model:
     provider: openai
     api_key: "${OPENAI_API_KEY}"
     model: gpt-4o
     temperature: 0.7
   memory:
     buffer_size: 10            # Context window size of 10 messages
     buffer_multiplier: 10      # Total buffer capacity will be 10 × 10 = 100 messages
     long_term: true            # Enable long-term memory with default SQLite in app's root
     # Or use SQLite explicitly: long_term: "sqlite:///data/memory.db"
     # Or PostgreSQL: long_term: "postgresql://user:password@localhost:5432/muxi"
   knowledge:
   - path: "knowledge/weather_facts.txt"
     description: "Facts about weather patterns and climate"
   - path: "knowledge/geography.txt"
     description: "Information about global geography"
   mcp_servers:
   - name: calculator
     url: http://localhost:5000
     credentials: []
   - name: weather
     url: http://localhost:5001
     credentials:
     - id: weather_api_key
       param_name: api_key
       required: true
       env_fallback: WEATHER_API_KEY
   - name: web_search
     url: http://localhost:5002
     credentials:
     - id: search_api_key
       param_name: api_key
       required: true
       env_fallback: SEARCH_API_KEY
   ```

3. **Set Up Environment Variables**

   Create a `.env` file:

   ```
   OPENAI_API_KEY=your_openai_key_here
   # PostgreSQL connection
   POSTGRES_DATABASE_URL=postgresql://user:password@localhost:5432/muxi
   # Or SQLite connection
   # USE_LONG_TERM_MEMORY=sqlite:///data/memory.db
   # Or just enable default SQLite in app's root directory
   # USE_LONG_TERM_MEMORY=true
   WEATHER_API_KEY=your_weather_api_key
   SEARCH_API_KEY=your_search_api_key
   ```

4. **Create a Simple Application**

   Create a file `app.py`:

   ```python
   from dotenv import load_dotenv
   from muxi import muxi

   # Load environment variables
   load_dotenv()

   # Initialize MUXI - the database connection will be loaded
   # automatically from POSTGRES_DATABASE_URL when needed
   mx = muxi()

   # Add agent from configuration
   mx.add_agent("assistant", "configs/my_agent.yaml")

   # Interactive mode - explicitly specify the agent (optional)
   response = mx.chat("What's the weather like in London?", agent_name="assistant")
   print(f"Response: {response}")

   # Let the overlord automatically select the appropriate agent (recommended)
   response = mx.chat("What's the weather like in New York?")
   print(f"Response: {response}")

   # Add knowledge programmatically
   from muxi.knowledge.base import FileKnowledge
   new_knowledge = FileKnowledge(path="knowledge/climate_data.txt", description="Climate data for major cities")
   mx.get_agent("assistant").add_knowledge(new_knowledge)

   # Or start a server
   # mx.start_server(port=5050)
   ```

5. **Run the Application**

   ```bash
   python app.py
   ```

### Working with Smart Buffer Memory

Demonstrates how to use the FAISS-backed smart buffer memory:

```python
from muxi.core.overlord import Overlord
from muxi.core.memory.buffer import BufferMemory
from muxi.core.models.providers.openai import OpenAIModel

# Create embedding model for vector search
embedding_model = OpenAIModel(model="text-embedding-ada-002", api_key="your_api_key")

# Create a buffer memory with semantic search capabilities
buffer = BufferMemory(
    max_size=10,                  # Context window size (recent messages)
    buffer_multiplier=10,         # Total capacity = 10 × 10 = 100 messages
    model=embedding_model,        # Model for generating embeddings
    vector_dimension=1536,        # Dimension for OpenAI embeddings
    recency_bias=0.3              # Balance between semantic (0.7) and recency (0.3)
)

# Create overlord with the smart buffer memory
overlord = Overlord(buffer_memory=buffer)

# Add a message to the buffer
await overlord.add_to_buffer_memory(
    "Important information about quantum computing algorithms",
    metadata={"topic": "quantum computing", "importance": "high"}
)

# Search the memory (semantically similar content)
results = await overlord.search_memory(
    "Tell me about quantum algorithms",
    k=5
)
```

### RESTful API Server

According to the api.md specification, starting a MUXI API server:

```python
from muxi import muxi

app = muxi()

# Load agents from configurations
app.add_agent("assistant", "configs/assistant.yaml")
app.add_agent("weather_expert", "configs/weather_agent.yaml")
app.add_agent("finance_expert", "configs/finance_agent.yaml")

# Start the server with authentication
app.run_server(
    port=5050,
    api_key=True,  # Auto-generate an API key and display it once
    # Or provide a specific key: api_key="sk_muxi_your_custom_key"
)
```

### Client-Server Connection
This scenario demonstrates connecting to a remote MUXI server:

1. **Install the Client Library**

   ```bash
   # Install just the client component
   pip install muxi-cli
   ```

2. **Connect to a Remote Server**

   ```python
   from muxi import muxi

   # Connect to an existing MUXI server
   app = muxi(
       server_url="http://server-ip:5050",
       api_key="sk_muxi_abc123"
   )

   # Use the same API as with local mode
   app.add_agent("remote_assistant", "configs/assistant.yaml")
   response = app.chat("Hello, remote assistant!")
   print(response)
   ```

