# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MUXI Runtime is the computational engine for executing AI agent formations. It follows a Docker-like paradigm where Formation YAML files define AI systems that run as live formations, similar to how Dockerfiles create containers.

Key architectural pattern: **Formation-Services-Overlord**
- **Formation**: Manages operational lifecycle and hot deployment
- **Services**: Unified service architecture for all capabilities
- **Overlord**: Intelligent decision-making and agent coordination

## Common Development Commands

```bash
# Installation
pip install -e .                      # Development installation

# Testing
python run_tests.py                   # Run all tests
python run_version_tests.sh           # Version-specific tests
pytest                                # Standard pytest execution
pytest tests/test_specific.py         # Run specific test file

# Code Quality
flake8 src/                          # Lint code (max line length: 120)
pyright                              # Type checking

# Secrets Management (Development)
python src/muxi/runtime/utils/add_secret.py <formation_path> <SECRET_NAME> "<value>"
python src/muxi/runtime/utils/delete_secret.py <formation_path> <SECRET_NAME>
python src/muxi/runtime/utils/add_secret.py <formation_path> list  # List secrets
```

## Architecture Guidelines

### Core Directory Structure

```
src/muxi/runtime/
├── datatypes/          # Unified data structures - ALL services use these types
├── formation/          # Formation orchestration - manages lifecycle, NOT intelligence
├── services/           # Unified services - ALL reusable capabilities live here
└── utils/              # Runtime utilities
```

### Key Architectural Rules

1. **Formation-Overlord Separation**: Formation handles operations, Overlord handles intelligence. Never mix concerns.

2. **Services Architecture**: ALL reusable capabilities must be in `services/`. No service code in `formation/`.

3. **MCP Integration**: Use the centralized MCPService singleton pattern:
   ```python
   mcp_service = await overlord.get_mcp_service()
   ```

4. **Hot Deployment**: Agents and MCP servers can be added/removed at runtime without restart.

5. **Memory Systems**: Use buffer memory with FIFO cleanup. Long-term storage uses vector search.

6. **Async Patterns**: Use anyio/asyncio for all async operations. Support streaming responses.

7. **Error Handling**: Use unified error types from `datatypes/errors.py`.

## Formation YAML Structure

Formations define AI systems with:
- **agents**: List of AI agents with models, roles, and specialties
- **mcp_servers**: External tool integrations via Model Context Protocol
- **memory**: Buffer and long-term memory configurations
- **secrets**: Encrypted credentials using `${{ secrets.KEY_NAME }}` syntax

## Testing Patterns

- Unit tests for individual components
- Integration tests for Formation-Overlord interaction
- MCP server connection tests with timeouts
- Memory system tests with cleanup verification
- Async operation tests with webhook simulations

## Security Considerations

- Never commit secrets - use the encrypted secrets system
- Use AES-256-GCM encryption for all sensitive data
- Validate all agent configurations before deployment
- Sanitize MCP server responses
- Use role-based access control for agent capabilities

## Recent Changes (Important)

1. **Architectural Transformation**: Complete refactor to Formation-Services-Overlord pattern
2. **Hot Agent Deployment**: Runtime agent management without restart
3. **Services Consolidation**: All capabilities moved to unified services architecture
4. **ZeroMQ Encryption**: Token-based encryption for distributed deployments
5. **Legacy API Removal**: No backward compatibility - use new patterns only

## Common Workflows

### Adding a New Service
1. Create service in `services/<service_name>/`
2. Define data types in `datatypes/`
3. Integrate with Formation configuration
4. Add to Overlord's service initialization

### Implementing Agent Capabilities
1. Use existing services - don't create new ones in agents/
2. Connect through MCPService for tools
3. Use memory services for state
4. Handle multi-modal content via multimodal services

### Debugging Tips
- Check Formation validation errors first
- Verify MCP server connectivity
- Monitor memory buffer cleanup
- Use observability services for tracing
- Check encrypted secrets are properly loaded

## Performance Considerations

- Parallel execution for independent tasks
- Connection pooling for MCP servers
- Vector search optimization for memory
- Streaming responses for real-time interaction
- Circuit breakers for resilience

## Integration Points

- **OneLLM**: Provider-agnostic LLM interface
- **FAISSx**: Distributed vector search
- **A2A SDK**: Agent-to-agent communication
- **MCP**: Model Context Protocol for tools
- **SQLite-vec**: Local vector search option
