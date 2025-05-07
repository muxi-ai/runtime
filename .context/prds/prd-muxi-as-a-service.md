# PRD: MUXI as a Service

## Overview

This PRD outlines the implementation strategy for transforming MUXI from primarily a Python framework into a full-fledged service that can be consumed by developers of any language background. This initiative will make MUXI accessible to a much broader audience while maintaining its power and flexibility for Python developers.

## Objectives

1. Lower the barrier to entry for non-Python developers
2. Provide a Docker-based ready-to-use deployment option
3. Enable fully declarative application configuration
4. Implement persistence for agent configurations
5. Support language-agnostic interaction through SDKs
6. Create a clear migration path to potential cloud offerings

## Background & Strategic Rationale

Currently, MUXI requires Python knowledge to use effectively, limiting adoption to developers familiar with Python ecosystems. Many potential users who could benefit from MUXI's capabilities but work primarily in JavaScript, Go, Java, or other languages face significant adoption barriers.

By offering MUXI as a containerized service with declarative configuration, we can:

1. Expand our user base to include all developers, regardless of language preference
2. Follow industry-standard patterns (Docker, K8s) that developers already understand
3. Enable easier integration into existing technology stacks
4. Create a foundation for potential managed cloud offerings in the future

## Detailed Requirements

### 1. Docker-based Deployment

#### 1.1 Pre-configured Docker Image

- Create an official Docker image containing the complete MUXI framework
- Include all core dependencies pre-installed
- Configure sensible defaults for memory settings, logging, etc.
- Expose necessary ports for HTTP API, WebRTC, and web UI
- Support volume mounts for configuration and persistence

#### 1.2 Environment Variable Configuration

- Support all critical configuration through environment variables
- Include variables for:
  - API keys for LLM providers
  - Authentication settings
  - Memory configuration
  - Logging levels
  - Database connection strings

#### 1.3 Basic Authentication

- Include built-in authentication mechanisms
- Allow configuring admin credentials via environment variables
- Support standard auth mechanisms (API keys, JWT)

### 2. Unified YAML Configuration

#### 2.1 Application-level Configuration

- Design a comprehensive YAML schema that describes an entire MUXI application
- Include sections for:
  - Global settings
  - Orchestrator configuration
  - Memory settings (buffer, long-term)
  - Agent definitions
  - Authentication and access control
  - Logging and tracing preferences

#### 2.2 Configuration Loading

- Load configuration from a mounted volume at startup
- Support hot-reloading when configuration changes
- Validate configuration against a schema
- Provide clear error messages for invalid configurations

#### 2.3 Configuration Examples

- Create comprehensive example configurations for common use cases
- Include templates for:
  - Simple single-agent deployments
  - Multi-agent with specialization
  - Complex enterprise setups with multiple user types

#### 2.4 Backward Compatibility

- Maintain compatibility with existing per-agent YAML configurations
- Support the programmatic API for Python developers
- Allow mixing configuration approaches as needed

### 3. Agent Persistence

#### 3.1 Configuration Persistence

- Store all agent configurations in durable storage
- Support PostgreSQL as the primary persistence layer
- Automatically reload configurations on server restart
- Track configuration changes and maintain version history

#### 3.2 Agent State Management

- Persist agent state between restarts
- Include mechanisms to reset agent state when needed
- Provide APIs to manage agent lifecycle (create, update, delete, restart)

#### 3.3 Backup & Restore

- Include utilities for backing up configurations
- Support restoring from backups
- Enable export/import of agent configurations

### 4. Management Interfaces

#### 4.1 HTTP API

- Develop a comprehensive REST API for agent management
- Include endpoints for:
  - Creating/updating/deleting agents
  - Modifying agent configurations
  - Managing orchestrator settings
  - Monitoring agent status
  - User management

#### 4.2 Command Line Interface

- Create a language-agnostic CLI tool
- Support all agent management functions
- Enable configuration validation
- Include commands for:
  - Starting/stopping agents
  - Updating configurations
  - Monitoring status
  - Managing users and permissions

#### 4.3 Web User Interface

- Enhance the existing web UI for comprehensive management
- Include configuration editors with validation
- Provide dashboards for monitoring agent activity
- Support user management functions

### 5. Multi-language SDKs

#### 5.1 SDK Architecture

- Design a common API surface across all language SDKs
- Use code generation to maintain consistency
- Ensure SDKs follow language-specific idioms and patterns

#### 5.2 Initial SDK Support

- Develop SDKs for:
  - JavaScript/TypeScript (priority)
  - Python (already exists)
  - Go
  - Swift
  - Java

