# MUXI Runtime - Docker Guide

**Stage 1: Docker First → Test Everything → Then SIF**

---

## 🎯 Current Focus: Docker (Stage 1)

We're taking an **incremental approach**:

1. ✅ **Docker** - Build and test (we are here!)
2. 🔜 **SIF** - Convert once Docker is proven

---

## 📁 File Organization

```
runtime/
├── Dockerfile                  ← Basic runtime
├── Dockerfile.production       ← With PostgreSQL + FAISSx
├── docker-compose.yaml         ← Local testing
├── build-docker.sh            ← Build automation
├── .dockerignore              ← Build optimization
├── examples/                   ← Test formations
│   └── test-formation.afs
│
└── sif/                        ← SIF files (Stage 2 - later!)
    ├── build-sif.sh
    ├── muxi-runtime.def
    ├── SIF-GUIDE.md
    └── ...
```

---

## 🚀 Quick Start

### Step 1: Build Docker Image

```bash
# Build basic runtime (~2-3 GB, 10-15 min)
./build-docker.sh basic

# Or build with all services (~3-4 GB, 15-20 min)
./build-docker.sh production
```

### Step 2: Test It Works

```bash
# Quick import test
docker run --rm muxi-runtime:latest python -c "import muxi; print('✅ Works!')"

# Check version
docker run --rm muxi-runtime:latest python -c "import muxi; print(muxi.__version__)"
```

### Step 3: Run Test Formation

```bash
# Using docker run
docker run --rm -p 8000:8000 \
  -v $(pwd)/examples:/formations \
  -e OPENAI_API_KEY=your-key-here \
  muxi-runtime:latest \
  python -m muxi.server run --formation /formations/test-formation.afs

# Or using docker-compose
docker-compose up muxi-runtime
```

### Step 4: Test Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "test"}'
```

---

## 📦 What's in Each Image

### Basic Runtime (`muxi-runtime:latest`)

**Contents:**
- Python 3.10
- MUXI Runtime + all dependencies
- System tools: ffmpeg, tesseract, poppler-utils

**Size:** ~2-3 GB
**Use:** Standard formations, development, most deployments

### Production Runtime (`muxi-runtime:production`)

**Contents:**
- Everything in basic +
- PostgreSQL 17 with pgvector
- FAISSx vector store
- Supervisor for process management

**Size:** ~3-4 GB
**Use:** Complex formations needing database/vector search

---

## 🧪 Testing Checklist

Before moving to SIF, verify:

- [ ] Docker image builds successfully
- [ ] `import muxi` works
- [ ] Test formation loads
- [ ] Endpoints respond
- [ ] Environment variables work
- [ ] Volume mounts work
- [ ] Logs are accessible

---

## 🔧 Development Workflow

```bash
# 1. Make changes to source code
vim src/muxi/...

# 2. Rebuild Docker image
./build-docker.sh basic

# 3. Test quickly
docker run --rm muxi-runtime:latest python -c "import muxi"

# 4. Test with formation
docker-compose up

# 5. When everything works → Move to SIF!
```

---

## 🐛 Troubleshooting

### Build Fails

```bash
# Check Docker is running
docker info

# Check disk space
docker system df

# Clean up old images
docker system prune -a
```

### Container Fails to Start

```bash
# Check logs
docker logs <container-id>

# Run with shell access
docker run --rm -it muxi-runtime:latest /bin/bash

# Check if dependencies are installed
docker run --rm muxi-runtime:latest pip list
```

### Can't Access Formation

```bash
# Check port mapping
docker ps

# Check if formation is running
docker exec <container-id> ps aux | grep python

# Check logs inside container
docker exec <container-id> cat /logs/formation.log
```

---

## 📚 Docker Commands Reference

```bash
# Build
docker build -t muxi-runtime:latest -f Dockerfile .
./build-docker.sh basic              # Automated

# Run
docker run --rm muxi-runtime:latest
docker-compose up

# Inspect
docker images muxi-runtime
docker inspect muxi-runtime:latest
docker ps
docker logs <container-id>

# Clean up
docker stop <container-id>
docker rm <container-id>
docker rmi muxi-runtime:latest
docker system prune
```

---

## ⚙️ Configuration

### Docker Compose

Edit `docker-compose.yaml`:

```yaml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

volumes:
  - ./examples:/formations:ro
  - ./data:/data
  - ./logs:/logs

ports:
  - "8000:8000"
```

### Environment Variables

Create `.env` file:

```bash
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
MUXI_FORMATIONS_DIR=/formations
MUXI_DATA_DIR=/data
MUXI_LOGS_DIR=/logs
```

---

## 🎯 Next Steps

### Once Docker is Working

1. **Document what works** - Note any issues or gotchas
2. **Test edge cases** - Multiple formations, restarts, etc.
3. **Measure performance** - Memory usage, startup time
4. **Check security** - Run as non-root, no secrets in logs

### Move to SIF (Stage 2)

```bash
# When Docker is proven, move to SIF
cd sif/
./build-sif.sh basic

# This converts the tested Docker image to SIF
# See sif/SIF-GUIDE.md for details
```

---

## 📖 Additional Documentation

- **[examples/README.md](./examples/README.md)** - Test formation examples
- **[sif/SIF-GUIDE.md](./sif/SIF-GUIDE.md)** - SIF documentation (Stage 2)
- **[AGENTS.md](./AGENTS.md)** - Development guide

---

## 💡 Tips

1. **Use docker-compose** - Easier than raw docker commands
2. **Mount volumes** - For development, mount source code
3. **Check logs** - Use `docker logs -f` to follow logs
4. **Tag versions** - Tag images with version numbers
5. **Test locally first** - Don't push until it works

---

## ✅ Success Criteria (Before SIF)

Docker is ready for SIF conversion when:

- ✅ Builds without errors
- ✅ All dependencies installed
- ✅ MUXI imports successfully
- ✅ Test formation runs
- ✅ Endpoints respond correctly
- ✅ No permission issues
- ✅ Logs are readable
- ✅ Can restart without issues

---

**Focus: Get Docker working perfectly first!** 🐳

Then SIF will be a simple conversion step. 🚀

Last Updated: 2025-10-29
