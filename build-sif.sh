#!/bin/bash
# Convert MUXI Runtime Docker image to Singularity SIF
# This creates a SIF file with proper naming for MUXI Server
# Supports building for specific architectures

set -e  # Exit on error

echo "======================================"
echo "Converting Docker to Singularity SIF"
echo "======================================"
echo ""

# Parse arguments
ARCH=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --arch=*)
            ARCH="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--arch amd64|arm64]"
            exit 1
            ;;
    esac
done

# Read version from .version file
if [ -f "src/muxi/.version" ]; then
    VERSION=$(cat src/muxi/.version | tr -d '[:space:]')
else
    echo "❌ Error: src/muxi/.version not found"
    exit 1
fi

# Configuration
IMAGE_NAME="muxi-runtime"

# Determine architecture
if [ -z "$ARCH" ]; then
    # Auto-detect from Docker image
    ARCH=$(docker inspect "$IMAGE_NAME:$VERSION" --format '{{.Architecture}}' 2>/dev/null || echo "")
    if [ -z "$ARCH" ]; then
        # Fallback to host architecture
        case "$(uname -m)" in
            aarch64|arm64)
                ARCH="arm64"
                ;;
            x86_64|amd64)
                ARCH="amd64"
                ;;
            *)
                ARCH="$(uname -m)"
                ;;
        esac
    fi
fi

TARBALL="muxi-runtime-$VERSION.tar"
SIF_DIR="sif-builds"
SIF_FILE="$SIF_DIR/muxi-runtime-$VERSION-linux-$ARCH.sif"

# Ensure sif-builds directory exists
mkdir -p "$SIF_DIR"

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Architecture: $ARCH"
echo "   Docker Image: $IMAGE_NAME:$VERSION"
echo "   Tarball: $TARBALL"
echo "   SIF File: $SIF_FILE"
echo ""

# Check if Docker image exists
if ! docker image inspect "$IMAGE_NAME:$VERSION" > /dev/null 2>&1; then
    echo "❌ Error: Docker image $IMAGE_NAME:$VERSION not found"
    echo ""
    echo "Build it first:"
    echo "   ./build-runtime.sh                        # Native arch"
    echo "   ./build-runtime.sh --platform linux/amd64 # Intel/AMD"
    echo "   ./build-runtime.sh --platform linux/arm64 # ARM"
    exit 1
fi

# Export Docker image to tarball
echo "💾 Exporting Docker image to tarball..."
docker save "$IMAGE_NAME:$VERSION" -o "$TARBALL"
echo "   ✓ Created $TARBALL"
echo ""

# Convert to SIF
echo "🔄 Converting to Singularity SIF..."

# Check if singularity is installed natively
if command -v singularity &> /dev/null; then
    echo "   Using native Singularity..."
    singularity build "$SIF_FILE" "docker-archive://$TARBALL"
else
    echo "   Singularity not found locally, using Docker-wrapped Singularity..."
    # Use our runtime-runner image which has Singularity
    docker run --rm --privileged \
        -v "$(pwd):/work" \
        -w /work \
        ghcr.io/muxi-ai/runtime-runner:latest \
        build "$SIF_FILE" "docker-archive://$TARBALL"
fi

echo "   ✓ Created $SIF_FILE"

# Also create a "latest" version for server fallback
# The MUXI Server downloads this when formation doesn't specify a version
LATEST_SIF_FILE="$SIF_DIR/muxi-runtime-latest-linux-${ARCH}.sif"
cp "$SIF_FILE" "$LATEST_SIF_FILE"
echo "   ✓ Created $LATEST_SIF_FILE (for server fallback)"
echo ""

# Show file sizes
echo "📊 File Information:"
echo "   Tarball: $(du -h "$TARBALL" | cut -f1)"
echo "   SIF: $(du -h "$SIF_FILE" | cut -f1)"
echo ""

# Cleanup tarball
echo "🧹 Cleaning up..."
rm "$TARBALL"
echo "   ✓ Removed $TARBALL"
echo ""

echo "✅ Conversion Complete!"
echo ""
echo "SIF Files:"
echo "   Versioned: $SIF_FILE"
echo "   Latest:    $LATEST_SIF_FILE"
echo ""
echo "📝 For MUXI Server (copy both to runtimes directory):"
echo "   cp $SIF_FILE ~/.muxi/server/runtimes/"
echo "   cp $LATEST_SIF_FILE ~/.muxi/server/runtimes/"
echo ""
SIF_FILENAME=$(basename "$SIF_FILE")
echo "✨ Test the SIF:"
echo "   # Using runtime-runner (macOS/Windows):"
echo "   docker run --rm --privileged \\"
echo "       -v \$(pwd)/$SIF_FILE:/sif/runtime.sif:ro \\"
echo "       -v \$(pwd)/formations/example-formation:/formation:ro \\"
echo "       -p 8001:8001 \\"
echo "       ghcr.io/muxi-ai/runtime-runner:latest \\"
echo "       exec --bind /formation:/formation /sif/runtime.sif \\"
echo "       python -m muxi.utils.run_formation /formation/formation.afs --port 8001 --host 0.0.0.0"
echo ""
echo "💡 Build for specific architecture:"
echo "   ./build-runtime.sh --platform linux/arm64 && ./build-sif.sh --arch arm64"
echo "   ./build-runtime.sh --platform linux/amd64 && ./build-sif.sh --arch amd64"
echo ""