#### 5.3 SDK Features

- Include support for:
  - Agent interaction
  - Agent management
  - Configuration manipulation
  - Authentication
  - WebRTC integration for audio/video

### 6. Documentation & Examples

#### 6.1 Dual-path Documentation

- Restructure documentation homepage to offer two clear paths:
  1. Python Developer (Library Approach)
  2. Service-based Approach (Any Language)

#### 6.2 Tutorials & Examples

- Create language-specific tutorials for all supported SDKs
- Provide Docker deployment examples for various environments
- Include configuration examples for common use cases

#### 6.3 Migration Guides

- Document migration from library to service approaches
- Provide guidance on scaling from development to production

## Technical Architecture

### Container Architecture

```
┌──────────────────────────────────────────────────────┐
│                MUXI Docker Container                 │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐        ┌────────────────────────┐  │
│  │              │        │                        │  │
│  │  MUXI Core   │◄─────►│  Configuration Service  │  │
│  │              │        │                        │  │
│  └──────┬───────┘        └────────────┬───────────┘  │
│         │                             │              │
│         ▼                             ▼              │
│  ┌──────────────┐        ┌────────────────────────┐  │
│  │              │        │                        │  │
│  │ Orchestrator │◄─────►│  Persistence Service   │  │
│  │              │        │                        │  │
│  └──────┬───────┘        └────────────┬───────────┘  │
│         │                             │              │
│         ▼                             ▼              │
│  ┌──────────────┐        ┌────────────────────────┐  │
│  │              │        │                        │  │
│  │  HTTP API    │◄─────►│      PostgreSQL        │  │
│  │              │        │                        │  │
│  └──────┬───────┘        └────────────────────────┘  │
│         │                                            │
│         ▼                                            │
│  ┌──────────────┐        ┌────────────────────────┐  │
│  │              │        │                        │  │
│  │   Web UI     │        │  Volume Mounts:        │  │
│  │              │        │  - Configuration       │  │
│  └──────────────┘        │  - Persistence         │  │
│                          │                        │  │
│                          └────────────────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Configuration Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│             │     │             │     │             │
│  YAML File  │────►│ Config      │────►│ Orchestrator│
│             │     │ Service     │     │             │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │             │     │             │
                    │ Agent       │◄────┤ Agent       │
                    │ Registry    │     │ Instances   │
                    │             │     │             │
                    └──────┬──────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │             │
                    │ PostgreSQL  │
                    │ Storage     │
                    │             │
                    └─────────────┘
```

## YAML Configuration Structure

The unified YAML configuration will follow this structure:

```yaml
# Global MUXI application settings
app:
  name: "My MUXI Application"
  version: "1.0.0"
  description: "A multi-agent system for customer support"

# Orchestrator configuration
orchestrator:
  default_agent: "general-assistant"
  routing_strategy: "capability-match"  # or "round-robin", "direct", etc.
  task_delegation: true

# Memory configuration
memory:
  buffer:
    max_size: 50
    buffer_multiplier: 10
    recency_bias: 0.3
  long_term:
    enabled: true
    connection_string: "${POSTGRES_CONNECTION}"
    max_items: 1000
    summarization: true

# Authentication and access control
auth:
  enabled: true
  admin_key: "${ADMIN_API_KEY}"
  anonymous_access: false
  user_registration: true
  session_expiry: "24h"

# Logging and tracing
logging:
  level: "info"  # debug, info, warn, error
  chain_of_thought: true
  log_file: "/var/log/muxi/application.log"
  request_tracing: true

# Agent definitions
agents:
  - name: "general-assistant"
    description: "General purpose assistant"
    model:
      provider: "anthropic"
      name: "claude-3-opus-20240229"
      api_key: "${ANTHROPIC_API_KEY}"
    system_prompt: |
      You are a helpful AI assistant that provides accurate and concise information.
    capabilities:
      - "general-knowledge"
      - "writing"
      - "summarization"
    memory:
      use_buffer: true
      use_long_term: true
    tools:
      - "web_search"
      - "calculator"
      - "file_manager"

  - name: "customer-support"
    description: "Specialized customer support agent"
    model:
      provider: "openai"
      name: "gpt-4-turbo"
      api_key: "${OPENAI_API_KEY}"
    system_prompt: |
      You are a customer support agent for our product. Help users troubleshoot issues and find information.
    capabilities:
      - "product-knowledge"
      - "troubleshooting"
    knowledge:
      sources:
        - "/app/data/product_docs"
        - "/app/data/faq.json"
      chunk_size: 1000
      overlap: 200
    memory:
      use_buffer: true
      use_long_term: true

# Domain knowledge configuration
knowledge_bases:
  - name: "product-docs"
    description: "Product documentation"
    source_directory: "/app/data/product_docs"
    file_types: ["md", "pdf", "txt"]
    embedding_model:
      provider: "openai"
      name: "text-embedding-3-small"
    index_storage: "/app/data/indexes/product_docs"
```

