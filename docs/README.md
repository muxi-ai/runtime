# MUXI Runtime Documentation

## Core Concepts

- [Formation API](api-v1.md) - REST API specification
- [Request Lifecycle](request-lifecycle.md) - Complete request processing flow
- [Memory Systems](memory-systems.md) - Three-tier memory architecture
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
- [Scheduler Architecture](scheduler/architecture.md) - Task scheduling system
- [Scheduler Usage Guide](scheduler/usage-guide.md) - How to use the scheduler
- [One-time Jobs](scheduler/onetime-jobs.md) - Scheduling single execution tasks
- [A2A Communication](a2a/) - Agent-to-agent protocol

### Features
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

- **September 2025**: Added [Prompt Management](prompt-management.md) documentation for centralized prompt system
- **September 2025**: Enhanced clarification system with multilingual support
- **August 2025**: Added scheduler service with natural language scheduling

## Quick Links

- [Main README](../README.md)
- [Test Reports](../tests/reports/)
- [Formation Schemas](../schemas/formation/)
- [Example Formations](../test-formations/)