# MUXI Runtime Containers - Start Here! 🚀

**Your complete containerization system is ready to use!**

---

## 🎯 What You Have

✅ **Docker Runtime** - Built and tested (2.82GB)
✅ **SIF Build System** - Ready to convert Docker → SIF
✅ **Complete Documentation** - 2,100+ lines
✅ **Build Automation** - One-command builds
✅ **Test Formations** - Included and ready

---

## ⚡ Quick Start (3 Steps)

### 1. Test Docker Image (Already Built! ✅)

```bash
# Verify it works
docker run --rm muxi-runtime:latest python -c "import muxi; print('✅ Ready!')"
```

### 2. Build SIF Image (5 minutes)

```bash
# Install Apptainer if needed
brew install apptainer  # macOS

# Convert Docker → SIF
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest
```

### 3. Test SIF (1 minute)

```bash
# Verify SIF works
apptainer exec muxi-runtime.sif python -c "import muxi; print('✅ SIF Ready!')"
```

**That's it!** You now have a production-ready SIF image.

---

## 📚 Documentation (Pick Your Path)

### 🚀 New to This?
→ Read: **[DOCKER-SIF-WORKFLOW.md](./DOCKER-SIF-WORKFLOW.md)**
Complete workflow guide with examples and architecture diagrams.
**Time:** 20 minutes

### 📋 Need Quick Reference?
→ Read: **[SIF-QUICKSTART.md](./SIF-QUICKSTART.md)**
Cheat sheet with common commands and troubleshooting.
**Time:** 5 minutes (keep it open while working!)

### 📖 Want Deep Dive?
→ Read: **[SIF-GUIDE.md](./SIF-GUIDE.md)**
Comprehensive guide (10 sections) covering everything.
**Time:** 30-60 minutes

### 📊 Want Overview?
→ Read: **[CONTAINER-BUILD-SUMMARY.md](./CONTAINER-BUILD-SUMMARY.md)**
What was created, status, metrics, and next steps.
**Time:** 10 minutes

---

## 🔄 The Workflow

```
┌─────────────────┐
│  Source Code    │  (runtime/)
└────────┬────────┘
         │
         ▼  ./build-docker.sh
┌─────────────────┐
│  Docker Image   │  ✅ muxi-runtime:latest (2.82GB)
└────────┬────────┘
         │
         ▼  apptainer build
┌─────────────────┐
│   SIF Image     │  🔜 muxi-runtime.sif (~1GB)
└────────┬────────┘
         │
         ▼  Deploy
┌─────────────────┐
│  MUXI Server    │  Production-ready!
└─────────────────┘
```

---

## 📦 Files Overview

### Core Build Files
- **Dockerfile** - Basic runtime
- **Dockerfile.production** - With PostgreSQL + FAISSx
- **docker-compose.yaml** - Local testing
- **build-docker.sh** - Automated Docker builder ⭐
- **build-sif.sh** - Automated SIF builder ⭐

### SIF Definitions
- **muxi-runtime.def** - Converts Docker → SIF (basic)
- **muxi-runtime-production.def** - Converts Docker → SIF (production)

### Documentation (Read These!)
- **CONTAINERS-README.md** - This file (start here)
- **DOCKER-SIF-WORKFLOW.md** - Complete workflow guide
- **SIF-QUICKSTART.md** - Quick reference card
- **SIF-GUIDE.md** - Comprehensive reference
- **CONTAINER-BUILD-SUMMARY.md** - Status and metrics

### Examples
- **examples/test-formation.afs** - Test formation
- **examples/README.md** - Testing instructions

---

## 🎮 Common Commands

### Docker

```bash
# Build
./build-docker.sh basic              # Build Docker image
./build-docker.sh basic --no-cache   # Rebuild from scratch

# Test
docker run --rm muxi-runtime:latest python -c "import muxi"
docker-compose up muxi-runtime       # Full test environment

# Manage
docker images muxi-runtime           # List images
docker system prune                  # Clean up
```

### SIF

```bash
# Build from Docker
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest

# Or use automation
./build-sif.sh basic                 # Automated build

# Test
apptainer exec muxi-runtime.sif python -c "import muxi"
apptainer shell muxi-runtime.sif     # Interactive
apptainer inspect muxi-runtime.sif   # Details
```

