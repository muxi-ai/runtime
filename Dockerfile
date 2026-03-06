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

# Install PyTorch CPU-only version first (avoids 4GB+ CUDA dependencies)
# This must be done before other requirements to prevent CUDA version from being pulled
RUN uv pip install --prefix=/install --no-cache \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install all dependencies to a temporary location
# This includes compiling binary extensions
RUN uv pip install --prefix=/install --no-cache -r requirements.txt

# Copy source and install MUXI
COPY src ./src
RUN uv pip install --prefix=/install --no-cache -e .

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

# Pre-download the sentence-transformers model used by OneLLM cache.
# Without this, the first formation startup downloads ~118MB from HuggingFace,
# adding ~80s to cold-start time inside SIF containers.
# Stored in /opt/hf-cache (not /root/.cache) because Singularity mounts the
# host home directory over /root, hiding anything baked into the image there.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

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
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script
ENTRYPOINT ["docker-entrypoint.sh"]

# Default: show usage (user must provide formation path)
CMD []
