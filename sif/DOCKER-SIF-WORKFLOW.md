# Docker → SIF Workflow Guide

**Complete workflow for building MUXI Runtime containers**

---

## 📋 Overview

To run MUXI formations as containers, we use a two-step process:

```
Step 1: Source Code → Docker Image
Step 2: Docker Image → SIF Image
```

**Why this workflow?**
- Docker is universal and easy to test
- SIF provides production benefits (single file, read-only, HPC-ready)
- Build once in Docker, convert to SIF when ready for production

---

## 🚀 Quick Start (30 minutes)

### Step 1: Build Docker Image (15 minutes)

```bash
cd /Users/ran/Projects/muxi/code/runtime

# Build basic runtime (~2.8GB, 10-15 min)
./build-docker.sh basic

# Test it works
docker run --rm muxi-runtime:latest python -c "import muxi; print('✅ Works!')"
```

### Step 2: Convert to SIF (5 minutes)

```bash
# Convert Docker → SIF
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest

# Test the SIF
apptainer exec muxi-runtime.sif python -c "import muxi; print('✅ SIF Works!')"
```

### Step 3: Test Formation (5 minutes)

```bash
# Run test formation in Docker
docker run --rm -p 8000:8000 \
  -v $(pwd)/examples:/formations \
  -e OPENAI_API_KEY=sk-your-key \
  muxi-runtime:latest \
  python -m muxi.server run --formation /formations/test-formation.yaml

# Or in SIF
apptainer run \
  --bind ./examples:/formations \
  --env OPENAI_API_KEY=sk-your-key \
  muxi-runtime.sif \
  python -m muxi.server run --formation /formations/test-formation.yaml
```

---

## 🏗️ Complete Workflow

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Source Code (runtime/)                                   │
│   • Python code (src/)                                   │
│   • Dependencies (requirements.txt)                      │
│   • Configuration (pyproject.toml)                       │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼ ./build-docker.sh
┌──────────────────────────────────────────────────────────┐
│ Docker Image (muxi-runtime:latest)                       │
│   • All dependencies installed                           │
│   • System tools (ffmpeg, tesseract)                     │
│   • Python 3.10 + MUXI runtime                           │
│   • Size: ~2.8GB                                         │
│   • Layer-cached for fast rebuilds                       │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼ apptainer build ... docker-daemon://...
┌──────────────────────────────────────────────────────────┐
│ SIF Image (muxi-runtime.sif)                             │
│   • Single immutable file                                │
│   • Read-only, signed, portable                          │
│   • Size: ~1GB (compressed)                              │
│   • Production-ready                                     │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼ Deploy to MUXI Server
┌──────────────────────────────────────────────────────────┐
│ MUXI Server spawns formations in SIF containers          │
│   • Clean server (no Python)                             │
│   • Isolated formations                                  │
│   • Auto-restart on crash                                │
│   • Resource limits per formation                        │
└──────────────────────────────────────────────────────────┘
```

---

## 📦 Files Created

| File | Purpose | When to Use |
|------|---------|-------------|
| **Dockerfile** | Basic runtime | Development, testing, most formations |
| **Dockerfile.production** | With PostgreSQL + FAISSx | Complex formations needing DB/vector search |
| **docker-compose.yaml** | Local testing | Quick local development |
| **build-docker.sh** | Docker build automation | Building Docker images |
| **muxi-runtime.def** | SIF from Docker | Converting Docker → SIF |
| **muxi-runtime-production.def** | Production SIF | Converting production Docker → SIF |
| **build-sif.sh** | SIF build automation | Building SIF images |

---

## 🔄 Development Workflow

### Local Development

```bash
# 1. Make changes to source code
vim src/muxi/...

# 2. Rebuild Docker image
./build-docker.sh basic

# 3. Test quickly with Docker
docker run --rm -it muxi-runtime:latest python -c "import muxi"

# 4. Test formation
docker-compose up muxi-runtime

# 5. When ready for production, build SIF
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest
```

### Production Deployment

```bash
# 1. Build production Docker image
./build-docker.sh production

# 2. Test thoroughly
docker-compose up muxi-production

# 3. Convert to SIF for deployment
apptainer build muxi-runtime-production.sif docker-daemon://muxi-runtime:production

# 4. Deploy to MUXI Server
scp muxi-runtime-production.sif user@server:/opt/muxi/

# 5. Update server config
# Edit ~/.muxi-server/config.yaml:
#   formations:
#     runtime_type: "singularity"
#     singularity_image: "/opt/muxi/muxi-runtime-production.sif"

# 6. Restart server
ssh user@server "sudo systemctl restart muxi-server"
```

---

## ⚙️ Configuration

### Docker Configuration

**docker-compose.yaml:**
```yaml
services:
  muxi-runtime:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./examples:/formations:ro
      - ./data:/data
      - ./logs:/logs
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
```

### SIF Configuration

**For MUXI Server** (`~/.muxi-server/config.yaml`):
```yaml
formations:
  runtime_type: "singularity"
  singularity_image: "/path/to/muxi-runtime.sif"
  
  port_range_start: 8000
  port_range_end: 9000
  bind_host: "127.0.0.1"
  
  auto_restart: true
  max_restart_count: 10
```

---

## 🧪 Testing

### Test Docker Image

```bash
# Basic import test
docker run --rm muxi-runtime:latest python -c "import muxi; print(muxi.__version__)"

# Formation test
docker run --rm -p 8000:8000 \
  -v $(pwd)/examples:/formations \
  -e OPENAI_API_KEY=sk-your-key \
  muxi-runtime:latest \
  python -m muxi.server run --formation /formations/test-formation.yaml

