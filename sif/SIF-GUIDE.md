# MUXI Runtime SIF Image Guide

**Building and Testing Singularity Image Format (SIF) Images for MUXI Formations**

---

## Table of Contents

1. [What is a SIF Image?](#what-is-a-sif-image)
2. [Why Use SIF for MUXI?](#why-use-sif-for-muxi)
3. [Prerequisites](#prerequisites)
4. [Building a SIF Image](#building-a-sif-image)
5. [Testing with MUXI Server](#testing-with-muxi-server)
6. [SIF Image Structure](#sif-image-structure)
7. [Best Practices](#best-practices)
8. [Optimization Tips](#optimization-tips)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Topics](#advanced-topics)

---

## What is a SIF Image?

**SIF (Singularity Image Format)** is a read-only, compressed container image format used by Singularity/Apptainer. It packages an entire Linux environment into a single file that can be executed anywhere Singularity/Apptainer is installed.

**Key Features:**
- **Single File:** Entire container in one `.sif` file (easy distribution)
- **Read-Only:** Immutable image ensures consistency
- **No Root Required:** Can run without privileged access
- **HPC Optimized:** Designed for scientific computing and multi-tenant systems
- **Native GPU Support:** Direct access to hardware acceleration
- **Portable:** Run the same image on any Linux system with Singularity/Apptainer

---

## Why Use SIF for MUXI?

The MUXI Server architecture uses SIF images to provide:

### 1. **Clean Server Environment**
```
Traditional Approach:          SIF Approach:
┌─────────────────────┐      ┌─────────────────────┐
│   MUXI Server       │      │   MUXI Server       │
│                     │      │                     │
│   Python 3.10       │      │   (No Python!)      │
│   pip packages      │      │   (No packages!)    │
│   MUXI Runtime      │      │   Just Go binary    │
│   Dependencies      │      │                     │
│   Conflicts!        │      │   Spawns SIF →      │
└─────────────────────┘      └─────────────────────┘
                                    ↓
                              Formation.sif
                              (self-contained)
```

### 2. **Formation Isolation**
- Each formation runs in its own isolated environment
- No dependency conflicts between formations
- Different Python versions per formation if needed
- Clean resource management

### 3. **Deployment Benefits**
- **Single File Distribution:** Just copy one `.sif` file
- **Reproducible:** Same image = same behavior everywhere
- **Versioning:** Easy to track and rollback
- **Security:** Read-only, signed images
- **Performance:** Native speed, minimal overhead

### 4. **Multi-Tenant Support**
- Run multiple formations with different requirements
- Resource limits per container
- Secure credential isolation
- Independent scaling

---

## Prerequisites

### 1. Install Singularity/Apptainer

#### **Linux (Recommended)**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:apptainer/ppa
sudo apt-get update
sudo apt-get install -y apptainer

# Verify installation
apptainer --version
```

#### **macOS**
```bash
# Install via Homebrew (requires Docker Desktop)
brew install --cask docker
brew install apptainer

# Note: On macOS, Apptainer runs Linux containers via Docker
# This is automatic and transparent
```

#### **Alternative: Use Docker to Build**
If you don't want to install Apptainer locally, you can use Docker to build the SIF:
```bash
# Use Apptainer Docker image
docker run --rm -v $(pwd):/work quay.io/singularity/singularity:latest \
    build /work/muxi-runtime.sif /work/muxi-runtime.def
```

### 2. Install Docker (for building from Docker images)
```bash
# macOS
brew install --cask docker

# Linux
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 3. Clone MUXI Runtime
```bash
git clone https://github.com/muxi-ai/runtime
cd runtime
```

---

## Building a SIF Image

### Method 1: From Definition File (Recommended)

Create a **Singularity definition file** (`muxi-runtime.def`):

```singularity
Bootstrap: docker
From: python:3.10-slim

%files
    # Copy runtime source code
    ./src /app/src
    ./requirements.txt /app/requirements.txt
    ./pyproject.toml /app/pyproject.toml
    ./setup.py /app/setup.py

%post
    # Update system and install dependencies
    apt-get update && apt-get install -y \
        build-essential \
        gcc \
        g++ \
        curl \
        wget \
        git \
        poppler-utils \
        tesseract-ocr \
        ffmpeg \
        libmagic1 \
        && rm -rf /var/lib/apt/lists/*

    # Install uv for faster package management
    pip install --no-cache-dir uv

    # Install Python packages
    cd /app
    uv pip install --system -r requirements.txt

    # Install MUXI runtime
    uv pip install --system -e .

    # Download spaCy model
    python -m spacy download en_core_web_sm

    # Create necessary directories
    mkdir -p /data /logs /formations

    # Clean up
    apt-get clean
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

%environment
    export PYTHONPATH=/app/src:/app:$PYTHONPATH
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1
    export LC_ALL=C.UTF-8
    export LANG=C.UTF-8

%runscript
    # Default: Run MUXI formation server
    cd /app
    exec python -m muxi.server "$@"

%labels
    Author Ran Aroussi
    Version 1.0.0
    Description MUXI Runtime - AI Agent Formation Container

%help
    MUXI Runtime Container

    This container packages the MUXI runtime for executing AI formations.

    Usage:
        # Run formation server (default)
        singularity run muxi-runtime.sif

        # Execute specific Python script
        singularity exec muxi-runtime.sif python your_script.py

        # Interactive shell
        singularity shell muxi-runtime.sif

    Environment Variables:
        MUXI_FORMATIONS_DIR - Directory for formation files
        MUXI_LOGS_DIR - Directory for logs
        MUXI_DATA_DIR - Directory for data storage
```

**Build the SIF:**
```bash
# Build the SIF image (requires sudo on Linux)
sudo apptainer build muxi-runtime.sif muxi-runtime.def

# Or use the Docker method (no sudo needed)
docker run --rm --privileged -v $(pwd):/work \
    quay.io/singularity/singularity:latest \
    build /work/muxi-runtime.sif /work/muxi-runtime.def
```

### Method 2: From Docker Image

If you already have a Docker image:

```bash
# Build Docker image first
docker build -t muxi-runtime:latest -f e2e/docker/Dockerfile .

# Convert to SIF
sudo apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest

# Or pull from registry
sudo apptainer build muxi-runtime.sif docker://username/muxi-runtime:latest
```

### Method 3: Production-Ready Definition (Complete Services)

For a full production image with all services:

```singularity
Bootstrap: docker
From: python:3.10-slim

%files
    ./src /app/src
    ./requirements.txt /app/requirements.txt
    ./pyproject.toml /app/pyproject.toml
    ./setup.py /app/setup.py
    ./e2e/assets/faissx-auth.json /app/faissx-auth.json

%post
    # Add PostgreSQL repository
    apt-get update
    apt-get install -y gnupg wget lsb-release
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
        gpg --dearmor -o /usr/share/keyrings/postgresql-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/postgresql-keyring.gpg] http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list

    # Install system dependencies
    apt-get update && apt-get install -y \
        postgresql-17 \
        postgresql-client-17 \
        postgresql-17-pgvector \
        build-essential \
        gcc \
        g++ \
        curl \
        wget \
        git \
        supervisor \
        netcat-openbsd \
        poppler-utils \
        tesseract-ocr \
        ffmpeg \
        libmagic1 \
        && rm -rf /var/lib/apt/lists/*

    # Install uv for package management
    pip install --no-cache-dir uv

    # Install Python packages
    cd /app
    uv pip install --system faissx fastapi uvicorn httpx aiofiles
    uv pip install --system -r requirements.txt
    uv pip install --system -e .

    # Download spaCy model
    python -m spacy download en_core_web_sm || true

    # Create directories
    mkdir -p /data /logs /formations /var/run/postgresql /var/lib/postgresql/17

    # Initialize PostgreSQL
    chown -R postgres:postgres /var/lib/postgresql /var/run/postgresql
    su - postgres -c "/usr/lib/postgresql/17/bin/initdb -D /var/lib/postgresql/17/main"
    echo "listen_addresses = '*'" >> /var/lib/postgresql/17/main/postgresql.conf
    echo "max_connections = 200" >> /var/lib/postgresql/17/main/postgresql.conf

    # Clean up
    apt-get clean
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

%environment
    export PYTHONPATH=/app/src:/app:$PYTHONPATH
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1
    export PATH=/usr/lib/postgresql/17/bin:$PATH
    export PGDATA=/var/lib/postgresql/17/main

%startscript
    # Start all services with supervisor
    /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

%runscript
    # Run formation server
    cd /app
    exec python -m muxi.server "$@"

%labels
    Author Ran Aroussi
    Version 1.0.0-production
    Description MUXI Runtime - Production Container with Services
```

---

## Testing with MUXI Server

### 1. Create Test Formation

Create a simple formation YAML (`test-formation.afs`):

```yaml
schema: "1.0.0"
id: "test-assistant"
name: "Test Assistant"
description: "Simple test formation for SIF validation"

llm:
  models:
    - text: "openai/gpt-4o-mini"
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"

agents:
  - id: "assistant"
    name: "General Assistant"
    system_message: "You are a helpful AI assistant. Keep responses concise."

memory:
  buffer:
    size: 20
    vector_search: false
```

### 2. Test SIF Image Locally

```bash
# Test 1: Verify image integrity
apptainer inspect muxi-runtime.sif

# Test 2: Run shell inside container
apptainer shell muxi-runtime.sif
# Inside container:
python --version
python -c "import muxi; print(muxi.__version__)"
exit

# Test 3: Execute Python directly
apptainer exec muxi-runtime.sif python -c "from muxi import Formation; print('✅ MUXI Runtime loaded')"

# Test 4: Run formation (bind mount formation file)
apptainer exec \
    --bind ./test-formation.afs:/formation.afs \
    --bind $(pwd)/data:/data \
    --env OPENAI_API_KEY=sk-your-key-here \
    muxi-runtime.sif \
    python -m muxi.server run --formation /formation.afs
```

### 3. Integration with MUXI Server

Now test with the actual MUXI Server (from the `server` repository):

#### **Step 1: Configure MUXI Server for SIF**

Edit `~/.muxi-server/config.yaml`:

```yaml
server:
  port: 7890
  host: "0.0.0.0"

formations:
  runtime_type: "singularity"  # Enable SIF runtime
  singularity_image: "/path/to/muxi-runtime.sif"

  port_range_start: 8000
  port_range_end: 9000
  logs_dir: "~/.muxi-server/logs"
  formations_dir: "~/.muxi-server/formations"
  bind_host: "127.0.0.1"

  auto_restart: true
  max_restart_count: 10
  restart_delay: 1
```

#### **Step 2: Start MUXI Server**

```bash
# Start server (from server repository)
cd ../server
./muxi-server serve
```

#### **Step 3: Deploy Formation with SIF**

```bash
# Create formation bundle
tar czf formation.tar.gz test-formation.afs

# Deploy to server
curl -X POST http://localhost:7890/rpc/formations/deploy \
  -H "Content-Type: application/gzip" \
  -H "X-HMAC-Signature: $(calculate_hmac formation.tar.gz)" \
  --data-binary @formation.tar.gz
```

#### **Step 4: Verify Formation is Running**

```bash
# List formations
curl http://localhost:7890/rpc/formations

# Check formation health
curl http://localhost:7890/api/test-assistant/health

# Test formation endpoint
curl -X POST http://localhost:7890/api/test-assistant/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello! Can you confirm you are running in a SIF container?",
    "user_id": "test-user"
  }'
```

### 4. Verify SIF Execution

Check that the formation is actually running in Singularity:

```bash
# Check process tree
ps aux | grep singularity

# You should see something like:
# singularity run instance://formation-test-assistant /app/muxi-runtime.sif

# Check logs
tail -f ~/.muxi-server/logs/formation-test-assistant.log
```

---

## SIF Image Structure

A production MUXI SIF image contains:

```
muxi-runtime.sif (read-only image)
│
├── /app/                         # Application code
│   ├── src/muxi/                # MUXI runtime source
│   ├── requirements.txt         # Python dependencies
│   └── pyproject.toml           # Project metadata
│
├── /data/                        # Data directory (bind mount)
├── /logs/                        # Logs directory (bind mount)
├── /formations/                  # Formations directory (bind mount)
│
├── /usr/bin/                     # System binaries
│   ├── python3.10               # Python interpreter
│   ├── postgres                 # PostgreSQL (optional)
│   └── ...
│
└── /usr/local/lib/python3.10/   # Python packages
    ├── muxi/                    # MUXI runtime
    ├── fastapi/                 # Web framework
    ├── onellm/                  # LLM interface
    └── ...                      # All dependencies
```

**Bind Mounts (Runtime):**
```bash
# MUXI Server will bind mount:
-B ~/.muxi-server/formations/{id}/current:/formation     # Formation files
-B ~/.muxi-server/formations/{id}/data:/data             # Data persistence
-B ~/.muxi-server/logs:/logs                             # Log output
```

---

## Best Practices

### 1. **Image Optimization**

```singularity
%post
    # Clean package manager cache
    apt-get clean
    rm -rf /var/lib/apt/lists/*

    # Remove pip cache
    pip cache purge

    # Remove build dependencies after install
    apt-get remove -y build-essential gcc g++
    apt-get autoremove -y

    # Clear tmp directories
    rm -rf /tmp/* /var/tmp/*
```

### 2. **Layer Efficiency**

Combine related commands to reduce layers:

```singularity
%post
    # ❌ BAD: Multiple RUN commands
    apt-get update
    apt-get install -y python3
    pip install numpy

    # ✅ GOOD: Combined in one section
    apt-get update && apt-get install -y python3 && \
        pip install numpy && \
        rm -rf /var/lib/apt/lists/*
```

### 3. **Version Pinning**

Pin all versions for reproducibility:

```singularity
Bootstrap: docker
From: python:3.10.12-slim  # Exact version, not just 3.10

%post
    pip install --no-cache-dir \
        muxi==1.0.0 \
        fastapi==0.108.0 \
        onellm==0.20251013.0
```

### 4. **Security**

```singularity
%post
    # Create non-root user
    useradd -m -u 1000 muxi
    chown -R muxi:muxi /app /data /logs

# Run as non-root by default
%runscript
    exec su - muxi -c "cd /app && python -m muxi.server $*"
```

### 5. **Testing During Build**

```singularity
%test
    # Verify Python installation
    python --version

    # Verify MUXI runtime
    python -c "import muxi; print(muxi.__version__)"

    # Test dependencies
    python -c "import fastapi, onellm, muxi"

    # Verify system tools
    which ffmpeg tesseract
```

---

## Optimization Tips

### 1. **Multi-Stage Builds** (Advanced)

For smaller images, build dependencies separately:

```singularity
# Stage 1: Builder
Bootstrap: docker
From: python:3.10-slim as builder
Stage: build

%post
    apt-get update && apt-get install -y build-essential
    pip install --user muxi fastapi onellm

# Stage 2: Runtime
Bootstrap: docker
From: python:3.10-slim

%files from build
    /root/.local /root/.local

%post
    # Only runtime dependencies
    apt-get update && apt-get install -y ffmpeg libmagic1
```

### 2. **Caching Strategy**

Use Docker BuildKit cache for faster rebuilds:

```bash
# Build with BuildKit cache
DOCKER_BUILDKIT=1 docker build \
    --cache-from muxi-runtime:latest \
    --cache-to type=local,dest=/tmp/cache \
    -t muxi-runtime:latest .

# Convert to SIF
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest
```

### 3. **Parallel Builds**

Build multiple architectures:

```bash
# Build for AMD64 and ARM64
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t muxi-runtime:latest .
```

### 4. **Image Compression**

SIF images are already compressed, but you can optimize:

```bash
# Build with maximum compression
apptainer build --compress muxi-runtime.sif muxi-runtime.def

# Verify compression
ls -lh muxi-runtime.sif
```

---

## Troubleshooting

### Problem: "Permission denied" when building

**Solution:**
```bash
# Use sudo on Linux
sudo apptainer build muxi-runtime.sif muxi-runtime.def

# Or use Docker method (no sudo)
docker run --rm --privileged -v $(pwd):/work \
    quay.io/singularity/singularity:latest \
    build /work/muxi-runtime.sif /work/muxi-runtime.def
```

### Problem: "Module not found" errors at runtime

**Solution:**
```bash
# Verify all dependencies are installed
apptainer exec muxi-runtime.sif pip list

# Check PYTHONPATH
apptainer exec muxi-runtime.sif echo $PYTHONPATH

# Test specific import
apptainer exec muxi-runtime.sif python -c "import muxi"
```

### Problem: Formation can't access files

**Solution:**
```bash
# Ensure bind mounts are correct
apptainer run \
    --bind ./formations:/formations:ro \
    --bind ./data:/data:rw \
    --bind ./logs:/logs:rw \
    muxi-runtime.sif

# Check permissions
ls -la formations/ data/ logs/
```

### Problem: Out of memory during build

**Solution:**
```bash
# Increase Docker memory limit (macOS)
# Docker Desktop → Settings → Resources → Memory: 8GB+

# Or build in stages
docker build --target builder -t muxi-builder .
docker build --target runtime -t muxi-runtime .
apptainer build muxi-runtime.sif docker-daemon://muxi-runtime:latest
```

### Problem: SIF image is too large

**Solution:**
```bash
# Check image size breakdown
apptainer inspect muxi-runtime.sif

# Remove unnecessary packages
%post
    apt-get remove -y build-essential
    apt-get autoremove -y
    pip cache purge
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Use slim base image
Bootstrap: docker
From: python:3.10-slim  # Not python:3.10
```

### Problem: Formation fails to start

**Solution:**
```bash
# Run with verbose logging
apptainer run --debug muxi-runtime.sif

# Check if ports are available
netstat -tuln | grep 8000-9000

# Verify environment variables
apptainer run --env-file .env muxi-runtime.sif

# Test in shell mode
apptainer shell muxi-runtime.sif
# Inside: python -m muxi.server run --formation /formation.afs
```

---

## Advanced Topics

### 1. **GPU Support**

For GPU-accelerated formations:

```singularity
Bootstrap: docker
From: nvidia/cuda:12.2.0-runtime-ubuntu22.04

%post
    # Install Python and MUXI
    apt-get update && apt-get install -y python3.10 python3-pip
    pip install muxi torch torchvision --index-url https://download.pytorch.org/whl/cu122

%environment
    export CUDA_VISIBLE_DEVICES=0

%runscript
    exec python -m muxi.server "$@"
```

**Run with GPU:**
```bash
apptainer run --nv muxi-runtime-gpu.sif  # --nv enables NVIDIA GPU
```

### 2. **Network Isolation**

For secure multi-tenant deployments:

```bash
# Run with restricted network
apptainer run \
    --network none \
    --bind ./formations:/formations:ro \
    muxi-runtime.sif

# Or with specific network
apptainer run \
    --network bridge \
    --network-args "portmap=8000:8000/tcp" \
    muxi-runtime.sif
```

### 3. **Resource Limits**

Limit container resources:

```bash
# CPU and memory limits (requires cgroups v2)
apptainer run \
    --cpu-shares 512 \
    --memory 2G \
    muxi-runtime.sif

# Use with systemd for production
systemd-run --scope -p CPUQuota=50% -p MemoryLimit=2G \
    apptainer run muxi-runtime.sif
```

### 4. **Signed Images**

For production security:

```bash
# Generate key pair
apptainer key newpair

# Sign image
apptainer sign muxi-runtime.sif

# Verify before running
apptainer verify muxi-runtime.sif
```

### 5. **OCI/Docker Compatibility**

Convert between formats:

```bash
# SIF → Docker
apptainer build --docker muxi-runtime:latest muxi-runtime.sif

# Docker → OCI → SIF
docker save muxi-runtime:latest | gzip > muxi-runtime.tar.gz
apptainer build muxi-runtime.sif docker-archive://muxi-runtime.tar.gz
```

---

## Quick Reference

### Common Commands

```bash
# Build from definition
apptainer build myimage.sif myimage.def

# Run container
apptainer run myimage.sif

# Execute command
apptainer exec myimage.sif python script.py

# Interactive shell
apptainer shell myimage.sif

# Inspect image
apptainer inspect myimage.sif

# Run as instance (background)
apptainer instance start myimage.sif myinstance
apptainer instance list
apptainer instance stop myinstance
```

### Environment Variables

```bash
# Pass environment variables
apptainer run --env VAR=value myimage.sif
apptainer run --env-file .env myimage.sif

# Clean environment
apptainer run --cleanenv myimage.sif
```

### Bind Mounts

```bash
# Bind single directory
apptainer run --bind /host/path:/container/path myimage.sif

# Multiple binds
apptainer run \
    --bind /data:/data \
    --bind /logs:/logs:rw \
    --bind /config:/config:ro \
    myimage.sif

# Automatic HOME binding (default behavior)
apptainer run myimage.sif  # $HOME is bound automatically
```

---

## Summary

**Building SIF images for MUXI formations provides:**

✅ **Isolation:** Clean server, no dependency conflicts
✅ **Portability:** Single-file distribution
✅ **Reproducibility:** Consistent behavior everywhere
✅ **Security:** Read-only, signed images
✅ **Performance:** Native speed, minimal overhead
✅ **Scalability:** Multi-tenant support with resource limits

**Next Steps:**

1. Build your first SIF: `apptainer build muxi-runtime.sif muxi-runtime.def`
2. Test locally: `apptainer run muxi-runtime.sif`
3. Deploy to MUXI Server: Configure `runtime_type: "singularity"`
4. Monitor in production: Check logs and resource usage
5. Optimize: Review image size and build time

**Resources:**

- [Apptainer Documentation](https://apptainer.org/docs/)
- [MUXI Runtime GitHub](https://github.com/muxi-ai/runtime)
- [MUXI Server GitHub](https://github.com/muxi-ai/server)
- [Singularity Hub](https://singularity-hub.org/)

---

**Questions or issues?** Open an issue at [github.com/muxi-ai/runtime/issues](https://github.com/muxi-ai/runtime/issues)

**Building the future of AI infrastructure, one container at a time** 🚀
