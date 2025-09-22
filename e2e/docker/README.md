# MUXI E2E Docker Testing Environment

## Overview

This directory contains the Docker configuration for running MUXI Runtime E2E tests in a fully isolated, reproducible environment. The all-in-one Docker image includes all required services and dependencies.

## Features

### 🚀 Performance Optimizations
- **Multi-stage build** reduces image size by pre-compiling Python wheels
- **Layer caching** for faster rebuilds
- **Parallel test execution** support with pytest-xdist
- **Optimized health checks** for all services

### 🔒 Security Improvements
- **Non-root user** for running services (muxi:muxi)
- **Isolated network** configuration (172.28.0.0/16)
- **Resource limits** to prevent resource exhaustion
- **No hardcoded secrets** - all via environment variables

### 🛠 Services Included
- **PostgreSQL 17** with pgvector extension for vector operations
- **FAISSx** (2 instances): one with auth, one without
- **Webhook Server** for async operation testing
- **A2A Registry** for agent-to-agent communication
- **Supervisor** for service orchestration

### 📦 Pre-installed Dependencies
- All MUXI Runtime requirements
- Test frameworks: pytest, pytest-asyncio, pytest-xdist, pytest-cov
- Document processing: MarkItDown, pypdf2, python-docx
- Image processing: Pillow, pdf2image, poppler-utils
- Audio/Video: ffmpeg
- NLP: spaCy, NLTK, sentence-transformers

## Quick Start

### 1. Set up environment variables
```bash
cp e2e/.env.example .env
# Edit .env and add your API keys
```

### 2. Build the Docker image
```bash
docker build -f e2e/docker/Dockerfile -t muxi-e2e .
# Or use the helper script:
./e2e/scripts/docker-build.sh
```

### 3. Run tests

Run all tests:
```bash
./e2e/scripts/run-docker-tests.sh
```

Run specific test area:
```bash
# Run foundation tests (area 1)
./e2e/scripts/run-docker-tests.sh -a 1

# Run memory tests (area 2) with verbose output
./e2e/scripts/run-docker-tests.sh -a 2 -v

# Run tests in parallel with 8 workers
./e2e/scripts/run-docker-tests.sh -p -w 8
```

Run tests matching a pattern:
```bash
./e2e/scripts/run-docker-tests.sh -k "test_memory"
```

### 4. Interactive development
```bash
# Drop into bash shell
./e2e/scripts/docker-build.sh

# Or after running tests
./e2e/scripts/run-docker-tests.sh -i
```

## Docker Compose Configuration

We provide a single, comprehensive Docker Compose configuration:

### `docker-compose.yml` - All-in-One Solution
**Purpose**: Everything in ONE container - simple, portable, and comprehensive
- **Use case**: E2E testing, CI/CD pipelines, developer onboarding
- **Architecture**: All services (PostgreSQL, FAISSx x2, webhook, A2A) run inside a single container managed by Supervisor
- **Pros**: Single command execution, no network complexity, easy distribution, perfect for GitHub Actions
- **Note**: When all tests pass, we'll create a test-runner image that includes and executes the tests automatically

## Docker Compose Usage

### Start all services
```bash
docker-compose -f e2e/docker/docker-compose.yml up -d
```

### Run specific tests
```bash
docker-compose -f e2e/docker/docker-compose.yml \
    run --rm muxi-e2e \
    pytest e2e/tests/1_foundation -v
```

### View logs
```bash
docker-compose -f e2e/docker/docker-compose.yml logs -f
```

### Stop and clean up
```bash
docker-compose -f e2e/docker/docker-compose.yml down -v
```

## Test Areas

| Area | Description | Test Count |
|------|------------|------------|
| 1 | Foundation (formation loading, basic chat) | 10 |
| 2 | Memory (buffer, persistent, vector) | 26 |
| 3 | Multimodal (images, audio, documents) | 38 |
| 4 | MCP (Model Context Protocol tools) | 24 |
| 5 | Artifacts (file generation) | 15 |
| 6 | Knowledge (knowledge base) | 19 |
| 7 | Orchestration (multi-agent) | 25 |
| 8 | Clarification (parameter collection) | 49 |
| 9 | Async (async operations) | 12 |
| 10 | Streaming (response streaming) | 6 |
| 11 | Formatting (output formatting) | 4 |
| 12 | Scheduling (task scheduling) | 11 |

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Database with pgvector |
| FAISSx (no auth) | 45678 | Vector search without auth |
| FAISSx (with auth) | 65432 | Vector search with auth |
| Webhook Server | 8080 | Async operation callbacks |
| A2A Registry | 8090 | Agent communication |

## Volume Mounts

The Docker container mounts several directories:
- `/app/src` - MUXI runtime source code (read-only)
- `/app/e2e/tests` - E2E test files (read-only)
- `/app/test-formations` - Test formation files (read-only)
- `/app/e2e/results` - Test results (writable)
- `/logs` - Service logs (writable)

## Health Checks

The container includes comprehensive health checks:
- PostgreSQL connectivity and database access
- FAISSx services (both instances)
- Webhook server responsiveness
- A2A registry availability

Health check script: `/app/healthcheck.sh`

## Troubleshooting

### Build fails with "no space left on device"
```bash
# Clean up Docker resources
docker system prune -a --volumes
```

### Services not starting
```bash
# Check service logs
docker exec muxi-e2e-test tail -f /logs/*.log

# Check supervisor status
docker exec muxi-e2e-test supervisorctl status
```

### Tests timing out
```bash
# Increase timeout
./e2e/scripts/run-docker-tests.sh -t 600
```

### PostgreSQL connection issues
```bash
# Verify PostgreSQL is running
docker exec muxi-e2e-test psql -U muxi -d muxi_test -c "SELECT 1"

# Check pgvector extension
docker exec muxi-e2e-test psql -U muxi -d muxi_test -c "\dx"
```

## Environment Variables

### Required
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - At least one LLM provider

### Optional
- `GEMINI_API_KEY` - Google Gemini API
- `GITHUB_TOKEN` - GitHub API access
- `LINEAR_API_KEY` - Linear integration
- `TEST_PARALLEL_WORKERS` - Number of parallel test workers (default: 4)
- `PYTEST_TIMEOUT` - Test timeout in seconds (default: 300)
- `LOG_LEVEL` - Logging level (default: info)

## Advanced Usage

### Rebuild without cache
```bash
./e2e/scripts/docker-build.sh --no-cache
```

### Generate coverage report
```bash
./e2e/scripts/run-docker-tests.sh -c
# View report at htmlcov/index.html
```

### Custom pytest options
```bash
docker-compose -f e2e/docker/docker-compose.all-in-one.yml \
    run --rm muxi-e2e-all \
    pytest e2e/tests -v --maxfail=1 --tb=short
```

## Development Tips

1. **Use the scripts** - The provided scripts handle most common tasks
2. **Check logs** - Service logs are in `/logs` inside the container
3. **Interactive debugging** - Use `-i` flag to drop into shell after tests
4. **Parallel execution** - Use `-p` flag for faster test runs
5. **Pattern matching** - Use `-k` to run specific tests quickly

## Files

- `Dockerfile` - Main Docker image definition with all services
- `docker-compose.yml` - Service orchestration configuration
- `.dockerignore` - Build context exclusions
- `../scripts/docker-build.sh` - Build helper script
- `../scripts/run-docker-tests.sh` - Test runner script
- `../.env.example` - Environment variable template (for future secrets.enc integration)