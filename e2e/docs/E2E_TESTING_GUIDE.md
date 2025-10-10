# E2E Testing Quick Start Guide

## Overview

The MUXI Runtime E2E test suite validates all major functionality across 12 areas with 215+ tests. Tests are located in `e2e/tests_new/` with a standardized structure.

## Required Services

### Core Services (Required)
1. **PostgreSQL** - Persistent memory storage
2. **FAISSx (no auth)** - Vector database without authentication (port 45678)
3. **FAISSx (with auth)** - Vector database with authentication (port 65432)
4. **API Keys** - OpenAI (required), Anthropic/Google (optional)

### Additional Services
5. **Webhook Server** - For async response handling
6. **A2A Registry** - Agent-to-agent communication

Note: MCP servers are defined in formation YAML files and started automatically by the runtime.

## Quick Start

### Option 1: Minimal Setup (Recommended for first run)

1. **Start basic services:**
```bash
docker-compose -f docker-compose.test-minimal.yml up -d
```

2. **Set up environment:**
```bash
cp .env.e2e.example .env.e2e
# Edit .env.e2e with your API keys
```

3. **Run a simple test to verify setup:**
```bash
python e2e/tests_new/1_foundation/test_1a6_simple_formation.py
```

### Option 2: Full Setup (All services)

1. **Start all services:**
```bash
docker-compose -f docker-compose.e2e.yml up -d
```

2. **Use the test runner script:**
```bash
./scripts/run-e2e-tests.sh --area 1  # Run foundation tests
```

## Running Tests

### Individual Test
```bash
python e2e/tests_new/2_memory/test_2a1_basic_conversation_context.py
```

### All Tests in an Area
```bash
# Using pytest
pytest e2e/tests_new/2_memory/ -v

# Using the test runner script
./scripts/run-e2e-tests.sh --area 2
```

### All Tests
```bash
# Using pytest
pytest e2e/tests_new/ -v

# Using the test runner script
./scripts/run-e2e-tests.sh
```

### With Detailed Logging
```bash
bash .claude/scripts/test-and-log.sh e2e/tests_new/1_foundation/test_1a6_simple_formation.py
```

## Test Areas

| Area | Directory | Tests | Focus |
|------|-----------|-------|-------|
| 1 | `1_foundation` | 10 | Basic formation loading and chat |
| 2 | `2_memory` | 26 | Memory systems (buffer, persistent, vector) |
| 3 | `3_multimodal` | 38 | Image, audio, video, document processing |
| 4 | `4_mcp` | 24 | Model Context Protocol tools |
| 5 | `5_artifacts` | 15 | File generation and artifacts |
| 6 | `6_knowledge` | 19 | Knowledge base operations |
| 7 | `7_orchestration` | 25 | Multi-agent coordination |
| 8 | `8_clarification` | 49 | Clarification flows |
| 9 | `9_async` | 12 | Async operations |
| 10 | `10_streaming` | 6 | Response streaming |
| 11 | `11_formatting` | 4 | Output formatting |
| 12 | `12_scheduling` | 11 | Task scheduling |

## Environment Variables

### Required
- `OPENAI_API_KEY` - OpenAI API key
- `POSTGRES_URI` - PostgreSQL connection string (default: postgresql://muxi:test123@localhost:5432/muxi_test)
- `FAISSX_NO_AUTH_URL` - FAISSx without auth (default: http://localhost:45678)
- `FAISSX_WITH_AUTH_URL` - FAISSx with auth (default: http://localhost:65432)

### Optional
- `ANTHROPIC_API_KEY` - For Anthropic models
- `GEMINI_API_KEY` - For Google models
- `A2A_REGISTRY_URL` - A2A Registry (default: http://localhost:8090)
- `WEBHOOK_URL` - Webhook server (default: http://localhost:8080)

## Test Patterns

Tests follow three main patterns:

1. **Pattern 1 (Runtime Modification)** - Modifies formation at runtime
2. **Pattern 2 (Shared Directory)** - Uses shared formation directory
3. **Pattern 3 (Separate Formations)** - Each test has its own formation

## Troubleshooting

### PostgreSQL Connection Issues
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs muxi-test-postgres

# Test connection
psql postgresql://muxi:test123@localhost:5432/muxi_test -c "SELECT 1"
```

### API Key Issues
- Ensure `.env.e2e` file exists and contains valid API keys
- Check that keys are properly formatted (e.g., `sk-...` for OpenAI)

### Memory Issues
- Some tests require significant memory
- Close other applications if tests fail with memory errors
- Use `--area` flag to run specific test areas

### Slow Tests
- First run may be slow due to model downloads
- Use `TEST_TIMEOUT_MULTIPLIER=2.0` in `.env.e2e` for slower systems

## CI/CD Integration

For GitHub Actions or other CI systems:

```yaml
- name: Start services
  run: docker-compose -f docker-compose.test-minimal.yml up -d

- name: Wait for services
  run: sleep 10

- name: Run tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    POSTGRES_URI: postgresql://muxi:test123@localhost:5432/muxi_test
  run: pytest e2e/tests_new/ -v --tb=short
```

## Tips

1. **Start small**: Run foundation tests first (`--area 1`)
2. **Check services**: Ensure Docker services are healthy before running tests
3. **Use logging**: The test runner script provides detailed output
4. **Parallel execution**: Set `TEST_PARALLEL_WORKERS` in `.env.e2e`
5. **Cleanup**: Use `--no-cleanup` flag to keep services running between test runs

## Common Commands

```bash
# Quick test to verify setup
python e2e/tests_new/1_foundation/test_1a6_simple_formation.py

# Run all memory tests
pytest e2e/tests_new/2_memory/ -v

# Run with specific timeout
TEST_TIMEOUT_MULTIPLIER=2.0 pytest e2e/tests_new/3_multimodal/ -v

# Stop all services
docker-compose -f docker-compose.test-minimal.yml down

# View service logs
docker logs muxi-test-postgres -f
```
