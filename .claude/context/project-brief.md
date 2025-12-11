# MUXI Framework Project Brief

## Project Overview

MUXI Runtime is the **container runtime for AI agents** - the low-level execution engine that powers AI agent formations inside the MUXI AI Server. It transforms declarative YAML configurations into living, breathing AI systems, handling all the complex orchestration, memory management, and tool integration that production AI applications require.

Think of MUXI Runtime as what makes AI agents actually work - like how container runtimes execute Docker images, MUXI Runtime executes AI formations. It provides the foundational layer for agent lifecycle management, intelligent routing, memory systems, and external tool integration through the Model Context Protocol (MCP).

## Core Philosophy

> **Give developers powerful primitives to build structured, composable, and observable agent architectures — with full control over models, memory, and logic.**

MUXI addresses the fundamental infrastructure gap in AI agent development by providing unified framework handling infrastructure concerns (memory, models, tools, multi-user support) while providing flexibility for business logic and user experience.

## Key Components

### 1. **Core Runtime Components**
The foundational execution engine providing:
- **Formation Engine**: Loads and validates YAML configurations as live AI systems
- **Overlord Orchestrator**: Intelligent message routing and agent coordination with SOP guidance
- **Agent Framework**: Flexible agent implementation with specialized capabilities and knowledge systems
- **Memory Systems**: Three-tier architecture (buffer, persistent, vector) with FIFO cleanup and multi-user isolation
- **MCP Protocol**: Full implementation supporting 1,000+ external tools via command, HTTP/SSE, and streamable transports
- **Built-in MCPs**: File Generation (Artifacts System) for secure creation of charts, documents, and code

### 2. **MUXI AI Server** (The AI Agent Daemon)
The always-on multi-modal daemon that hosts and manages Agent formations:
- **Formation Runtime**: Executes formation files as live AI systems
- **Multi-Protocol API**: REST, Server-Sent Events, WebRTC, MCP, and Webhooks
- **Multi-Modal Support**: Handle text, image, audio, video, and document content
- **Unified Authentication**: Consistent security across all protocols
- **Multi-Tenant Support**: Support for multiple users and formations
- **Production Ready**: Built for enterprise deployment from day one

### 3. **Formation System** (Declarative AI System Definition)
YAML files that define complete AI systems, similar to Dockerfiles for containers:
- **Declarative Specification**: Define agents, memory, MCP servers, and configuration
- **Portable Deployment**: Deploy the same formation to any MUXI server
- **Version Control**: Track changes and manage AI system evolution
- **Template System**: Reusable components and inheritance
- **Environment Variables**: Configure for different deployment environments

### 4. **MUXI CLI** (Formation Management Interface)
Command-line tool for managing formations, like Docker CLI for containers:
- **Formation Lifecycle**: `muxi push`, `muxi pull`, `muxi start`, `muxi stop`
- **Agent Management**: Add, remove, and configure agents within formations
- **MCP Management**: Deploy and manage MCP servers and tools
- **Live Updates**: Modify running formations without downtime

## Core Runtime Features

1. **Formation Execution**: Transform YAML configurations into living AI systems
2. **Intelligent Orchestration**: Overlord routes messages to appropriate agents based on intent and context
3. **Memory Management**: Three-tier memory with buffer, persistent storage, and vector search
4. **Tool Integration**: MCP protocol for accessing 1,000+ external tools and services
5. **Knowledge Systems**: Agent-specific domain knowledge with intelligent caching
6. **Security & Isolation**: Multi-user support with credential encryption and data isolation
7. **Production Ready**: Async operations, webhook delivery, and comprehensive observability

## Technical Architecture

### Docker-Like Paradigm
| Docker Concept | MUXI Equivalent | Benefit |
|---------------|-----------------|---------|
| **Dockerfile** | **formation.afs** | Declarative, version-controlled AI system definition |
| **Docker Image** | **Formation Registry** | Shareable, reusable AI system templates |
| **Docker Container** | **Running Formation** | Live AI system with isolated resources |
| **Docker Daemon** | **MUXI Server** | Always-on service managing AI systems |
| **Docker CLI** | **MUXI CLI** | Command-line management interface |

