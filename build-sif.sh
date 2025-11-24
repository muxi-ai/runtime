#!/bin/bash
# Convert MUXI Runtime Docker image to Singularity SIF
# This creates a SIF file with proper naming for MUXI Server

set -e  # Exit on error

echo "======================================"
echo "Converting Docker to Singularity SIF"
echo "======================================"
echo ""

# Read version from .version file
if [ -f "src/muxi/.version" ]; then
    VERSION=$(cat src/muxi/.version | tr -d '[:space:]')
else
    echo "❌ Error: src/muxi/.version not found"
    exit 1
fi

# Configuration
IMAGE_NAME="muxi-runtime"
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"

# Normalize architecture names (aarch64 -> arm64, x86_64 -> amd64)
case "$(uname -m)" in
    aarch64)
        ARCH="arm64"
        ;;
    x86_64)
        ARCH="amd64"
        ;;
    arm64)
        ARCH="arm64"
        ;;
    *)
        ARCH="$(uname -m)"
        ;;
esac

PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$ARCH"
TARBALL="muxi-runtime-$VERSION.tar"
SIF_FILE="muxi-runtime-$VERSION-$PLATFORM.sif"

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Platform: $PLATFORM"
echo "   Docker Image: $IMAGE_NAME:$VERSION"
echo "   Tarball: $TARBALL"
echo "   SIF File: $SIF_FILE"
echo ""

# Check if Docker image exists
if ! docker image inspect "$IMAGE_NAME:$VERSION" > /dev/null 2>&1; then
    echo "❌ Error: Docker image $IMAGE_NAME:$VERSION not found"
    echo "   Run ./build-docker.sh first"
    exit 1
fi

# Check if singularity is installed
if ! command -v singularity &> /dev/null; then
    echo "❌ Error: singularity command not found"
    echo ""
    echo "On macOS, Singularity must run inside Docker:"
    echo "   docker run --rm --privileged -v \$(pwd):/work -w /work \\"
    echo "          quay.io/singularity/singularity:latest \\"
    echo "          build $SIF_FILE docker-archive://$TARBALL"
    echo ""
    echo "On Linux, install Singularity/Apptainer:"
    echo "   https://apptainer.org/docs/user/latest/quick_start.html"
    exit 1
fi

# Export Docker image to tarball
echo "💾 Exporting Docker image to tarball..."
docker save "$IMAGE_NAME:$VERSION" -o "$TARBALL"
echo "   ✓ Created $TARBALL"
echo ""

# Convert to SIF
echo "🔄 Converting to Singularity SIF..."
singularity build "$SIF_FILE" "docker-archive://$TARBALL"
echo "   ✓ Created $SIF_FILE"
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
echo "SIF File: $SIF_FILE"
echo ""
echo "📝 For MUXI Server:"
echo "   Place this file in: ~/.muxi/server/runtimes/"
echo "   Server expects: muxi-runtime-{version}-{platform}.sif"
echo ""
echo "✨ Test the SIF:"
echo "   singularity exec $SIF_FILE python -m muxi.utils.run_formation --help"
echo ""