### Test Formation

```bash
# In Docker
docker run --rm -p 8000:8000 \
  -v $(pwd)/examples:/formations \
  -e OPENAI_API_KEY=your-key \
  muxi-runtime:latest \
  python -m muxi.server run --formation /formations/test-formation.afs

# In SIF
apptainer run \
  --bind ./examples:/formations \
  --env OPENAI_API_KEY=your-key \
  muxi-runtime.sif \
  python -m muxi.server run --formation /formations/test-formation.afs

# Test it
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "test"}'
```

---

## 🎯 Your Next Steps

### Right Now (10 minutes)
1. Build SIF: `apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest`
2. Test it: `apptainer exec muxi-runtime.sif python -c "import muxi"`
3. Celebrate! 🎉

### Today (1 hour)
1. Test formation in Docker
2. Test formation in SIF
3. Read DOCKER-SIF-WORKFLOW.md

### This Week (Deploy!)
1. Integrate with MUXI Server
2. Deploy test formation
3. Monitor and verify

---

## 💡 Pro Tips

### For Development
- Use Docker (faster iteration)
- Test locally with `docker-compose up`
- Rebuild only changed layers

### For Production
- Use SIF (better isolation)
- Sign images for security
- Version your images

### For MUXI Server
- Set `runtime_type: "singularity"`
- Point to your SIF file
- Server handles everything else

---

## 🔧 Troubleshooting

### Docker Issues
| Problem | Solution |
|---------|----------|
| Build fails | Check Docker is running |
| Out of memory | Increase Docker memory (8GB+) |
| Slow build | Layers are cached after first build |

### SIF Issues
| Problem | Solution |
|---------|----------|
| Permission denied | Use `sudo` on Linux |
| Module not found | Test Docker image first |
| Can't access files | Check bind mounts |

### Need Help?
- Check **SIF-GUIDE.md** troubleshooting section
- Read **DOCKER-SIF-WORKFLOW.md** section 7
- Open issue on GitHub

---

## 📊 What's Included

| Component | Status | Size |
|-----------|--------|------|
| Docker (basic) | ✅ Built | 2.82GB |
| Docker (production) | 🔜 To build | ~3.5GB |
| SIF (basic) | 🔜 To build | ~1GB |
| SIF (production) | 🔜 To build | ~1.3GB |
| Documentation | ✅ Complete | 2,100+ lines |
| Build Scripts | ✅ Ready | Automated |
| Examples | ✅ Included | test-formation.afs |

---

## 🎓 Learning Path

```
1. Read this file                     (5 min)  ← You are here!
   ↓
2. Build SIF                          (5 min)
   ↓
3. Read DOCKER-SIF-WORKFLOW.md        (20 min)
   ↓
4. Test formation                     (10 min)
   ↓
5. Deploy to MUXI Server             (30 min)
   ↓
6. Production ready!                  (ongoing)
```

**Total:** ~1-2 hours to production deployment

---

## 🌟 Benefits

### For You
- ✅ Docker tested and ready
- ✅ SIF build system complete
- ✅ Documentation comprehensive
- ✅ Automation scripts included

### For MUXI Server
- 🧹 Clean server (no Python!)
- 🔐 Isolated formations
- 📦 Single-file distribution
- 🔄 Easy versioning & rollback
- ⚡ Native performance

---

## 📞 Support

- **Start Here:** This file
- **Workflow:** DOCKER-SIF-WORKFLOW.md
- **Reference:** SIF-GUIDE.md
- **Quick Help:** SIF-QUICKSTART.md
- **Issues:** [GitHub](https://github.com/muxi-ai/runtime/issues)

---

## ✨ Quick Summary

**You have:**
- ✅ Working Docker image (2.82GB, tested)
- ✅ SIF build system (ready to use)
- ✅ Complete documentation (all guides)
- ✅ Test formations (included)
- ✅ Build automation (one command)

**Next step:**
```bash
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest
```

**That's it!** You'll have a production-ready SIF in 5 minutes.

---

**Ready to build? Let's go!** 🚀

Last Updated: 2025-10-29
