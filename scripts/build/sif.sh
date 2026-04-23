#!/bin/bash
# Convert MUXI Runtime Docker images to Singularity/Apptainer SIF artifacts.
# Supports runtime variants (default, pytorch, cuda) and specific architectures.

set -euo pipefail

show_usage() {
    cat <<'EOF'
Usage: ./scripts/build/sif.sh [--arch amd64|arm64] [--variant default|pytorch|cuda]

Examples:
  ./scripts/build/sif.sh
  ./scripts/build/sif.sh --arch amd64
  ./scripts/build/sif.sh --variant pytorch
  ./scripts/build/sif.sh --arch amd64 --variant cuda
EOF
}

echo "======================================"
echo "Converting Docker to Singularity SIF"
echo "======================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ARCH=""
VARIANT="default"

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
        TAG_SUFFIX=""
        FILE_SUFFIX=""
        VARIANT_LABEL="default"
        ;;
    pytorch)
        TAG_SUFFIX="-pytorch"
        FILE_SUFFIX="-pytorch"
        VARIANT_LABEL="pytorch"
        ;;
    cuda)
        TAG_SUFFIX="-cuda"
        FILE_SUFFIX="-cuda"
        VARIANT_LABEL="cuda"
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
IMAGE_TAG="${IMAGE_NAME}:${VERSION}${TAG_SUFFIX}"

if [ -z "$ARCH" ]; then
    ARCH=$(docker image inspect "$IMAGE_TAG" --format '{{.Architecture}}' 2>/dev/null || echo "")
    if [ -z "$ARCH" ]; then
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

SIF_DIR="sif-builds"
TARBALL="muxi-runtime-${VERSION}${FILE_SUFFIX}.tar"
SIF_FILE="$SIF_DIR/muxi-runtime-${VERSION}${FILE_SUFFIX}-linux-${ARCH}.sif"
LATEST_SIF_FILE="$SIF_DIR/muxi-runtime-latest${FILE_SUFFIX}-linux-${ARCH}.sif"

mkdir -p "$SIF_DIR"

echo "📦 Configuration:"
echo "   Version: $VERSION"
echo "   Variant: $VARIANT_LABEL"
echo "   Architecture: $ARCH"
echo "   Docker Image: $IMAGE_TAG"
echo "   Tarball: $TARBALL"
echo "   SIF File: $SIF_FILE"
echo ""

if [ "$VARIANT" != "default" ]; then
    echo "ℹ️  Note: non-default variant token/file resolution on muxi-server is still"
    echo "    being coordinated; local artifacts use a '${FILE_SUFFIX}' filename"
    echo "    suffix so default/pytorch/cuda builds do not collide."
    echo ""
fi

if ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    echo "❌ Error: Docker image $IMAGE_TAG not found"
    echo ""
    echo "Build it first:"
    echo "   ./scripts/build/runtime.sh --variant $VARIANT"
    echo "   ./scripts/build/runtime.sh --platform linux/amd64 --variant $VARIANT"
    echo "   ./scripts/build/runtime.sh --platform linux/arm64 --variant $VARIANT"
    exit 1
fi

echo "💾 Exporting Docker image to tarball..."
# Register cleanup before docker save so a partial tarball from a mid-write
# failure (e.g. ENOSPC on an ~830 MB pytorch image) is also removed.
trap 'rm -f "$TARBALL"' EXIT
docker save "$IMAGE_TAG" -o "$TARBALL"
echo "   ✓ Created $TARBALL"
echo ""

echo "🔄 Converting to Singularity SIF..."
if command -v apptainer >/dev/null 2>&1; then
    echo "   Using native Apptainer..."
    apptainer build "$SIF_FILE" "docker-archive://$TARBALL"
elif command -v singularity >/dev/null 2>&1; then
    echo "   Using native Singularity..."
    singularity build "$SIF_FILE" "docker-archive://$TARBALL"
