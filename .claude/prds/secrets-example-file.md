---
name: secrets-example-file
description: Automatically generate and maintain a secrets.example file documenting all secrets required by a formation
status: backlog
created: 2025-08-19T15:33:52Z
---

# PRD: secrets-example-file

## Executive Summary

Automatically generate and maintain a `secrets.example` file that documents all secrets required by a formation, providing developers with a clear template of what secrets they need to configure when receiving or deploying a formation. This self-documenting approach transforms secret management from a source of confusion into clear documentation.

## Problem Statement

Currently, when developers share formations:
- Recipients don't know what secrets are required without the encryption key
- No clear documentation of which secrets are used where
- No way to identify unused secrets in `secrets.enc`
- Manual secret documentation quickly becomes outdated
- Developers resort to trial-and-error or reading through YAML configs

This leads to increased setup time, runtime errors from missing secrets, and difficulty debugging secret-related issues.

## User Stories

### Primary Personas

1. **Formation Developer**
   - As a formation developer, I want my formations to self-document their secret requirements so recipients know exactly what they need to configure
   - Acceptance: Auto-generated secrets.example file listing all required secrets

2. **Formation Recipient**
   - As a developer receiving a formation, I want to quickly understand what secrets I need to provide without decrypting or parsing YAML
   - Acceptance: Clear .env-style template with usage context

3. **DevOps Engineer**
   - As a DevOps engineer, I want to know which secrets are used where for auditing and rotation purposes
   - Acceptance: Comments showing exact configuration paths for each secret

### User Journeys

1. **Sharing a Formation**
   - Developer creates formation with various API integrations
   - System automatically generates secrets.example
   - Developer shares formation with secrets.enc and secrets.example
   - Recipient immediately sees required secrets without decryption

2. **Dynamic Configuration**
   - Developer adds new MCP server via API at runtime
   - System detects new secret requirements
   - Regenerates secrets.example with new entries
   - Documentation stays current with actual usage

## Requirements

### Functional Requirements

**Core Features:**
- Scan all formation configurations for secret references (`${{ secrets.KEY }}` pattern)
- Generate .env-format secrets.example file with empty placeholders
- Include usage comments showing where each secret is used
- Update automatically on formation lifecycle events
- Support all configuration sections (agents, MCP, A2A, database, etc.)

**User Interactions:**
- File generated automatically without user intervention
- Developers can copy as template: `cp secrets.example .env`
- Future: CLI commands for import/export operations
- Future: Interactive setup wizard

### Non-Functional Requirements

**Performance:**
- Generation completes in <100ms for typical formations
- No performance impact on formation startup
- Efficient regex scanning of configurations

**Security:**
- Never include actual secret values
- Safe to commit to version control
- No sensitive information in usage paths
- Read-only generation (always regenerated, never edited)

**Scalability:**
- Handle formations with 100+ secrets
- Support deep nested configurations
- Efficient memory usage for large config trees

## Success Criteria

### Measurable Outcomes
- **Setup time reduction**: 80% faster initial configuration for new developers
- **Runtime error reduction**: 90% fewer missing secret errors
- **Documentation accuracy**: 100% match between example and actual usage
- **Developer satisfaction**: Positive feedback on self-documenting nature

### Key Metrics
- Time to configure new formation: <5 minutes
- Number of secret-related support tickets: 50% reduction
- Formation sharing success rate: 95% work on first try
- Documentation staleness: Always current (0 days)

## Constraints & Assumptions

### Technical Constraints
- Must use flat key structure (no nested secrets)
- Limited to regex pattern matching for secret detection
- File I/O operations for generation
- Python 3.10+ requirement

### Assumptions
- Developers familiar with .env format
- Secrets follow naming convention (UPPER_SNAKE_CASE)
- Formation configurations use standard secret reference pattern
- Secrets directory exists and is writable

## Out of Scope

Explicitly NOT building:
- Actual secret value storage or encryption
- Secret validation or format checking
- Integration with external secret managers (AWS, Vault)
- Automatic secret rotation
- Secret value generation or suggestions
- Multi-environment secret management
- Nested or hierarchical secret structures

## Dependencies

### Internal Dependencies
- Formation loading system
- Configuration parser
- Secrets manager module
- File system access

### External Dependencies
- No external services required
- No additional Python packages needed
- Uses only standard library components

## Implementation Plan

### Phase 1: Core Implementation (Week 1)
- SecretUsageTracker class for tracking usage
- ConfigSecretScanner for regex-based scanning
- SecretsExampleGenerator for file generation
- Integration with Formation class

### Phase 2: Lifecycle Integration (Week 1)
- Hook into formation initialization
- Trigger on dynamic agent/MCP additions
- Handle configuration hot-reload
- Comprehensive test coverage

### Phase 3: CLI Integration (Future)
- Import command: `muxi secrets import .env`
- Export command: `muxi secrets export`
- Setup wizard: `muxi secrets setup`

### Phase 4: Enhanced Features (Future)
- Secret validation patterns
- Multi-environment support
- Integration with external managers

## Technical Design

### Architecture
```
Formation Config → Secret Scanner → Usage Tracker → Example Generator
                        ↓                ↓                ↓
                  Regex Matching    Usage Map      .env Format File
```

### Key Components

1. **SecretUsageTracker**: Maintains map of secret_key → usage_paths
2. **ConfigSecretScanner**: Recursively scans configs with regex
3. **SecretsExampleGenerator**: Produces .env-format output
4. **Formation Integration**: Hooks for lifecycle events

### File Format Example
```bash
# Auto-generated secrets in use by this formation
# Generated: 2025-01-11 10:30:00

# Used by: mcp.github.auth.token
GITHUB_TOKEN=

# Used by: agents.code-expert.llm.api_key
OPENAI_API_KEY=

# Used by: agents.research.llm.api_key, agents.code.llm.fallback_key
ANTHROPIC_API_KEY=
```

## Testing Strategy

### Unit Tests
- Secret pattern matching accuracy
- Configuration traversal completeness
- File generation format validation
- Usage tracking correctness

### Integration Tests
- Formation lifecycle integration
- Dynamic configuration updates
- Multi-section scanning
- File system operations

### End-to-End Tests
- Complete flow from config to file
- Real formation configurations
- Runtime API additions
- Hot-reload scenarios

## Documentation Requirements

### User Documentation
- How secrets.example works
- Using the generated file
- Understanding usage comments
- Troubleshooting guide

### Developer Documentation
- Integration points
- Extending scanner patterns
- Adding new configuration sections
- Performance considerations

## Risk Mitigation

### Identified Risks
1. **Regex pattern changes**: Mitigate with comprehensive pattern tests
2. **Performance degradation**: Implement caching for large configs
3. **File system errors**: Graceful fallback without blocking formation
4. **Breaking changes**: Version the file format for compatibility

## Summary

The secrets-example-file feature transforms MUXI Runtime's secret management from a source of confusion into clear, self-documenting configuration. By automatically tracking and documenting secret usage throughout the formation lifecycle, we eliminate guesswork when sharing or deploying formations. The familiar .env format ensures universal developer compatibility while usage comments provide valuable debugging context. This foundational improvement will significantly reduce setup time, prevent runtime errors, and enhance the overall developer experience with MUXI Runtime formations.