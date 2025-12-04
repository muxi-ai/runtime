#!/bin/bash
# Build versioned MUXI Runtime Docker image
# Supports multi-architecture builds (amd64, arm64)

set -e  # Exit on error

echo "======================================"
echo "🏗️  MUXI Runtime Builder"
echo "======================================"
echo ""

# Parse arguments
PLATFORM=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --platform=*)
            PLATFORM="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--platform linux/amd64|linux/arm64]"
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

IMAGE_NAME="muxi-runtime"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Image: $IMAGE_NAME"
echo "   Git Commit: $VCS_REF"
echo "   Build Date: $BUILD_DATE"
if [ -n "$PLATFORM" ]; then
    echo "   Platform: $PLATFORM"
else
    echo "   Platform: (native)"
fi
echo ""

# Build with version tags
echo "🔨 Building Docker image..."
if [ -n "$PLATFORM" ]; then
    docker build \
        --platform "$PLATFORM" \
        --file Dockerfile \
        --tag "$IMAGE_NAME:$VERSION" \
        --tag "$IMAGE_NAME:latest" \
        --build-arg VERSION="$VERSION" \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg VCS_REF="$VCS_REF" \
        .
else
    docker build \
        --file Dockerfile \
        --tag "$IMAGE_NAME:$VERSION" \
        --tag "$IMAGE_NAME:latest" \
        --build-arg VERSION="$VERSION" \
        --build-arg BUILD_DATE="$BUILD_DATE" \
        --build-arg VCS_REF="$VCS_REF" \
        .
fi

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
echo "   This creates: muxi-runtime-$VERSION-linux-{arch}.sif"
echo "   Server expects versioned SIF files to manage multiple runtimes"
echo ""
echo "💡 Multi-arch builds:"
echo "   ./build-runtime.sh --platform linux/amd64   # Intel/AMD"
echo "   ./build-runtime.sh --platform linux/arm64   # Apple Silicon/ARM"
echo ""
