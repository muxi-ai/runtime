# MUXI Runtime - Production Docker Image
# Basic runtime for running MUXI formations
FROM python:3.10-slim

LABEL maintainer="Ran Aroussi <ran@aroussi.com>"
LABEL description="MUXI Runtime - Container for AI agent formations"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Build dependencies
    build-essential \
    gcc \
    g++ \
    # System utilities
    curl \
    wget \
    git \
    # Image processing
    poppler-utils \
    tesseract-ocr \
    # Audio/Video processing
    ffmpeg \
    # Magic file detection
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt pyproject.toml setup.py ./

# Install uv for faster package management
RUN pip install --no-cache-dir uv

# Install Python packages
RUN uv pip install --system -r requirements.txt

# Copy source code
COPY src ./src

# Note: schemas and context are symlinks outside build context
# They're not needed at runtime - only for development reference

# Install MUXI runtime in development mode
RUN uv pip install --system -e .

# Download spaCy model (optional but recommended)
RUN python -m spacy download en_core_web_sm || true

# Create necessary directories
RUN mkdir -p /data /logs /formations

# Set environment variables
ENV PYTHONPATH=/app/src:/app:$PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Expose default port (formations will use this)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command: Run MUXI server
# Override with your own command or bind mount formation files
CMD ["python", "-m", "muxi.server"]
