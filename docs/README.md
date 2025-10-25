# MUXI Runtime Documentation

Welcome to the MUXI Runtime documentation. This directory contains comprehensive guides and references for all MUXI features and capabilities.

## 🚀 Quick Start

New to MUXI? Start here:
- **[Scheduler Quick Start](scheduler/quickstart.md)** ⭐ Schedule recurring AI tasks in 5 minutes
- **[Streaming Quick Start](features/streaming-quickstart.md)** - Real-time response streaming
- **[Response Formats Quick Start](features/response-formats-quickstart.md)** - JSON, Markdown, HTML, Text output

## Core Concepts

- [Formation API](api-v1.md) - REST API specification
- [Request Lifecycle](request-lifecycle.md) - Complete request processing flow
- [Memory Systems](memory-systems.md) - Three-tier memory architecture
- [User Synopsis](user-synopsis.md) - Two-tier LLM-synthesized user context caching
- **[Multi-Identity User Management](features/multi-identity.md)** - Multiple identifiers per user with automatic resolution
  - [Quick Start Guide](features/multi-identity-quickstart.md) - Get started in 5 minutes
- [Multi-User Architecture](multi-user-architecture.md) - Multi-tenant design

## System Components

### Formation Management
- [Prompt Management](prompt-management.md) - Centralized prompt system with PromptLoader
- [Clarification System](clarification-system.md) - Intelligent parameter collection
- [User Credentials](user-credentials.md) - Credential handling system
- [Knowledge System](knowledge-system.md) - Domain knowledge architecture

### Workflow & Orchestration
- [Workflow Orchestration](workflow/orchestration.md) - Task decomposition and execution
- [SOP System](workflow/sop-system.md) - Standard Operating Procedures
- [Technical Guide](workflow/technical_guide.md) - Workflow technical details
- [Quick Reference](workflow/quick_reference.md) - Workflow quick reference

### Services

#### Scheduler Service - Automated Task Scheduling
Transform your AI from reactive to proactive:
- **[Quick Start Guide](scheduler/quickstart.md)** ⭐ Get started in 5 minutes with examples
- **[Tutorial](scheduler/tutorial.md)** - Comprehensive step-by-step guide
- **[Common Patterns](scheduler/common-patterns.md)** - Real-world examples from production tests
- **[Usage Guide](scheduler/usage-guide.md)** - Complete feature documentation
- **[Formation API](scheduler/formation-api.md)** - API reference for job management
- **[Architecture](scheduler/architecture.md)** - Technical deep dive
- **[One-time Jobs](scheduler/onetime-jobs.md)** - Single execution scheduling
- **[Audit Trail](scheduler/audit-trail-guide.md)** - Job history and compliance

#### Other Services
- [A2A Communication](a2a/) - Agent-to-agent protocol

### Features
- **[Multi-Identity User Management](features/multi-identity.md)** - Multiple identifiers per user with automatic resolution
  - [Quick Start Guide](features/multi-identity-quickstart.md) - Get started in 5 minutes
- **[LLM Caching](features/llm-caching.md)** - Intelligent response caching with 70%+ cost savings
- **[Streaming Responses](features/streaming.md)** - Real-time response streaming with SSE
  - [Quick Start Guide](features/streaming-quickstart.md) - 5-minute guide to streaming
  - [Troubleshooting Guide](features/streaming-troubleshooting.md) - Common issues and solutions
- **[Response Formats](features/response-formats.md)** - JSON, Markdown, HTML, and Text output formats
  - [Quick Start Guide](features/response-formats-quickstart.md) - 5-minute guide to response formats
  - [Troubleshooting Guide](features/response-formats-troubleshooting.md) - Common issues and solutions
- [Artifacts System](artifacts.md) - File generation and management
- [File Generation](features/file-generation.md) - Built-in file generation

### Configuration
- [Built-in MCPs](configuration/built-in-mcps.md) - Built-in MCP servers
- [Response Formats Config](configuration/response-formats.md) - Format configuration

### MCP Development
- [MCP Transport Guide](mcp/transport-guide.md) - MCP transport implementation
- [MCP Server Development](mcp/) - Building MCP servers

### Security & Credentials
- **[SECURITY.md](SECURITY.md)** - Complete security architecture and credential encryption
  - LLM-based security (prompt injection, credential fishing, jailbreak detection)
  - Credential encryption with PBKDF2 (100k iterations)
  - Salt rotation procedures and best practices
  - PII redaction in observability events
- [User Credentials](user-credentials.md) - Credential handling system
- [Secrets Management](secrets-management.md) - Formation-level secrets

### Developer Guides
- [Type Safety Guide](type-safety-guide.md) - Type checking best practices
- [Observability](observability.md) - Event streaming and monitoring
- [ID Conventions](ID_CONVENTIONS.md) - Identifier naming conventions
- [Licensing](licensing.md) - License information

### Troubleshooting
- [API Discrepancies](api-discrepancies.md) - Known API issues
- [MCP STDIO Fix Summary](mcp-stdio-fix-summary.md) - MCP stdio transport fixes

### Examples
- [Agent Collaboration](agent-collaboration.md) - Multi-agent examples
- [Agent Tool Chaining](agent-tool-chaining.md) - Tool chaining patterns
- [Examples](examples/) - Code examples

## Recent Updates

- **October 2025 (Production Enhancements)**: 
  - ✅ Input validation limits with configurable boundaries
  - ✅ Database query timeouts (30s default)
  - ✅ Workflow max timeout (2-hour hard ceiling)
  - ✅ Configurable credential encryption salt
  - ✅ Automatic PII redaction in observability events
  - ✅ Salt rotation utility for credential security
  - See [SECURITY.md](SECURITY.md) for credential encryption details
- **October 2025**: Added [LLM Caching](features/llm-caching.md) - Intelligent response caching for 70%+ cost savings
- **September 2025**: Added [Prompt Management](prompt-management.md) documentation for centralized prompt system
- **September 2025**: Enhanced clarification system with multilingual support
- **August 2025**: Added scheduler service with natural language scheduling

## Quick Links

- [Main README](../README.md)
- [Test Reports](../tests/reports/)
- [Formation Schemas](../schemas/formation/)
- [Example Formations](../test-formations/)