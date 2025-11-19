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

# Create necessary directories
RUN mkdir -p /data /logs /formations

# Set environment variables
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Expose default port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: Print usage and keep container alive
# Override in docker-compose.yaml or when running:
#   docker run muxi-runtime python -m muxi.utils.run_formation /formations/my-formation/formation.yaml
CMD ["sh", "-c", "echo 'MUXI Runtime v0.2025.0 - Ready!' && echo 'To run a formation, use: python -m muxi.utils.run_formation /formations/your-formation/formation.yaml' && tail -f /dev/null"]
