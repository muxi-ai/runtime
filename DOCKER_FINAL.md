# MUXI Runtime Docker - Final Configuration

**Date**: October 29, 2025
**Status**: ✅ Production Ready
**Image**: `muxi-runtime:latest`
**Size**: 2.41 GB (optimized)

---

## 📦 Single Optimized Image

We've consolidated to **one primary Docker image** for simplicity and consistency:

### `muxi-runtime:latest` (2.41 GB)

**What's Inside:**
- Multi-stage optimized build
- Full Python ML stack (208 packages)
- All system dependencies (ffmpeg, tesseract, poppler)
- MUXI Runtime 0.2025.0
- Ready for production use

**Why This Size:**
- Python ML packages: 1.6 GB (66%) - PyTorch, transformers, etc.
- System libraries: 603 MB (25%) - ffmpeg, tesseract, libs
- Base OS: 148 MB (6%) - Debian + Python
- Other: 60 MB (3%)

**Optimizations Applied:**
- ✅ Multi-stage build (removed build tools)
- ✅ Minimal base image (python:3.10-slim)
- ✅ Aggressive cleanup
- ✅ No cache retention
- ✅ Layer consolidation

**Result**: 19% smaller than initial build (2.96GB → 2.41GB)

---

## 🚀 Usage

### Build
```bash
./build-docker.sh          # Builds muxi-runtime:latest
```

### Run
```bash
# Test import
docker run --rm muxi-runtime:latest \
  python -c "from muxi import Formation; print('✓ Works')"

# Run formation
docker run --rm \
  -v $(pwd)/formations:/formations \
  -e OPENAI_API_KEY=sk-your-key \
  muxi-runtime:latest \
  python -m muxi run --formation /formations/my-formation.afs

# Start server
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/formations:/formations \
  -e OPENAI_API_KEY=sk-your-key \
  --name muxi-server \
  muxi-runtime:latest
```

### With Docker Compose
```bash
docker-compose up
```

---

## 📁 Files Structure

```
runtime/
├── Dockerfile              # Main optimized build (2.4GB)
├── Dockerfile.production   # With PostgreSQL (~3GB)
├── docker-compose.yaml     # Orchestration
├── build-docker.sh         # Build automation
├── test-docker.sh          # Test suite
└── .dockerignore           # Build exclusions
```

**Removed/Archived:**
- ❌ Dockerfile.basic (merged into main)
- ❌ Dockerfile.slim (now the main Dockerfile)
- ❌ Dockerfile.minimal (experimental, removed)

---

## ✅ Test Results

All 6 tests passing:
1. ✅ MUXI Import
2. ✅ Version Check (0.2025.0)
3. ✅ Dependencies (all 7 key packages)
4. ✅ Formation Validation
5. ✅ Filesystem Structure
6. ✅ Package Count (208 installed)

Run tests:
```bash
./test-docker.sh
```

---

## 🎯 Design Decisions

### Why Not Alpine?
- Saves only ~100MB (4% of total)
- Breaks ML package compatibility
- Much longer build times
- Not worth the trade-offs

### Why Not Optional ML Dependencies?
- Breaks "works out of the box" promise
- Users would hit import errors
- Defeats purpose of batteries-included runtime
- Size savings require removing core functionality

### Why Multi-Stage Build?
- ✅ Removes 550MB of build tools
- ✅ No functionality loss
- ✅ Same build time
- ✅ Production best practice

### Why This Size is OK?
- PyTorch official: ~2.0 GB
- Langchain: ~2.5 GB
- Hugging Face: ~3.0 GB
- **MUXI: 2.4 GB** ← Competitive!

For a full-featured AI agent runtime, 2.4GB is industry-standard.

---

## 🔧 Advanced: Production Variant

For deployments needing PostgreSQL and enhanced services:

```bash
./build-docker.sh production
```

**Includes:**
- Everything in `latest`
- PostgreSQL with pgvector
- Redis (optional)
- Enhanced monitoring
- Production optimizations

**Size**: ~3 GB

---

## 📊 Size Comparison

| Image | Size | Build Time | Features | Use Case |
|-------|------|------------|----------|----------|
| **muxi-runtime:latest** | 2.41 GB | 3-4 min | All features | Production ✅ |
| muxi-runtime:production | ~3 GB | 5-6 min | + PostgreSQL | Full stack |

---

## 🐳 Docker Hub (Future)

When published to Docker Hub:

```bash
# Pull pre-built image
docker pull muxiai/runtime:latest

# Or specific version
docker pull muxiai/runtime:0.2025.0
```

---

## 📝 Notes

- Image is optimized and production-ready
- Size is appropriate for feature set
- Multi-stage build removes unnecessary layers
- All dependencies verified and tested
- Consistent with industry standards

---

**Ready for production deployment! 🚀**
