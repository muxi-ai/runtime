# Day 4: MCP Integration & User Credentials - Test Mapping

## Overview
This document maps the Day 4 test plan requirements to actual test implementations.

## Test Groups and Files

### Group 4A: Single MCP Server (2 tests + 3 tool chaining variants) 
1. **test_4a1_filesystem_mcp_operations.py** - Filesystem MCP CRUD operations
   - Create file operation
   - Read file operation
   - Update file operation
   - Delete file operation

   **Tool Chaining Variants (3 tests):**
   - **test_4a1_variant_1_existing_dir.py** - File creation in existing directory
   - **test_4a1_variant_2_missing_dir.py** - File creation with automatic directory creation
   - **test_4a1_variant_3_explicit.py** - File creation with explicit directory instruction

2. **test_4a2_system_info_mcp.py** - System information retrieval
   - CPU usage monitoring
   - Memory statistics
   - System resource information

### Group 4B: Multi-MCP Integration (3 tests)
1. **test_4b1_complex_multi_mcp_workflow.py** - Linear → System → GitHub → Linear
   - Create Linear issue
   - Get system CPU usage
   - Create GitHub gist with data
   - Update Linear issue with gist link

2. **test_4b2_file_system_coordination.py** - File + System Info coordination
   - Check system memory usage
   - Create file with system stats
   - Verify multi-MCP coordination

3. **test_4b3_mcp_failure_handling.py** - Error handling and recovery
   - Permission denied handling
   - Invalid path handling
   - Graceful error messages

### Group 4C: Linear MCP Operations (3 tests)
1. **test_4c1_create_linear_issue.py** - Issue creation via formation secrets
   - Create issue with title and description
   - Verify issue creation response
   - Use formation-level Linear API token

2. **test_4c2_update_linear_issue.py** - Issue status updates
   - Update issue to in-progress
   - Verify update confirmation
   - Test status transitions

3. **test_4c3_list_linear_issues.py** - Issue listing and retrieval
   - List recent Linear issues
   - Verify issue data retrieval
   - Test pagination/filtering

### Group 4D: GitHub MCP with User Credentials (4 tests)
1. **test_4d1_user1_github_credentials.py** - User with existing credentials
   - Create GitHub gist successfully
   - Use stored user credentials
   - Verify gist creation

2. **test_4d2_user2_credential_flow.py** - User without credentials
   - Trigger clarification flow
   - Request credential input
   - Handle missing credentials gracefully

3. **test_4d3_list_user_gists.py** - List user's GitHub gists
   - Retrieve user1's gists
   - Verify gist listing
   - Use user-specific credentials

4. **test_4d4_create_github_issue.py** - Create GitHub repository issue
   - Create issue in piepilot org
   - Use user credentials for auth
   - Verify issue creation

### Group 4E: User Credential Isolation (2 tests)
1. **test_4e1_verify_user_isolation.py** - Cross-user credential protection
   - User2 cannot use User1's credentials
   - Proper credential scoping
   - Security validation

2. **test_4e2_multiple_users_permissions.py** - Private content isolation
   - User1 creates private content
   - User2 cannot access even with own credentials
   - MCP-level isolation verification

## Summary

**Total Tests:** 18 MCP tests + credential flow validation
- Single MCP Server: 2 tests + 3 tool chaining variants
- Multi-MCP Integration: 3 tests
- Linear MCP (Formation Secrets): 3 tests
- GitHub MCP (User Credentials): 4 tests
- User Credential Isolation: 2 tests

**Key Testing Areas:**
- MCP tool discovery and invocation
- Agent tool chaining and intelligent error recovery
- Multi-server coordination
- Formation-level secrets (Linear)
- User-level credentials (GitHub)
- Security and isolation
- Error handling and recovery

## Pre-requisites

1. **MCP Servers Required:**
   - Filesystem MCP (command transport)
   - System Info MCP (command transport)
   - Linear MCP (HTTP/SSE transport) - requires `LINEAR_MCP_TOKEN` in formation secrets
   - GitHub MCP (HTTP/streamable transport) - requires user credentials

2. **Test Users:**
   - User1: Has GitHub credentials pre-configured in database
   - User2: No GitHub credentials (will trigger clarification flow)

3. **Formation:**
   - `test-formations/formation-mcp` with all MCP servers configured
   - Proper secrets.enc file with Linear API token
   - User credentials in database for User1

## Notes

- All tests use real MCP servers, not mocks
- Tests verify actual tool execution and results
- Credential flow tests ensure proper security isolation
- Multi-MCP tests validate complex orchestration scenarios