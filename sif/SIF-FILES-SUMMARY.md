# MUXI SIF Files Summary

**Complete guide to Singularity Image Format (SIF) builds for MUXI Runtime**

---

## 📁 Files Created

| File | Purpose | Size |
|------|---------|------|
| **SIF-GUIDE.md** | Comprehensive guide (10 sections) | ~23 KB |
| **SIF-QUICKSTART.md** | Quick reference card | ~4.5 KB |
| **muxi-runtime.def** | Basic runtime definition | ~3.7 KB |
| **muxi-runtime-production.def** | Production definition with services | ~6.1 KB |
| **build-sif.sh** | Automated build script | ~6.9 KB |
| **examples/test-formation.afs** | Test formation | ~0.6 KB |
| **examples/README.md** | Examples documentation | ~2.9 KB |

**Total:** ~48 KB of documentation and tooling

---

## 🎯 What You Can Do Now

### 1. **Build a SIF Image**

```bash
cd /Users/ran/Projects/muxi/code/runtime

# Build basic runtime (~2GB, 10-15 min)
./build-sif.sh basic

# Build production with services (~3GB, 15-20 min)
./build-sif.sh production
```

### 2. **Test the Image**

```bash
# Quick test
apptainer exec muxi-runtime.sif python -c "import muxi; print('✅ Works!')"

# Run test formation
apptainer run \
    --bind ./examples/test-formation.afs:/formation.afs \
    --env OPENAI_API_KEY=sk-your-key \
    muxi-runtime.sif \
    --formation /formation.afs --port 8000
```

### 3. **Integrate with MUXI Server**

Update `~/.muxi-server/config.yaml`:

```yaml
formations:
  runtime_type: "singularity"
  singularity_image: "/path/to/muxi-runtime.sif"
```

Then deploy formations as normal - the server will spawn them in SIF containers!

---

## 📖 Documentation Structure

### **SIF-GUIDE.md** (Comprehensive - 23 KB)

The complete guide with 10 major sections:

1. **What is a SIF Image?** - Introduction to Singularity containers
2. **Why Use SIF for MUXI?** - Benefits and architecture diagrams
3. **Prerequisites** - Installation for Linux/macOS/Windows
4. **Building a SIF Image** - 3 methods with examples
5. **Testing with MUXI Server** - Full integration guide
6. **SIF Image Structure** - Internal layout and bind mounts
7. **Best Practices** - Optimization, security, testing
8. **Optimization Tips** - Multi-stage builds, caching, compression
9. **Troubleshooting** - Common problems and solutions
10. **Advanced Topics** - GPU support, networking, resource limits, signed images

**Key Features:**
- 50+ code examples
- Architecture diagrams
- Production-ready configurations
- Security best practices
- Performance optimization
- Complete troubleshooting guide

### **SIF-QUICKSTART.md** (Quick Reference - 4.5 KB)

