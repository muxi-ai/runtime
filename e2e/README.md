# E2E Testing Suite

Complete end-to-end testing environment for MUXI Runtime, containing all test files, Docker configurations, and utilities needed for comprehensive system validation.

## Directory Structure

```
e2e/
├── tests/              # All E2E test files (215+ tests)
│   ├── 1_foundation/   # Basic formation and chat tests
│   ├── 2_memory/       # Memory system tests
│   ├── 3_multimodal/   # Image, audio, video processing
│   ├── 4_mcp/          # Model Context Protocol tests
│   ├── 5_artifacts/    # File generation tests
│   ├── 6_knowledge/    # Knowledge base tests
│   ├── 7_orchestration/# Multi-agent coordination
│   ├── 8_clarification/# Clarification flow tests
│   ├── 9_async/        # Async operation tests
│   ├── 10_streaming/   # Response streaming tests
│   ├── 11_formatting/  # Output formatting tests
│   ├── 12_scheduling/  # Task scheduling tests
│   └── common/         # Shared test utilities
├── docker/             # Docker configurations
│   ├── Dockerfile      # All-in-one testing environment
│   ├── docker-compose.yml  # Service orchestration
│   └── README.md       # Docker-specific documentation
├── scripts/            # Test runner scripts
│   ├── docker-build.sh     # Build Docker image
│   └── run-docker-tests.sh # Run tests in Docker
├── utils/              # Utility services
│   ├── webhook_server.py  # Async webhook handler (port 8765)
│   └── a2a_registry.py    # A2A registry mock (port 9090)
├── fixtures/           # Test data and formations
│   ├── formations/     # Test formation configs
│   └── test-data/      # Sample test data
├── results/            # Test output directory
├── logs/               # Service and test logs
├── docs/               # E2E-specific documentation
├── .env.example        # Environment variables template
└── README.md           # This file
```

## Quick Start

### 1. Setup Environment

```bash
cd e2e
cp .env.example .env
# Edit .env and add your API keys (especially OPENAI_API_KEY)
```

### 2. Provision Formation Keys

Formation directories under `e2e/tests/` pair a committed `secrets.enc`
with a gitignored `.key` symlink to the shared `e2e/assets/.key`. Fresh
checkouts and git worktrees are missing every `.key` symlink; without
one, SecretsManager auto-generates a wrong key that cannot decrypt the
committed `secrets.enc` (confusing `InvalidToken`/`InvalidSignature`
failures).

`run_all_tests.py` and `run_random_tests.py` provision the symlinks
automatically at startup. For direct single-test runs, provision once
first:

```bash
cd e2e && uv run python provision_keys.py
```

The script is idempotent, only touches `e2e/tests/`, and never
overwrites a formation-owned `.key`/`secrets.enc` pair (it only replaces
stale auto-generated keys sitting over the shared symlinked
`secrets.enc`). It requires `e2e/assets/.key` to exist (gitignored --
copy it from a provisioned checkout). Verify the logic with
`uv run python provision_keys.py --self-test`.

### 3. Run Tests with Docker

#### Build and Start Services

```bash
# Build the Docker image
docker build -f e2e/docker/Dockerfile -t muxi-e2e .

# Start all services
docker-compose -f e2e/docker/docker-compose.yml up -d

# Verify services are healthy
docker ps
# Should show: muxi-e2e-test container running (healthy)
```

#### Run Tests

```bash
# Run tests inside container
docker exec -it muxi-e2e-test pytest e2e/tests/1_foundation/ -v

# Or run specific test
docker exec -it muxi-e2e-test python e2e/tests/1_foundation/test_1a6_simple_formation.py

# Interactive shell for debugging
docker exec -it muxi-e2e-test bash
```

#### Available Services
Once the container is running, these services are available:
- **PostgreSQL 17 + pgvector**: `localhost:5432`
- **FAISSx (no auth)**: `localhost:45678` (ZeroMQ protocol)
- **FAISSx (with auth)**: `localhost:65432` (ZeroMQ protocol)
- **Webhook Server**: `http://localhost:8765/health`
- **A2A Registry**: `http://localhost:9090/health`

## Test Areas

| Area | Tests | Purpose | Key Features |
|------|-------|---------|--------------|
| 1_foundation | 10 | Core functionality | Formation loading, basic chat |
| 2_memory | 26 | Memory systems | Buffer, persistent, vector search |
| 3_multimodal | 38 | Media processing | Images, audio, video, documents |
| 4_mcp | 24 | Tool integration | MCP servers, tool discovery |
| 5_artifacts | 15 | File generation | Charts, reports, code generation |
| 6_knowledge | 19 | Knowledge base | Search, retrieval, updates |
| 7_orchestration | 25 | Multi-agent | Coordination, delegation, workflows |
| 8_clarification | 49 | User interaction | Clarification flows, context |
| 9_async | 12 | Async operations | Async requests, callbacks |
| 10_streaming | 6 | Response streaming | Real-time streaming |
| 11_formatting | 4 | Output formatting | Markdown, JSON, custom formats |
| 12_scheduling | 11 | Task scheduling | Cron, delayed execution |

