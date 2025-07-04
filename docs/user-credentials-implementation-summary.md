# User Credentials Implementation Summary

**Date:** January 30, 2025
**Status:** Implemented (Refactored to execution-time resolution)

## Overview

Implemented user-specific credential resolution for MCP servers and other services, allowing them to access external resources on behalf of individual users using the syntax `${{ user.credentials.SERVICE }}`.

## Key Features Implemented

### 1. Formation Validation
- Added `validate_user_credentials_requirements()` function in `src/muxi/runtime/formation/config/validation.py`
- Validates that persistent database storage is configured when user credentials are used
- Raises clear error messages guiding users to configure database

### 2. Credential Resolver Service
- Created new service in `src/muxi/runtime/formation/memory/`
- `CredentialResolver` class handles runtime credential resolution
- Features:
  - Case-insensitive service names (GitHub, github, GITHUB all resolve to "github")
  - In-memory caching to avoid repeated database queries
  - Database-agnostic using JSONType (works with PostgreSQL and SQLite)
  - Async SQLAlchemy patterns throughout

### 3. MCP Integration
- Updated `MCPCoordinator` to support user credential resolution
- Added `_resolve_user_credentials()` method to handle placeholders
- Added `resolve_mcp_auth_for_execution()` method for runtime resolution
- Credentials are resolved at tool execution time when user context is available

### 4. Overlord Integration
- Credential resolver is initialized in Overlord when database is configured
- Uses formation_id_hash for data isolation between formations
- Integrated with existing services architecture

### 5. Database Manager Updates
- Ensured `db_manager` is properly initialized for all persistent memory types
- Fixed initialization for SQLite, PostgreSQL, and Memobase backends
- Database manager is required for credential storage

## Usage Example

### Formation Configuration
```yaml
mcp:
  servers:
    - id: github-api
      type: http
      endpoint: https://api.github.com
      auth:
        token: "${{ user.credentials.github }}"  # Resolved at runtime per user
```

### Runtime Behavior
1. MCP servers are registered with placeholder auth at formation startup
2. When a tool is invoked with user context, credentials are resolved
3. If credentials are missing, `MissingCredentialError` is raised
4. This triggers the clarification flow to request credentials from the user
5. Credentials are stored in the database and cached for the session
6. The MCP connection is re-established with resolved credentials if needed

## Technical Details

### Database Schema
Uses existing `credentials` table:
- `service` field is always lowercase for consistency
- Supports both PostgreSQL (JSONB) and SQLite (TEXT with JSON)
- Formation isolation via `formation_id_hash`

### Resolution Order
1. Formation-wide secrets (`${{ secrets.* }}`) - resolved at config load time
2. User credentials (`${{ user.credentials.* }}`) - resolved at runtime

### Error Handling
- `MissingCredentialError` extends `FormationError`
- Provides service name and user_id for clarification flow
- Clear validation errors if database not configured

## Testing

Created comprehensive tests in `test_user_credentials.py`:
- ✅ Validation fails without database configured
- ✅ Validation passes with database configured
- ✅ Credential resolver properly initialized
- ✅ Case-insensitive service names work correctly
- ✅ Missing credentials raise appropriate errors

Additional tests:
- `test_credential_generic.py` - Demonstrates the generic approach
- `test_credential_clarification.py` - Tests clarification flow
- `test_credential_clarification_simple.py` - Unit tests for handler

## Next Steps

1. ✅ Implement clarification flow integration for credential collection
2. ✅ Create database indexes for performance
3. Add credential management endpoints (list, update, delete) 
4. Add support for complex credential types (OAuth flows, multi-field auth)
5. Create Day 4 MCP tests with user credentials

## Recent Updates (2025-01-30)

### Database Indexes Added
- Created migration script: `migrations/add_credential_indexes.py`
- Adds indexes: `idx_credentials_user_service`, `idx_credentials_user_formation`, `idx_credentials_service_lower`
- Supports both PostgreSQL and SQLite with appropriate syntax

### Clarification Flow Implemented
- Created `CredentialClarificationHandler` in `src/muxi/runtime/formation/clarification/credential_handler.py`
- Added `handle_missing_credential` method to Overlord
- Added `process_credential_clarification_response` method to handle user responses
- Integrated with existing clarification system

**Generic Approach**: The system now uses a fully generic approach without any hardcoded service configurations:
- Works with ANY service name (no maintenance required)
- Intelligently formats service names (e.g., `github` → `GitHub`, `my_api` → `My Api`)
- Determines credential field names based on simple heuristics
- Minimum 8 character validation for all credentials
- LLM can provide service-specific guidance when needed

The clarification flow now works as follows:
1. Agent catches `MissingCredentialError` during tool execution
2. Agent calls `overlord.handle_missing_credential()` 
3. Overlord generates appropriate clarification request using generic handler
4. User provides credential in response
5. Overlord stores credential and retries the operation

## Files Modified

- `/src/muxi/runtime/formation/config/validation.py` - Added user credential validation
- `/src/muxi/runtime/formation/formation.py` - Added validation call and imports
- `/src/muxi/runtime/formation/overlord/overlord.py` - Added credential resolver initialization
- `/src/muxi/runtime/formation/overlord/mcp_coordinator.py` - Added credential resolution methods
- `/src/muxi/runtime/formation/initialization.py` - Fixed db_manager initialization
- `/src/muxi/runtime/formation/memory/credential_resolver.py` - New credential resolver implementation
- `/src/muxi/runtime/services/mcp/service.py` - Added user_id and credential resolution to invoke_tool
- `/src/muxi/runtime/formation/agents/agent.py` - Pass user_id and credential resolver to MCP tools
- `/schemas/formation/README.md` - Updated documentation

## Key Design Decisions

1. **Execution-Time Resolution**: User credentials are resolved at tool execution, not server registration
2. **Case Insensitivity**: Service names normalized to lowercase for consistency
3. **Caching Strategy**: In-memory cache per session, cleared on credential updates
4. **Error Strategy**: Missing credentials trigger clarification, not silent failures
5. **Database Requirement**: Persistent storage required when user credentials are used
6. **Dynamic Reconnection**: MCP connections are re-established with resolved credentials when needed
7. **User Context Propagation**: Agents track current user_id and pass it to tool invocations