A condensed cheat sheet covering:
- Prerequisites (3 commands)
- Build (2 commands)
- Test (3 methods)
- Deploy (4 steps)
- Common commands (10 operations)
- Bind mounts, environment variables
- Troubleshooting table
- Performance tips (DO/DON'T)

**Perfect for:** Keeping open while working, quick lookups

### **Definition Files**

#### **muxi-runtime.def** (Basic - 3.7 KB)

Minimal production runtime:
- Python 3.10 + MUXI Runtime
- System dependencies (ffmpeg, tesseract, etc.)
- ~2 GB final image
- ~10-15 minute build time

**Use for:** Standard formations without external services

#### **muxi-runtime-production.def** (Full - 6.1 KB)

Complete production environment:
- Everything in basic +
- PostgreSQL 17 with pgvector
- FAISSx vector store (with auth)
- Supervisor for service management
- ~3 GB final image
- ~15-20 minute build time

**Use for:** Complex formations needing databases/vector search

### **build-sif.sh** (Build Script - 6.9 KB)

Automated build tool with:
- ✅ Auto-detects Apptainer/Singularity/Docker
- ✅ Fallback to Docker-based build (no sudo needed)
- ✅ macOS and Linux support
- ✅ Colored output and progress
- ✅ Automatic testing after build
- ✅ Safety checks (overwrite protection)
- ✅ Detailed usage instructions

```bash
./build-sif.sh                      # Build basic
./build-sif.sh production           # Build with services
./build-sif.sh basic custom.sif     # Custom name
```

### **Examples** (Test Formations)

**examples/test-formation.afs**
- Simple chat assistant
- OpenAI GPT-4o-mini
- Validates SIF runtime
- Minimal configuration

**examples/README.md**
- 3 testing methods
- Expected results
- Troubleshooting guide
- Links to more examples

---

## 🏗️ Architecture: SIF in MUXI

```
┌─────────────────────────────────────────┐
│         MUXI Server (Go Binary)         │
│              Port 7890                   │
└─────────────────┬───────────────────────┘
                  │
        Spawns SIF instances
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
┌──────────────┐      ┌──────────────┐
│ Formation 1  │      │ Formation 2  │
│ 127.0.0.1:8001│     │ 127.0.0.1:8002│
├──────────────┤      ├──────────────┤
│ muxi-runtime │      │ muxi-runtime │
│    .sif      │      │    .sif      │
│              │      │              │
│ Python 3.10  │      │ Python 3.10  │
│ MUXI Runtime │      │ MUXI Runtime │
│ Dependencies │      │ Dependencies │
│ Isolated!    │      │ Isolated!    │
└──────────────┘      └──────────────┘
```

**Benefits:**
- ✅ Clean server (no Python contamination)
- ✅ Isolated formations (no conflicts)
- ✅ Single-file distribution
- ✅ Reproducible deployments
- ✅ Version control with rollback
- ✅ Security (read-only images)

---

## 🚀 Quick Start Guide

### Step 1: Install Prerequisites (2 minutes)

```bash
# macOS
brew install apptainer

# Ubuntu/Debian
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt update && sudo apt install -y apptainer
```

### Step 2: Build Image (10-15 minutes)

```bash
cd /Users/ran/Projects/muxi/code/runtime
./build-sif.sh basic
```

### Step 3: Test Image (1 minute)

```bash
apptainer exec muxi-runtime.sif python -c "import muxi; print('✅ Works!')"
```

### Step 4: Test Formation (2 minutes)

```bash
apptainer run \
    --bind ./examples/test-formation.afs:/formation.afs \
    --env OPENAI_API_KEY=sk-your-key \
    muxi-runtime.sif \
    --formation /formation.afs --port 8000

# Test in another terminal
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "user_id": "test"}'
```

### Step 5: Integrate with Server (5 minutes)

```bash
# Copy SIF to server location
cp muxi-runtime.sif /opt/muxi/

# Update server config
vim ~/.muxi-server/config.yaml
# Add:
#   formations:
#     runtime_type: "singularity"
#     singularity_image: "/opt/muxi/muxi-runtime.sif"

# Restart server
cd ../server
./muxi-server restart
```

**Total Time:** ~20-25 minutes from zero to production! 🎉

---

## 📚 Where to Go Next

### **If you're new to SIF:**
→ Read [SIF-QUICKSTART.md](./SIF-QUICKSTART.md) first (5-minute read)

### **If you're ready to build:**
→ Run `./build-sif.sh` and follow the prompts

### **If you need detailed docs:**
→ Read [SIF-GUIDE.md](./SIF-GUIDE.md) (10 sections, comprehensive)

### **If you want to test:**
→ See [examples/README.md](./examples/README.md)

### **If you're deploying to production:**
→ Build production image: `./build-sif.sh production`
→ Read "Best Practices" section in SIF-GUIDE.md

### **If you hit issues:**
→ Check "Troubleshooting" section in SIF-GUIDE.md
→ Or open an issue: https://github.com/muxi-ai/runtime/issues

---

## 🎓 Learning Path

```
1. SIF-QUICKSTART.md              (5 min read)
   ↓
2. ./build-sif.sh basic           (10-15 min build)
   ↓
3. Test locally                    (5 min)
   ↓
4. Read SIF-GUIDE.md sections 1-5 (15 min)
   ↓
5. Deploy to MUXI Server          (10 min)
   ↓
6. Production: Read sections 6-10 (20 min)
   ↓
7. Build production SIF           (15-20 min)
   ↓
8. Deploy & Monitor               (ongoing)
```

**Total learning time:** ~1-2 hours to full production deployment

---

## ✅ Benefits of This Implementation

### **For Developers:**
- 📖 Complete documentation (48 KB)
- 🛠️ Automated build script
- 🧪 Test examples included
- 🎯 Quick start in 5 minutes
- 📚 Comprehensive guide available

### **For Operations:**
- 🚀 One-command builds
- 📦 Single-file distribution
- 🔒 Read-only security
- 🔄 Easy rollbacks
- 📊 Reproducible deployments

### **For MUXI Server:**
- 🧹 Clean server (no Python!)
- 🔐 Formation isolation
- ⚡ Native performance
- 🎛️ Resource control
- 🏢 Multi-tenant ready

---

## 🔍 Technical Details

### **Image Sizes:**

| Image | Compressed | Uncompressed | Build Time |
|-------|-----------|--------------|------------|
| Basic | ~750 MB | ~2.0 GB | 10-15 min |
| Production | ~1.1 GB | ~3.0 GB | 15-20 min |

### **Dependencies Included:**

**System:**
- Python 3.10
- ffmpeg, tesseract-ocr
- poppler-utils, libmagic1
- gcc, g++, build-essential

**Python Packages:**
- MUXI Runtime + all deps
- FastAPI, Uvicorn
- OneLLM (multi-provider LLM)
- FAISSx (vector search)
- PostgreSQL drivers (psycopg2)
- And 60+ more from requirements.txt

**Production Only:**
- PostgreSQL 17 + pgvector
- FAISSx server (with auth)
- Supervisor (process manager)

### **Build Process:**

1. **Base Image:** Python 3.10 slim (~150 MB)
2. **System Deps:** +300 MB
3. **Python Packages:** +1.5 GB
4. **MUXI Runtime:** +50 MB
5. **Services (prod):** +1 GB
6. **Cleanup:** -200 MB
7. **Compression:** ~35% reduction

---

## 🎉 Summary

You now have everything you need to build and deploy MUXI formations as Singularity containers!

**Created:**
- ✅ 7 new files (guides, definitions, scripts, examples)
- ✅ 48 KB of documentation
- ✅ Automated build system
- ✅ Test formations
- ✅ Quick reference cards

**What's Next:**

1. **Try it:** `./build-sif.sh basic`
2. **Test it:** Follow SIF-QUICKSTART.md
3. **Deploy it:** Integrate with MUXI Server
4. **Scale it:** Use in production

**Questions?**
- 📖 Read SIF-GUIDE.md
- 💬 Ask in GitHub Discussions
- 🐛 Report issues on GitHub

---

**Building the future of AI infrastructure, one container at a time** 🚀

Last Updated: 2025-10-29
