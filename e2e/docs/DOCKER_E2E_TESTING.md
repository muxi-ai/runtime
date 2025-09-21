# Docker All-in-One E2E Testing

## Overview

The all-in-one Docker setup provides a complete, self-contained testing environment with:
- All required services (PostgreSQL, FAISSx x2, Webhook, A2A Registry)
- MUXI runtime and all dependencies pre-installed
- Test runner with pytest configured
- Automatic service orchestration

## Quick Start

### 1. Set up environment
```bash
# Copy and configure environment variables
cp .env.e2e.example .env.e2e
# Edit .env.e2e and add your API keys (especially OPENAI_API_KEY)
```

### 2. Run tests using the convenience script
```bash
# Run all tests
./scripts/test-in-docker.sh

# Run specific area
./scripts/test-in-docker.sh --area 1

# Run with rebuild
./scripts/test-in-docker.sh --build --area 2

# Open interactive shell
./scripts/test-in-docker.sh --shell
```

## Architecture

### Single Container Design
The `Dockerfile.e2e-all-in-one` creates a single container with:

```
┌─────────────────────────────────────┐
│      MUXI E2E Test Container        │
├─────────────────────────────────────┤
│  Services (via supervisor):         │
│  - PostgreSQL (port 5432)          │
│  - FAISSx no-auth (port 45678)     │
│  - FAISSx with-auth (port 65432)   │
│  - Webhook server (port 8080)      │
│  - A2A Registry (port 8090)        │
├─────────────────────────────────────┤
│  MUXI Runtime:                      │
│  - Source mounted from host         │
│  - All dependencies installed       │
│  - pytest configured                │
└─────────────────────────────────────┘
```

### Volume Mounts
- `/app/src` - MUXI runtime source (read-only)
- `/app/tests` - Test files (read-only)
- `/app/test-results` - Test output (writable)
- `/logs` - Service logs (writable)

## Usage Examples

### Running All Tests
```bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all \
    pytest tests/e2e_new/ -v
```

### Running Specific Area
```bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all \
    pytest tests/e2e_new/2_memory/ -v
```

### Interactive Development
```bash
# Start container with bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all bash

# Inside container:
pytest tests/e2e_new/1_foundation/test_1a6_simple_formation.py -v -s
```

### Viewing Logs
```bash
# While container is running
docker exec -it muxi-e2e-test tail -f /logs/*.log

# Or use the script
./scripts/test-in-docker.sh --logs
```

## Service Details

### PostgreSQL
- User: `muxi`
- Password: `muxi_test_password`
- Database: `muxi_test`
- Port: 5432

### FAISSx (No Auth)
- Port: 45678
- URL: http://localhost:45678

### FAISSx (With Auth)
- Port: 65432
- URL: http://localhost:65432
- Auth file: `/app/faissx-auth.json`

### Webhook Server
- Port: 8080
- Script: `/app/utils/webhook_server.py`

### A2A Registry
- Port: 8090
- Script: `/app/utils/a2a_registry.py`

## Building the Image

### First Build
```bash
docker-compose -f docker-compose.all-in-one.yml build
```

### Rebuild After Changes
```bash
docker-compose -f docker-compose.all-in-one.yml build --no-cache
```

### Using the Script
```bash
./scripts/test-in-docker.sh --build
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose -f docker-compose.all-in-one.yml logs

# Verify services
docker exec -it muxi-e2e-test supervisorctl status
```

### Tests Can't Find Modules
```bash
# Verify PYTHONPATH
docker exec -it muxi-e2e-test env | grep PYTHONPATH

# Should show: /app/src:/app
```

### API Key Issues
```bash
# Verify environment variables
docker exec -it muxi-e2e-test env | grep API_KEY

# Make sure .env.e2e exists and is loaded
cat .env.e2e | grep OPENAI_API_KEY
```

### PostgreSQL Connection Issues
```bash
# Test connection inside container
docker exec -it muxi-e2e-test psql -U muxi -d muxi_test -c "SELECT 1"
```

### FAISSx Not Responding
```bash
# Check if services are running
docker exec -it muxi-e2e-test curl http://localhost:45678/health
docker exec -it muxi-e2e-test curl http://localhost:65432/health
```

## Performance Tips

1. **Use cached builds**: The image caches pip packages
2. **Mount only necessary files**: Use read-only mounts where possible
3. **Run specific tests**: Don't run all tests if you only need one area
4. **Keep container running**: Use `--shell` for iterative development

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build test image
  run: docker-compose -f docker-compose.all-in-one.yml build

- name: Run E2E tests
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: |
    docker-compose -f docker-compose.all-in-one.yml run --rm \
      muxi-e2e-all pytest tests/e2e_new/ -v --junit-xml=test-results.xml

- name: Upload test results
  uses: actions/upload-artifact@v2
  with:
    name: test-results
    path: test-results.xml
```

## Cleanup

```bash
# Stop and remove container
docker-compose -f docker-compose.all-in-one.yml down

# Remove volumes
docker-compose -f docker-compose.all-in-one.yml down -v

# Remove image
docker rmi muxi-e2e:all-in-one

# Or use the script
./scripts/test-in-docker.sh --clean
```

## Advanced Usage

### Custom pytest options
```bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all \
    pytest tests/e2e_new/ -v -s -x --tb=long --maxfail=3
```

### Running with coverage
```bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all \
    pytest tests/e2e_new/ --cov=muxi --cov-report=html
```

### Parallel test execution
```bash
docker-compose -f docker-compose.all-in-one.yml run --rm muxi-e2e-all \
    pytest tests/e2e_new/ -n 4
```

## Benefits

1. **Zero setup**: No need to install services locally
2. **Consistency**: Same environment for all developers
3. **Isolation**: Tests run in contained environment
4. **Reproducibility**: Exact same setup every time
5. **CI/CD ready**: Can be used directly in pipelines