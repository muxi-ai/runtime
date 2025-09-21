#!/bin/bash
# Build and optionally run the E2E all-in-one Docker image

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Building MUXI E2E All-in-One Docker Image${NC}"
echo "=========================================="

# Parse arguments
BUILD_ONLY=false
NO_CACHE=false
RUN_TESTS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --run)
            RUN_TESTS="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --build-only     Only build the image, don't run it"
            echo "  --no-cache       Build without cache"
            echo "  --run <path>     Run specific tests after build"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Navigate to runtime directory
cd "$(dirname "$0")/../.."

# Load environment variables if .env exists
if [ -f .env ]; then
    echo -e "${YELLOW}Loading environment variables from .env${NC}"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Build arguments
BUILD_ARGS=""
if [ "$NO_CACHE" = true ]; then
    BUILD_ARGS="--no-cache"
fi

# Build the image
echo -e "${GREEN}Building Docker image...${NC}"
docker build $BUILD_ARGS \
    -f e2e/docker/Dockerfile.e2e-all-in-one \
    -t muxi-e2e:all-in-one \
    -t muxi-e2e:latest \
    .

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker build failed!${NC}"
    exit 1
fi

echo -e "${GREEN}Docker image built successfully!${NC}"

# Run container if not build-only
if [ "$BUILD_ONLY" = false ]; then
    echo -e "${GREEN}Starting container...${NC}"

    # Stop and remove existing container if it exists
    docker stop muxi-e2e-test 2>/dev/null || true
    docker rm muxi-e2e-test 2>/dev/null || true

    # Run with docker-compose for proper volume mounts
    if [ -n "$RUN_TESTS" ]; then
        echo -e "${YELLOW}Running tests: $RUN_TESTS${NC}"
        docker-compose -f e2e/docker/docker-compose.all-in-one.yml \
            run --rm muxi-e2e-all \
            pytest "e2e/tests/$RUN_TESTS" -v
    else
        echo -e "${YELLOW}Starting interactive container...${NC}"
        docker-compose -f e2e/docker/docker-compose.all-in-one.yml \
            run --rm muxi-e2e-all bash
    fi
fi

echo -e "${GREEN}Done!${NC}"