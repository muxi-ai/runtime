# Docker Testing Guide

Quick guide for testing the MUXI Runtime Docker container.

---

## Prerequisites

1. **Docker installed** (Docker Desktop or Docker Engine)
2. **OpenAI API key** (or other LLM provider key)
3. **Formation YAML file**

---

## Quick Start

### 1. Test Locally First (Recommended)

Before Docker, test that the runtime works locally:

```bash
# Set your API key
export OPENAI_API_KEY="sk-..."

# Run the test script
./test-local-server.sh
```

**Expected:** Server starts on http://localhost:8000

**Test endpoints:**
```bash
# Health check
curl http://localhost:8000/v1/health

# Server info
curl http://localhost:8000/

# API docs
open http://localhost:8000/docs
```

---

### 2. Build Docker Image

```bash
# Build the default image
./scripts/build/runtime.sh

# Or build a specific variant
./scripts/build/runtime.sh --variant pytorch

# Check image size
docker images muxi-runtime
```

**Expected image size:** ~2.4 GB (default), larger for pytorch/cuda variants

---

### 3. Test Docker Container

#### Option A: Using docker-compose (Easiest)

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Start container
docker-compose -f docker-compose.test.yaml up

# Or detached mode
docker-compose -f docker-compose.test.yaml up -d

# View logs
docker-compose -f docker-compose.test.yaml logs -f

# Stop
docker-compose -f docker-compose.test.yaml down
```

#### Option B: Using docker run

```bash
docker run -it --rm \
  -v $(pwd)/examples:/formations:ro \
  -e OPENAI_API_KEY="sk-..." \
  -p 8000:8000 \
  muxi-runtime:test \
  /formations/test-formation.afs
```

**Flags explained:**
- `-it` - Interactive terminal
- `--rm` - Remove container after exit
- `-v` - Mount formations directory (read-only)
- `-e` - Set environment variable
- `-p` - Port mapping (host:container)

---

### 4. Test the Running Container

```bash
# Health check
curl http://localhost:8000/v1/health

# Get server status
curl http://localhost:8000/

# View API documentation
open http://localhost:8000/docs

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! What can you help me with?",
    "user_id": "test-user"
  }'
```

---

## Using Your Own Formation

### Directory Structure

```
my-formation/
├── formation.afs
├── agents/
│   └── assistant.yaml
├── knowledge/
│   └── docs.txt
└── sops/
    └── onboarding.md
```

### Run with Custom Formation

```bash
docker run -it --rm \
  -v /path/to/my-formation:/formation:ro \
  -e OPENAI_API_KEY="sk-..." \
  -p 8000:8000 \
  muxi-runtime:test \
  /formation/formation.afs
```

---

## Common Issues

### 1. "Formation file not found"

**Problem:** Volume mount incorrect

**Solution:**
```bash
# Check your paths
ls /path/to/formation/formation.afs

# Use absolute paths
docker run -v "$(pwd)/my-formation:/formation:ro" ...
```

### 2. "No API keys detected"

**Problem:** Environment variable not set

**Solution:**
```bash
# Check if set
echo $OPENAI_API_KEY

# Set it
export OPENAI_API_KEY="sk-..."

# Or inline
docker run -e OPENAI_API_KEY="sk-..." ...
```

### 3. "Port already in use"

**Problem:** Port 8000 is occupied

**Solution:**
```bash
# Use different host port
docker run -p 9000:8000 ...

# Or set in environment
docker run -e FORMATION_PORT=9000 -p 9000:9000 ...
```

### 4. Container starts but server crashes

**Problem:** Check logs

**Solution:**
```bash
# View logs
docker logs <container-id>

# Or with docker-compose
docker-compose -f docker-compose.test.yaml logs
```

---

## Production Deployment

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
FORMATION_HOST=0.0.0.0
FORMATION_PORT=8000
ANTHROPIC_API_KEY=sk-...
```

### Resource Limits

```yaml
# docker-compose.yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

### Health Check

The container includes a health check:
```bash
# Docker will automatically check
curl -f http://localhost:8000/v1/health
```

---

## Next Steps

After Docker testing passes:

1. **SIF Conversion** - Convert Docker image to Singularity SIF
2. **Server Integration** - Test with MUXI Server deployment
3. **Performance Testing** - Load test multiple formations
4. **Production Deployment** - Deploy to production environment

---

## Cleanup

```bash
# Stop all containers
docker-compose -f docker-compose.test.yaml down

# Remove images
docker rmi muxi-runtime:test

# Clean up volumes
docker volume prune

# Full cleanup
docker system prune -a
```
