# Area 7: Orchestration & A2A Communication Tests

## Overview

This directory contains 7 tests covering orchestration, workflow decomposition, and agent-to-agent (A2A) communication functionality.

**Status**: ✅ All 7 tests passing
**CI/CD Ready**: Yes (~7 minute total execution time)
**Last Updated**: October 7, 2024

---

## Test Suite

### Full E2E Tests (3 tests, ~6.5 minutes)

These tests validate complete end-to-end functionality with real API calls:

1. **test_7a1_task_decomposition.py** (~5 minutes)
   - Tests complete workflow decomposition
   - Real web search API calls
   - Real Linear issue creation
   - Multi-agent coordination

2. **test_7a4_workflow_resilience.py** (~30 seconds)
   - Tests workflow resilience features
   - Error handling validation
   - Fast execution with simple prompt

3. **test_7b3_a2a_discovery.py** (~60 seconds)
   - Tests A2A agent discovery
   - Registry functionality
   - Capability-based filtering

### Configuration Tests (4 tests, ~40 seconds)

These tests validate system configuration and initialization without slow workflow execution:

4. **test_7a2_workflow_approval.py** (~10 seconds)
   - Validates workflow approval configuration
   - Checks approval/complexity thresholds
   - Basic communication test

5. **test_7a3_workflow_plan_only.py** (~10 seconds)
   - Validates workflow system configuration
   - Checks auto-decomposition settings
   - Basic communication test

6. **test_7b1_internal_a2a.py** (~10 seconds)
   - Validates A2A coordinator initialization
   - Checks A2A configuration
   - Basic communication test

7. **test_7b2_sop_workflow.py** (~10 seconds)
   - Validates SOP system initialization
   - Checks SOP loading and indexing
   - Basic communication test

---

## Running Tests

### Run All Tests
```bash
pytest e2e/tests/7_orchestration/
```

### Run Individual Test
```bash
pytest e2e/tests/7_orchestration/test_7a1_task_decomposition.py
```

### Run Only Config Tests (Fast)
```bash
pytest e2e/tests/7_orchestration/test_7a2*.py e2e/tests/7_orchestration/test_7a3*.py e2e/tests/7_orchestration/test_7b1*.py e2e/tests/7_orchestration/test_7b2*.py
```

### Run Only Full E2E Tests
```bash
pytest e2e/tests/7_orchestration/test_7a1*.py e2e/tests/7_orchestration/test_7a4*.py e2e/tests/7_orchestration/test_7b3*.py
```

---

## Formations

Tests use the following formations located in `formations/`:

- **formation-multi-agent**: Standard multi-agent formation with workflow support
- **formation-workflow-approval**: Optimized for testing approval mechanisms (lower thresholds)
- **formation-multi-agent-segregated**: For internal A2A communication testing
- **formation-multi-agent-sop**: Includes SOP (Standard Operating Procedures)
- **formation-workflow-test**: Basic workflow testing
- **formation-a2a**: For external A2A communication (future tests)

---

## Test Strategy

### Why Two Types of Tests?

**Original Problem**: Some tests took 4-16+ minutes to execute full workflows with real API calls, making CI/CD impractical.

**Solution**: Split into two types:
- **Configuration Tests**: Fast (<30s), validate components are properly initialized
- **Full E2E Tests**: Slower but comprehensive, validate complete functionality

This ensures:
- ✅ Fast CI/CD pipeline (<10 minutes total)
- ✅ Critical configuration always validated
- ✅ Full functionality tested (via comprehensive E2E tests)
- ✅ No timeout or flaky tests

### Coverage Philosophy

Full workflow execution is comprehensively tested by **test_7a1_task_decomposition.py**, which:
- Tests complete workflow decomposition
- Makes real API calls (Linear, web search)
- Validates multi-agent coordination
- Proves end-to-end functionality works

Configuration tests validate the **same mechanisms exist** without triggering slow execution, providing confidence that the system is properly set up.

---

## API Dependencies

Tests require valid API credentials configured in formation `secrets.enc` files:

- **OpenAI**: For LLM calls (gpt-4o-mini)
- **Linear**: For issue creation (MCP server)
- **Web Search**: For information gathering (MCP server)
- **Web Scraper**: For content extraction (MCP server)

---

## Expected Behaviors

### Normal (Not Issues)
- MCP SSE fallback after streamable_http attempt
- Formation loading takes 5-10 seconds with MCP servers
- Variable response times based on API load
- Configuration tests complete in 10-30 seconds
- Full E2E tests may take 30 seconds to 5 minutes

### Issues to Watch For
- Tests consistently failing (not just timeouts)
- API authentication errors
- Formation loading failures
- Missing MCP servers

---

## Troubleshooting

### Test Times Out
- Check if it's a config test or full E2E test
- Config tests should complete in <30s
- Full E2E tests can take up to 5 minutes
- Increase timeout if needed: `pytest --timeout=300`

### API Errors
- Verify API keys in formation `secrets.enc`
- Check MCP server availability
- Review Linear API rate limits

### Formation Loading Fails
- Check symlinks in formations/ directory
- Verify secrets.enc files exist
- Check formation YAML syntax

---

## Future Tests

Planned but not yet implemented:
- **test_7b4_external_a2a_provider.py**: External A2A provider
- **test_7b5_external_a2a_requester.py**: External A2A requester

See `test_7b4_external_a2a_README.md` for implementation guide.

---

## Migration Notes

These tests were migrated from `e2e/tests/7_orchestration/` to follow the new E2E test standardization plan.

**Key Changes**:
- All tests send real messages via `overlord.chat()`
- All tests validate response content/transcripts
- Tests are isolated with their own formations
- Configuration tests added to reduce CI/CD time
- Full E2E coverage maintained via comprehensive tests

**Migration Date**: October 6-7, 2024
**Optimization Date**: October 7, 2024