### Multi-Repository Architecture
- **muxi/runtime**: Foundational agent framework (Overlord, Agents, Memory)
- **muxi/server**: API server with REST, SSE, WebRTC, MCP protocols
- **onellm**: Provider-agnostic LLM library (formerly MUXI LLM)
- **faissx**: Distributed FAISS vector database service
- **muxi/cli**: Command-line interface for formation management
- **muxi/schemas**: Configuration schemas for formations, agents, MCP servers

## Current Development Status

### ✅ Completed Features (Production Ready)
- **Formation System**: Complete YAML loading, validation, and execution
- **Overlord Orchestration**: Intelligent routing with intent detection and SOP support
- **Memory Systems**: Buffer (FIFO + vector), persistent (PostgreSQL/SQLite), multi-user isolation
- **MCP Protocol**: Full implementation with tool discovery, execution, and multiple transports
- **Built-in MCPs**: Artifacts System for secure file generation with sandboxed Python execution
- **Knowledge System**: Agent-level domain knowledge with MarkItDown support and MD5 caching
- **User Credentials**: Secure per-user credential storage with encryption and isolation
- **Multimodal Support**: Text, image, audio, video, and document processing via unified services
- **Async Operations**: Production-ready async request-response with webhook delivery
- **Observability**: Comprehensive event streaming with 10 formatters and 4 transports
- **A2A Communication**: Internal and external agent-to-agent collaboration
- **Task Scheduling**: Natural language scheduling for recurring and one-time tasks

### 🚧 In Progress
- **Standard Operating Procedures (SOPs)**: Enhanced task decomposition with procedural guidance
- **Multiple Clarification Sequences**: Stack-based clarification management
- **Thinking Visibility**: Automatic model detection with configurable transparency
- **Large File Processing**: Intelligent chunking for >100MB multimodal files

### 📋 Planned Enhancements
- **Performance Optimization**: Target <2s simple queries, <30s complex workflows
- **Enhanced Caching**: Distributed cache for formations and embeddings
- **Advanced Monitoring**: Distributed tracing and performance profiling
- **Extended LLM Support**: Additional providers via OneLLM

## Project Scope

### In Scope

**Phase 1: Runtime Completion**
- Finalize runtime components and optimizations
- Complete A2A communication protocol
- Enhance observability with tracing capabilities
- Performance optimizations and stability improvements

**Phase 2: Server Development**
- Formation execution runtime using runtime
- Multi-protocol API implementation (REST, SSE, WebRTC, MCP, Webhooks)
- Authentication and multi-user support
- Production deployment features

**Phase 3: Developer Tools**
- CLI for formation management and deployment
- Formation registry for template sharing
- Visual formation builder (future)
- Comprehensive documentation and examples

**Phase 4: Ecosystem Expansion**
- Language-specific SDKs (TypeScript, Go, Java, etc.)
- Additional OneLLM providers (Anthropic, Google, xAI, etc.)
- Advanced observability and monitoring
- Enterprise features and integrations

### Out of Scope

- Training custom LLM models (use existing providers)
- Hardware-specific optimizations
- Mobile-specific interfaces (use standard APIs)
- Enterprise IAM beyond standard protocols
- Autonomous agent governance (future consideration)

## Success Metrics

1. **Performance**: <2s response time for simple queries, <30s for complex workflows
2. **Memory Efficiency**: <100MB growth per 100 conversations
3. **Concurrent Users**: 1,000+ per instance with proper isolation
4. **Knowledge Performance**: 45% cache hit rate, 10x faster cached loads
5. **Test Coverage**: 100% success rate across 6 days of comprehensive testing
6. **Cost Optimization**: 70% reduction through intelligent caching

## Target Use Cases

- **Customer Service**: Multi-agent support systems with specialized routing
- **Development Assistance**: Code generation, review, and documentation automation
- **Content Creation**: Research, writing, and multi-modal content generation
- **Business Intelligence**: Data analysis, reporting, and decision support
- **Enterprise Integration**: AI-powered workflows and process automation

## License

The project will be released under MIT license to encourage ecosystem adoption and community contribution while maintaining compatibility with enterprise usage.
