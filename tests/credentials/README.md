# Credential System Tests

This directory contains comprehensive tests for the MUXI user credential system.

## Test Organization

### Main Tests
- `test_complete_system.py` - Complete integration test with database operations
- `test_flow_triggering.py` - Tests the clarification flow triggering from Agent to Overlord
- `test_edge_cases.py` - Edge cases like empty values, special characters, concurrent access
- `test_summary_credential_system.py` - Summary of what's been tested

### Supporting Tests
- `test_credential_minimal.py` - Minimal test of core logic without imports
- `test_credential_generic.py` - Demonstrates the generic approach
- `test_overlord_credential_flow.py` - Explains the complete flow

### Debug Files
- Various debug files for troubleshooting specific issues

## Running Tests

### Run all main tests:
```bash
python test_all.py
```

### Run individual tests:
```bash
python test_complete_system.py
python test_flow_triggering.py
```

## What's Tested

✅ **Credential Handler**
- Service name formatting (github → GitHub)
- Field name determination
- Request generation
- Response parsing
- Validation

✅ **Credential Resolver**
- Database operations (store, retrieve, delete)
- Case-insensitive service names
- User isolation
- Formation isolation
- Caching

✅ **Clarification Flow**
- MissingCredentialError handling
- Agent → Overlord flow
- User response processing

✅ **Integration**
- End-to-end flow
- MCP placeholder resolution
- Concurrent access

## Key Features

- **Generic System**: No hardcoded service configurations
- **Case Insensitive**: GitHub, github, GITHUB all work
- **User Isolation**: Each user has their own credentials
- **Formation Isolation**: Credentials scoped to formations
- **Runtime Resolution**: Credentials resolved when needed, not at config time

## Dependencies

- SQLAlchemy with async support
- aiosqlite for testing
- Python 3.8+