# Health check
curl http://localhost:8000/health

# Chat test
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "test"}'
```

### Test SIF Image

```bash
# Basic import test
apptainer exec muxi-runtime.sif python -c "import muxi"

# Formation test
apptainer run \
  --bind ./examples:/formations \
  --env OPENAI_API_KEY=sk-your-key \
  muxi-runtime.sif \
  python -m muxi.server run --formation /formations/test-formation.yaml

# Interactive shell
apptainer shell muxi-runtime.sif
```

---

## 🔧 Troubleshooting

### Docker Issues

| Problem | Solution |
|---------|----------|
| Build fails | Check Docker daemon is running |
| Out of memory | Increase Docker memory to 8GB+ |
| Image too large | Remove build dependencies after install |
| Slow build | Layer caching helps on rebuilds |

### SIF Issues

| Problem | Solution |
|---------|----------|
| "Permission denied" | Use `sudo` on Linux or Docker method |
| "Module not found" | Verify Docker image works first |
| Can't access files | Check bind mounts: `--bind src:dst` |
| Large SIF size | Docker image determines SIF size |

### Integration Issues

| Problem | Solution |
|---------|----------|
| Formation won't start | Check MUXI Server logs |
| Port conflicts | Verify port_range in config |
| API keys not found | Pass via environment variables |
| Performance issues | Monitor resource usage |

---

## 📊 Comparison: Docker vs SIF

| Feature | Docker | SIF |
|---------|--------|-----|
| **File Size** | ~2.8GB | ~1GB (compressed) |
| **Distribution** | Registry required | Single file |
| **Performance** | Native | Native |
| **Security** | Mutable layers | Immutable, signed |
| **Development** | ✅ Excellent | ⚠️ Rebuild needed |
| **Production** | ✅ Good | ✅ Excellent |
| **Multi-tenant** | ✅ Good | ✅ Excellent |
| **HPC** | ❌ Not ideal | ✅ Perfect |
| **Testing** | ✅ Very fast | ⚠️ Slower |
| **Debugging** | ✅ Easy | ⚠️ Limited |

**Recommendation:**
- **Development:** Use Docker (faster iteration)
- **Production:** Use SIF (better isolation, security, portability)

---

## 🎯 Best Practices

### Docker Best Practices

1. **Layer Caching:** Structure Dockerfile to maximize caching
2. **Multi-stage Builds:** Separate build and runtime stages
3. **Security:** Run as non-root user
4. **Size:** Clean up after installations
5. **Testing:** Test every build before pushing

### SIF Best Practices

1. **Source:** Always build from tested Docker image
2. **Signing:** Sign SIF images for production
3. **Versioning:** Include version in filename
4. **Testing:** Test SIF before deploying
5. **Distribution:** Store in shared filesystem or registry

### MUXI Server Integration

1. **Configuration:** Set `runtime_type: "singularity"`
2. **Bind Mounts:** Server handles formation/data/logs
3. **Environment:** Pass secrets via environment variables
4. **Monitoring:** Watch logs and resource usage
5. **Updates:** Test new SIF before replacing production

---

## 📚 Quick Reference

### Build Commands

```bash
# Docker
./build-docker.sh basic                     # Basic runtime
./build-docker.sh production                # With services
./build-docker.sh basic --no-cache          # Force rebuild

# SIF (from Docker)
apptainer build image.sif docker-daemon://muxi-runtime:latest

# SIF (from definition)
apptainer build image.sif definition.def
```

### Run Commands

```bash
# Docker
docker run --rm -it muxi-runtime:latest
docker-compose up muxi-runtime

# SIF
apptainer run image.sif
apptainer exec image.sif python script.py
apptainer shell image.sif
```

### Test Commands

```bash
# Docker
docker run --rm muxi-runtime:latest python -c "import muxi"
docker inspect muxi-runtime:latest

# SIF
apptainer exec image.sif python -c "import muxi"
apptainer inspect image.sif
apptainer test image.sif
```

---

## 🎓 Next Steps

1. **Read Documentation:**
   - [SIF-GUIDE.md](./SIF-GUIDE.md) - Comprehensive SIF guide
   - [SIF-QUICKSTART.md](./SIF-QUICKSTART.md) - Quick reference

2. **Try It:**
   - Build Docker image: `./build-docker.sh basic`
   - Test locally: `docker-compose up`
   - Convert to SIF: `apptainer build ...`

3. **Deploy:**
   - Test formation in Docker
   - Convert to SIF
   - Deploy to MUXI Server
   - Monitor and iterate

4. **Optimize:**
   - Review Docker image size
   - Optimize layer caching
   - Sign SIF images
   - Set up CI/CD

---

## ✅ Current Status

**✅ Completed:**
- Docker images (basic + production)
- SIF definitions (Docker-based)
- Build scripts (automated)
- Test formations (examples/)
- Documentation (comprehensive)

**✅ Tested:**
- Docker build: ✅ Works (2.82GB)
- Docker run: ✅ MUXI imports successfully
- Ready for SIF conversion

**🔜 Next:**
1. Build SIF from Docker image
2. Test SIF with formation
3. Integrate with MUXI Server
4. Production deployment

---

## 🤝 Support

- **Issues:** [GitHub Issues](https://github.com/muxi-ai/runtime/issues)
- **Discussions:** [GitHub Discussions](https://github.com/muxi-ai/runtime/discussions)
- **Documentation:** [muxi.org/docs](https://muxi.org/docs)

---

**Building the future of AI infrastructure, one container at a time** 🚀

Last Updated: 2025-10-29
