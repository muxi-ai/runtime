#!/bin/bash
# Build versioned MUXI Runtime Docker images.
# Supports runtime variants (default, pytorch, cuda) and multi-arch builds.

set -euo pipefail

show_usage() {
    cat <<'EOF'
Usage: ./scripts/build/runtime.sh [--platform linux/amd64|linux/arm64] [--variant default|pytorch|cuda]

Examples:
  ./scripts/build/runtime.sh
  ./scripts/build/runtime.sh --platform linux/amd64
  ./scripts/build/runtime.sh --variant pytorch
  ./scripts/build/runtime.sh --platform linux/amd64 --variant cuda

Notes:
  - The default variant builds from ./Dockerfile.
  - The pytorch/cuda variants inherit from the locally built lean image
    (muxi-runtime:<version>), so build the default variant first.
  - The cuda variant is EXPERIMENTAL — arm64 wheels for faiss-gpu-cu12,
    onnxruntime-gpu and CUDA-enabled torch are not published, so cuda
    only works on linux/amd64 hosts with a real NVIDIA GPU and the
    nvidia-container-toolkit. Treat it as unvalidated until it lands in CI.
EOF
}

echo "======================================"
echo "🏗️  MUXI Runtime Builder"
echo "======================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PLATFORM=""
VARIANT="default"

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
        --variant)
            VARIANT="$2"
            shift 2
            ;;
        --variant=*)
            VARIANT="${1#*=}"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo ""
            show_usage
            exit 1
            ;;
    esac
done

case "$VARIANT" in
    default)
        DOCKERFILE="Dockerfile"
        TAG_SUFFIX=""
        VARIANT_LABEL="default"
        ;;
    pytorch)
        DOCKERFILE="Dockerfile.pytorch"
        TAG_SUFFIX="-pytorch"
        VARIANT_LABEL="pytorch"
        ;;
    cuda)
        DOCKERFILE="Dockerfile.cuda"
        TAG_SUFFIX="-cuda"
        VARIANT_LABEL="cuda (experimental)"
        echo "⚠️  The cuda variant is experimental. It is only buildable on linux/amd64"
        echo "    hosts with NVIDIA tooling and is not covered by the macOS dev loop."
        echo ""
        ;;
    *)
        echo "❌ Error: unsupported variant '$VARIANT'"
        echo ""
        show_usage
        exit 1
        ;;
esac

cd "$PROJECT_ROOT"

VERSION_FILE="src/muxi/runtime/.version"
if [ ! -f "$VERSION_FILE" ]; then
    echo "❌ Error: $VERSION_FILE not found"
    exit 1
fi

VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
IMAGE_NAME="muxi-runtime"
VERSION_TAG="${IMAGE_NAME}:${VERSION}${TAG_SUFFIX}"
LATEST_TAG="${IMAGE_NAME}:latest${TAG_SUFFIX}"
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [ "$VARIANT" != "default" ] && ! docker image inspect "${IMAGE_NAME}:${VERSION}" >/dev/null 2>&1; then
    echo "❌ Error: base image ${IMAGE_NAME}:${VERSION} not found"
    echo ""
    echo "Build the lean/default image first:"
    echo "   ./scripts/build/runtime.sh"
    if [ -n "$PLATFORM" ]; then
        echo "   ./scripts/build/runtime.sh --platform $PLATFORM"
    fi
    exit 1
fi

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Variant: $VARIANT_LABEL"
echo "   Dockerfile: $DOCKERFILE"
echo "   Version Tag: $VERSION_TAG"
echo "   Latest Tag: $LATEST_TAG"
echo "   Git Commit: $VCS_REF"
echo "   Build Date: $BUILD_DATE"
if [ -n "$PLATFORM" ]; then
    echo "   Platform: $PLATFORM"
else
    echo "   Platform: (native)"
fi
if [ "$VARIANT" != "default" ]; then
    echo "   Base Image: ${IMAGE_NAME}:${VERSION}"
fi
echo ""

echo "🔨 Building Docker image..."
BUILD_CMD=(
    docker build
    --file "$DOCKERFILE"
    --tag "$VERSION_TAG"
    --tag "$LATEST_TAG"
    --build-arg "VERSION=$VERSION"
    --build-arg "BUILD_DATE=$BUILD_DATE"
    --build-arg "VCS_REF=$VCS_REF"
)

if [ -n "$PLATFORM" ]; then
    BUILD_CMD+=(--platform "$PLATFORM")
fi

if [ "$VARIANT" != "default" ]; then
    BUILD_CMD+=(--build-arg "BASE_IMAGE=$IMAGE_NAME" --build-arg "BASE_TAG=$VERSION")
fi

BUILD_CMD+=(.)
"${BUILD_CMD[@]}"

echo ""
echo "✅ Build Complete!"
echo ""

docker images "$IMAGE_NAME" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

echo ""
echo "📝 Docker Images Created:"
echo "   • $VERSION_TAG"
echo "   • $LATEST_TAG"
echo ""
echo "✨ Next Steps:"
echo ""
echo "1️⃣  Test locally:"
echo "   docker run --rm -v \$(pwd)/e2e/tests/1_foundation/formations/formation-base:/formation \\"
echo "              -e PORT=8000 -e HOST=0.0.0.0 -p 8000:8000 \\"
echo "              $VERSION_TAG /formation/formation.afs"
echo ""
echo "2️⃣  Convert to SIF (for MUXI Server):"
echo "   ./scripts/build/sif.sh --variant $VARIANT"
echo ""
echo "3️⃣  Build another runtime variant:"
echo "   ./scripts/build/runtime.sh --variant pytorch"
echo "   ./scripts/build/runtime.sh --variant cuda"
echo ""
echo "💡 Multi-arch builds:"
echo "   ./scripts/build/runtime.sh --platform linux/amd64 --variant $VARIANT"
echo "   ./scripts/build/runtime.sh --platform linux/arm64 --variant $VARIANT"
echo ""