## Implementation Phases

### Phase 1: Foundation

1. Design and validate the unified YAML configuration schema
2. Implement configuration loading and validation
3. Create the Docker image with core MUXI components
4. Develop the configuration persistence service
5. Update documentation structure for dual-path approach

### Phase 2: Management Interfaces

1. Develop the HTTP API for agent and configuration management
2. Enhance the web UI for configuration editing
3. Create the CLI tool for remote management
4. Implement user authentication and access control
5. Add configuration export/import functionality

### Phase 3: SDK Development

1. Design the common API surface for all SDKs
2. Implement the JavaScript/TypeScript SDK
3. Create the Go SDK
4. Develop the Swift SDK
5. Build the Java SDK
6. Write comprehensive SDK documentation and examples

### Phase 4: Advanced Features & Optimization

1. Implement configuration hot-reloading
2. Add agent state persistence
3. Develop backup and restore utilities
4. Optimize container performance
5. Add monitoring and health check endpoints

## Success Metrics

1. Reduction in time-to-hello-world for new developers
2. Adoption by non-Python developers
3. Number of Docker image pulls
4. SDK downloads across different languages
5. Reduction in support requests related to setup and configuration
6. Feedback from user testing with developers of various language backgrounds

## Future Considerations

1. **Cloud Service**: The containerized approach lays the groundwork for a managed MUXI cloud service
2. **Multi-container Deployments**: Support for Kubernetes-based distributed deployments
3. **Marketplace**: A repository of pre-configured agents that can be imported
4. **Observability**: Integration with popular monitoring tools
5. **Scaling**: Automatic scaling based on traffic patterns

## Appendix

### API Endpoints

The HTTP API will include the following key endpoints:

```
POST   /api/v1/agents                 # Create a new agent
GET    /api/v1/agents                 # List all agents
GET    /api/v1/agents/{name}          # Get agent details
PUT    /api/v1/agents/{name}          # Update agent configuration
DELETE /api/v1/agents/{name}          # Delete an agent
POST   /api/v1/agents/{name}/restart  # Restart an agent

GET    /api/v1/config                 # Get full application configuration
PUT    /api/v1/config                 # Update application configuration
POST   /api/v1/config/validate        # Validate configuration without applying
POST   /api/v1/config/export          # Export configuration
POST   /api/v1/config/import          # Import configuration

GET    /api/v1/orchestrator/status    # Get orchestrator status
POST   /api/v1/orchestrator/restart   # Restart the orchestrator

POST   /api/v1/auth/users             # Create a user
GET    /api/v1/auth/users             # List users
PUT    /api/v1/auth/users/{id}        # Update a user
DELETE /api/v1/auth/users/{id}        # Delete a user
POST   /api/v1/auth/login             # Login
POST   /api/v1/auth/logout            # Logout
POST   /api/v1/auth/token             # Get a new access token
```

### CLI Commands

The CLI will support these commands:

```
muxi-cli login                       # Authenticate with a MUXI server
muxi-cli logout                      # Log out from the MUXI server

muxi-cli config get                  # Get the current configuration
muxi-cli config set                  # Update the configuration
muxi-cli config validate             # Validate a configuration file
muxi-cli config import               # Import a configuration file
muxi-cli config export               # Export the current configuration

muxi-cli agents list                 # List all agents
muxi-cli agents get <name>           # Get agent details
muxi-cli agents create               # Create a new agent
muxi-cli agents update <name>        # Update an agent
muxi-cli agents delete <name>        # Delete an agent
muxi-cli agents restart <name>       # Restart an agent

muxi-cli orchestrator status         # Get orchestrator status
muxi-cli orchestrator restart        # Restart the orchestrator

muxi-cli users list                  # List users
muxi-cli users create                # Create a user
muxi-cli users update <id>           # Update a user
muxi-cli users delete <id>           # Delete a user
```

### Docker Deployment Example

```bash
docker run -d \
  --name muxi-server \
  -p 8000:8000 \
  -p 8080:8080 \
  -v ./config:/app/config \
  -v ./data:/app/data \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -e ADMIN_API_KEY=admin-key-... \
  -e POSTGRES_CONNECTION=postgresql://user:pass@host:port/db \
  muxi/muxi-server:latest
```