else
    # runtime-runner is published linux/amd64 only, and this is intentional:
    # Apptainer/Singularity upstream ships x86_64 Linux binaries only, so any
    # image that embeds singularity has to be amd64. That in turn means the
    # SIF loaded by that singularity must also be amd64. The arm64 SIF path
    # is real but only matters when you have a native arm64 Linux host with
    # a self-built arm64 apptainer (e.g., AWS Graviton). On macOS and Windows,
    # the correct SIF arch is always linux-amd64, regardless of host CPU —
    # Rosetta (Apple Silicon) or Hyper-V handles the translation.
    echo "   Apptainer/Singularity not found locally, using Docker-wrapped runtime-runner..."
    if [ "$ARCH" = "arm64" ]; then
        echo ""
        echo "   ⚠️  Building a linux-arm64 SIF."
        echo "       This is the right choice ONLY on a native arm64 Linux host running"
        echo "       a matching arm64 apptainer (e.g., AWS Graviton). On macOS/Windows"
        echo "       the SIF is loaded by an amd64 Singularity process inside Docker,"
        echo "       so the SIF must be linux-amd64 there. Rebuild with --arch amd64"
        echo "       if you're testing on a Mac or Windows box."
        echo ""
    fi
    docker run --rm --privileged \
        -v "$(pwd):/work" \
        -w /work \
        ghcr.io/muxi-ai/runtime-runner:latest \
        build "$SIF_FILE" "docker-archive://$TARBALL"
fi

echo "   ✓ Created $SIF_FILE"

cp "$SIF_FILE" "$LATEST_SIF_FILE"
echo "   ✓ Created $LATEST_SIF_FILE (for server fallback)"
echo ""

echo "📊 File Information:"
echo "   Tarball: $(du -h "$TARBALL" | cut -f1)"
echo "   SIF: $(du -h "$SIF_FILE" | cut -f1)"
echo ""

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
echo "✨ Test the SIF:"
echo ""
echo "   Required mounts (SIF rootfs is read-only by design):"
echo "     --writable-tmpfs                      # scratch fs for runtime state (~/.muxi)"
echo "     --bind <formation-dir>:/formation     # the formation to boot"
echo ""
echo "   Option A — native apptainer (Linux host with matching arch):"
echo ""
echo "       apptainer exec --writable-tmpfs \\"
echo "           --bind <formation-dir>:/formation \\"
echo "           $SIF_FILE \\"
echo "           python -m muxi.runtime.utils.run_formation \\"
echo "               /formation/formation.yaml --host 0.0.0.0 --port 8000"
echo ""
echo "   Option B — docker-wrapped apptainer (no native apptainer; host arch MUST match SIF arch):"
echo ""
echo "       docker run --rm --privileged \\"
echo "           -v \$(pwd)/$SIF_FILE:/sif/runtime.sif:ro \\"
echo "           -v <formation-dir>:/formation:ro \\"
echo "           -p 8000:8000 \\"
echo "           ghcr.io/muxi-ai/runtime-runner:latest \\"
echo "           exec --writable-tmpfs \\"
echo "               --bind /formation:/formation \\"
echo "               /sif/runtime.sif \\"
echo "               python -m muxi.runtime.utils.run_formation \\"
echo "                   /formation/formation.yaml --host 0.0.0.0 --port 8000"
echo ""
echo "       NOTE: runtime-runner is currently amd64-only. On an arm64 host with an"
echo "       arm64 SIF, build a local helper image from ubuntu:22.04 + ppa:apptainer/ppa."
echo ""
echo "   Health check (both options):"
echo "       curl -fsS http://127.0.0.1:8000/v1/health"
echo ""
echo "💡 Build for specific architecture:"
echo "   ./scripts/build/runtime.sh --platform linux/arm64 --variant $VARIANT && ./scripts/build/sif.sh --arch arm64 --variant $VARIANT"
echo "   ./scripts/build/runtime.sh --platform linux/amd64 --variant $VARIANT && ./scripts/build/sif.sh --arch amd64 --variant $VARIANT"
echo ""