## Required Services

### Core Services
- **PostgreSQL**: Database for persistent storage
- **FAISSx (x2)**: Vector databases (with/without auth)
- **OpenAI API**: Required for LLM operations

### Support Services
- **Webhook Server**: Async response handling
- **A2A Registry**: Agent-to-agent communication

## Running Specific Tests

### By Area
```bash
# Using pytest
pytest e2e/tests/2_memory/ -v

# Using test runner
./e2e/scripts/test-in-docker.sh --area 2
```

### Individual Test
```bash
# Direct execution
python e2e/tests/1_foundation/test_1a6_simple_formation.py

# With pytest
pytest e2e/tests/1_foundation/test_1a6_simple_formation.py -v -s
```

### With Options
```bash
# Verbose output
pytest e2e/tests/ -v -s

# Stop on first failure
pytest e2e/tests/ -x

# Run parallel
pytest e2e/tests/ -n 4

# With coverage
pytest e2e/tests/ --cov=muxi --cov-report=html
```

## Docker Commands

### Build Images
```bash
cd e2e/docker
docker-compose -f docker-compose.all-in-one.yml build
```

### Start Services
```bash
# All services
docker-compose -f docker-compose.e2e.yml up -d

# Minimal services
docker-compose -f docker-compose.test-minimal.yml up -d
```

### View Logs
```bash
# All service logs
docker-compose -f docker-compose.e2e.yml logs -f

# Specific service
docker logs muxi-e2e-test -f
```

### Cleanup
```bash
# Stop services
docker-compose -f docker-compose.e2e.yml down

# Remove volumes
docker-compose -f docker-compose.e2e.yml down -v

# Full cleanup
./e2e/scripts/test-in-docker.sh --clean
```

## Environment Variables

### Required
- `OPENAI_API_KEY`: OpenAI API key for LLM operations
- `POSTGRES_URI`: PostgreSQL connection string
- `FAISSX_NO_AUTH_URL`: FAISSx without auth (default: http://localhost:45678)
- `FAISSX_WITH_AUTH_URL`: FAISSx with auth (default: http://localhost:65432)

### Optional
- `ANTHROPIC_API_KEY`: For Anthropic models
- `GEMINI_API_KEY`: For Google models
- `A2A_REGISTRY_URL`: A2A Registry URL
- `WEBHOOK_URL`: Webhook server URL
- `TEST_PARALLEL_WORKERS`: Number of parallel test workers
- `TEST_TIMEOUT_MULTIPLIER`: Timeout adjustment factor

## CI/CD Integration

### GitHub Actions
```yaml
jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build E2E image
        run: |
          cd e2e/docker
          docker-compose -f docker-compose.all-in-one.yml build

      - name: Run E2E tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          cd e2e/docker
          docker-compose -f docker-compose.all-in-one.yml run --rm \
            muxi-e2e-all pytest e2e/tests/ -v --junit-xml=results/junit.xml

      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: e2e/results/
```

## Troubleshooting

### Import Errors
```bash
# Ensure PYTHONPATH is set correctly
export PYTHONPATH=$PYTHONPATH:$(pwd)/src:$(pwd)/e2e

# Or run from runtime directory
cd runtime
python -m pytest e2e/tests/
```

### Service Connection Issues
```bash
# Check if services are running
docker ps

# Test PostgreSQL connection
psql postgresql://muxi:test123@localhost:5432/muxi_test -c "SELECT 1"

# Test FAISSx
curl http://localhost:45678/health
```

### API Key Issues
```bash
# Check environment
echo $OPENAI_API_KEY

# Verify in container
docker exec muxi-e2e-test env | grep API_KEY
```

## Development Tips

1. **Use the all-in-one Docker setup** for consistent environment
2. **Run specific areas** during development, full suite before commits
3. **Check logs** in `e2e/logs/` for debugging
4. **Use `--shell` mode** for interactive debugging
5. **Keep services running** between test runs with `--no-cleanup`

## Test Patterns

Tests follow three main patterns:

1. **Pattern 1**: Runtime modification - modifies formation at runtime
2. **Pattern 2**: Shared directory - uses shared formation directory
3. **Pattern 3**: Separate formations - each test has its own formation

## Contributing

1. Add new tests to appropriate area directory
2. Follow existing test structure and naming
3. Use base classes for consistency
4. Document test purpose and validation
5. Run linting before committing: `ruff check e2e/tests/`

## Additional Documentation

- [Docker Setup Guide](docs/DOCKER_E2E_TESTING.md)
- [Testing Guide](docs/E2E_TESTING_GUIDE.md)
- [Migration Notes](tests/COMPLETE_MIGRATION_SUMMARY.md)