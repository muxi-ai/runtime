#!/usr/bin/env bash
#
# MUXI Runtime Docker Builder
# Builds Docker images for MUXI formations
#
# Usage:
#   ./build-docker.sh [basic|production] [options]
#
# Examples:
#   ./build-docker.sh                    # Build basic runtime
#   ./build-docker.sh basic              # Build basic runtime
#   ./build-docker.sh production         # Build production with services
#   ./build-docker.sh basic --no-cache   # Rebuild from scratch
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BUILD_TYPE="${1:-basic}"
EXTRA_ARGS="${@:2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker not found!"
        echo ""
        echo "Please install Docker:"
        echo "  macOS: brew install --cask docker"
        echo "  Linux: curl -fsSL https://get.docker.com | sh"
        echo "  Windows: https://docs.docker.com/desktop/windows/install/"
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running!"
        echo ""
        echo "Please start Docker Desktop or the Docker daemon"
        exit 1
    fi
    
    print_success "Docker is ready: $(docker --version | head -n1)"
}

# Build Docker image
build_docker() {
    local build_type="$1"
    local extra_args="$2"
    
    # Determine Dockerfile and image tag
    local dockerfile
    local image_tag
    
    case "$build_type" in
        basic)
            dockerfile="Dockerfile"
            image_tag="muxi-runtime:latest"
            ;;
        production|prod)
            dockerfile="Dockerfile.production"
            image_tag="muxi-runtime:production"
            build_type="production"
            ;;
        *)
            print_error "Unknown build type: $build_type"
            echo "Valid types: basic, production"
            exit 1
            ;;
    esac
    
    print_header "MUXI Runtime Docker Builder"
    echo ""
    print_info "Build Type: $build_type"
    print_info "Dockerfile: $dockerfile"
    print_info "Image Tag: $image_tag"
    echo ""
    
    # Check if Dockerfile exists
    if [[ ! -f "$SCRIPT_DIR/$dockerfile" ]]; then
        print_error "Dockerfile not found: $dockerfile"
        exit 1
    fi
    
    # Build the image
    print_info "Building Docker image..."
    echo ""
    
    docker build \
        -f "$SCRIPT_DIR/$dockerfile" \
        -t "$image_tag" \
        $extra_args \
        "$SCRIPT_DIR"
    
    # Verify build
    if docker image inspect "$image_tag" &> /dev/null; then
        echo ""
        print_success "Build complete!"
        echo ""
        print_header "Image Information"
        docker images "$image_tag" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        echo ""
        
        # Show next steps
        print_header "Next Steps"
        echo ""
        echo "1. Test the image:"
        echo "   docker run --rm -it $image_tag python -c 'import muxi; print(muxi.__version__)'"
        echo ""
        echo "2. Run a formation (basic):"
        if [[ "$build_type" == "basic" ]]; then
            echo "   docker run --rm -p 8000:8000 \\"
            echo "     -v \$(pwd)/examples:/formations \\"
            echo "     -e OPENAI_API_KEY=sk-your-key \\"
            echo "     $image_tag \\"
            echo "     python -m muxi.server run --formation /formations/test-formation.yaml"
        else
            echo "   docker run --rm -p 8000:8000 -p 5432:5432 \\"
            echo "     -v \$(pwd)/examples:/formations \\"
            echo "     -e OPENAI_API_KEY=sk-your-key \\"
            echo "     $image_tag"
        fi
        echo ""
        echo "3. Or use docker-compose:"
        echo "   docker-compose up muxi-runtime      # Basic"
        echo "   docker-compose up muxi-production   # Production"
        echo ""
        echo "4. Build SIF from this image:"
        echo "   ./build-sif.sh $build_type"
        echo ""
        print_success "All done! 🚀"
    else
        print_error "Build failed - image not created"
        exit 1
    fi
}

# Show usage
show_usage() {
    cat << EOF
MUXI Runtime Docker Builder

Usage:
  $0 [TYPE] [OPTIONS]

Build Types:
  basic       - Basic runtime (~2GB)
  production  - Production with services (~3GB)

Options:
  --no-cache      Rebuild from scratch
  --pull          Always pull latest base image
  --quiet         Suppress build output
  -h, --help      Show this help message

Examples:
  $0                              # Build basic runtime
  $0 basic                        # Build basic runtime
  $0 production                   # Build production runtime
  $0 basic --no-cache             # Rebuild from scratch
  $0 production --pull            # Pull latest base image

After Building:
  • Test: docker run --rm $image_tag python -c 'import muxi'
  • Use: docker-compose up
  • SIF: ./build-sif.sh

For more information, see DOCKER-GUIDE.md (coming soon)

EOF
}

# Parse arguments
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    show_usage
    exit 0
fi

# Change to script directory
cd "$SCRIPT_DIR"

# Check prerequisites
check_docker

# Run build
build_docker "$BUILD_TYPE" "$EXTRA_ARGS"
