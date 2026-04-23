# MUXI Runtime - Optimized Multi-Stage Build
# This creates a much smaller image by separating build and runtime stages

# ============================================================================
# Stage 1: Builder - Install dependencies and compile
# ============================================================================
FROM python:3.10-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Install uv for fast package management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY requirements.txt pyproject.toml setup.py ./

# Install all dependencies to a temporary location
# This includes compiling binary extensions.
#
# Note: the lean variant uses OneLLM's ``cache`` extra (ONNX-based), which
# does NOT require PyTorch or sentence-transformers. The earlier explicit
# ``pip install torch --index-url .../whl/cpu`` step has been removed
# because nothing in the dep tree pulls torch as a transitive. The
# ``pytorch`` variant (see Dockerfile.pytorch) layers torch + the
# ``local-pytorch`` extra on top of this base.
RUN uv pip install --prefix=/install --no-cache -r requirements.txt

# Copy source and install MUXI
COPY src ./src
RUN uv pip install --prefix=/install --no-cache -e .

# Fix sqlite-vec: the published aarch64 wheel ships a 32-bit ARM binary.
# Compile the correct 64-bit shared library from the amalgamation source.
# Need libsqlite3-dev for sqlite3ext.h header.
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
        echo "Compiling sqlite-vec for aarch64..." && \
        apt-get update && apt-get install -y --no-install-recommends libsqlite3-dev && \
        VEC_VERSION="0.1.7-alpha.10" && \
        python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/asg017/sqlite-vec/releases/download/v${VEC_VERSION}/sqlite-vec-${VEC_VERSION}-amalgamation.tar.gz', 'sqlite-vec.tar.gz')" && \
        echo "c50a6caef46eb32e99f69f1b26808a2e28043b358c9513fed3846ce4776e5ee1  sqlite-vec.tar.gz" | sha256sum -c - && \
        tar xzf sqlite-vec.tar.gz && \
        gcc -O2 -fPIC -shared sqlite-vec.c -o vec0.so && \
        PYVER=$(python -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')") && \
        cp vec0.so /install/lib/${PYVER}/site-packages/sqlite_vec/vec0.so && \
        echo "sqlite-vec compiled and installed for aarch64" && \
        rm -f sqlite-vec.tar.gz sqlite-vec.c sqlite-vec.h vec0.so && \
        apt-get purge -y libsqlite3-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "sqlite-vec: skipping recompilation for $ARCH"; \
    fi

# Note: Skipping spaCy model download to save ~45MB
# Can be downloaded at runtime if needed: python -m spacy download en_core_web_sm

# ============================================================================
# Stage 2: Runtime - Minimal runtime environment
# ============================================================================
FROM python:3.10-slim

LABEL maintainer="Ran Aroussi <ran@aroussi.com>"
LABEL description="MUXI Runtime - Optimized container for AI agent formations"
LABEL version="1.0.0"

# Install ONLY runtime system dependencies (no build tools!)
RUN apt-get update && apt-get install -y \
    # Runtime utilities (not build tools)
    curl \
    wget \
    # Image processing (runtime only)
    poppler-utils \
    tesseract-ocr \
    # Media processing
    ffmpeg \
    # File type detection
    libmagic1 \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy MUXI source
COPY --from=builder /build/src ./src

# Clean up to reduce image size
# Note: numpy._core.tests is imported at runtime by numpy 2.x (for pd_NA),
# so we must preserve it while removing other test directories.
RUN find /usr/local -name "*.pyc" -delete \
    && find /usr/local -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local -name "*.pyo" -delete \
    && find /usr/local -name "tests" -type d -not -path "*/numpy/_core/tests" -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /root/.cache /tmp/*

# HuggingFace cache paths: both HF_HOME and HF_HUB_CACHE point at the same
# directory so models land flat at /opt/hf-cache/models--* (without the
# /hub subdirectory HF would otherwise introduce via HF_HUB_CACHE=$HF_HOME/hub).
# This flat layout matches the bind-mount target — muxi-server bind-mounts
# ~/.muxi/server/cache (host) to /opt/hf-cache (container) at launch, and
# the cache it populates on the host must align 1:1 with where HF reads.
#
# Model weights are NOT baked into this image. muxi-server populates the
# host cache via `onellm download` and bind-mounts it in at runtime. The
# previous pre-download of sentence-transformers models was removed because
# (1) the lean variant has no sentence-transformers, and (2) baked models
# contradict the host-managed cache contract.
#
# /opt/hf-cache is created as an empty stub so the bind-mount always has a
# valid target. In the managed-container path the entrypoint asserts the
# mount is non-empty before launching the runtime (see docker-entrypoint.sh).
ENV HF_HOME=/opt/hf-cache \
    HF_HUB_CACHE=/opt/hf-cache
RUN mkdir -p /opt/hf-cache

# Create necessary directories
RUN mkdir -p /data /logs /formations ~/.muxi

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set environment variables
ENV PYTHONPATH="/app/src:/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Expose default port
EXPOSE 8000

# Health check
# The formation API mounts the health router under the /v1 prefix
# (see formation/server/server.py: `include_router(health_router, prefix="/v1")`),
# so /health alone returns 404 and marks the container unhealthy. Probe
# the real path instead. --start-period covers the Formation init window
# (observed ~4s default variant, ~25s pytorch variant under cold imports).
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/v1/health || exit 1

# Use entrypoint script
ENTRYPOINT ["docker-entrypoint.sh"]

# Default: show usage (user must provide formation path)
CMD []
