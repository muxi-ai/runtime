#!/bin/bash
# Build versioned MUXI Runtime Docker image
# Simple wrapper around docker build with version management

set -e  # Exit on error

echo "======================================"
echo "🏗️  MUXI Runtime Builder"
echo "======================================"
echo ""

# Read version from .version file
if [ -f "src/muxi/.version" ]; then
    VERSION=$(cat src/muxi/.version | tr -d '[:space:]')
else
    echo "❌ Error: src/muxi/.version not found"
    exit 1
fi

IMAGE_NAME="muxi-runtime"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Image: $IMAGE_NAME"
echo "   Git Commit: $VCS_REF"
echo "   Build Date: $BUILD_DATE"
echo ""

# Build with version tags
echo "🔨 Building Docker image..."
docker build \
    --file Dockerfile \
    --tag "$IMAGE_NAME:$VERSION" \
    --tag "$IMAGE_NAME:latest" \
    --build-arg VERSION="$VERSION" \
    --build-arg BUILD_DATE="$BUILD_DATE" \
    --build-arg VCS_REF="$VCS_REF" \
    .

echo ""
echo "✅ Build Complete!"
echo ""

# Show image info
docker images "$IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | head -3

echo ""
echo "📝 Docker Images Created:"
echo "   • $IMAGE_NAME:$VERSION"
echo "   • $IMAGE_NAME:latest"
echo ""
echo "✨ Next Steps:"
echo ""
echo "1️⃣  Test locally:"
echo "   docker run --rm -v \$(pwd)/e2e/tests/1_foundation/formations/formation-base:/formation \\"
echo "              -e PORT=8000 -e HOST=0.0.0.0 -p 8000:8000 \\"
echo "              $IMAGE_NAME:$VERSION /formation/formation.yaml"
echo ""
echo "2️⃣  Convert to SIF (for MUXI Server):"
echo "   ./build-sif.sh"
echo ""
echo "   This creates: muxi-runtime-$VERSION-{platform}.sif"
echo "   Server expects versioned SIF files to manage multiple runtimes"
echo ""
