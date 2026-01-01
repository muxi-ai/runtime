#!/bin/bash

# Run E2E tests in the all-in-one Docker container
# This script provides a simple interface to test execution in Docker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="../docker/docker-compose.all-in-one.yml"
CONTAINER_NAME="muxi-e2e-test"
IMAGE_NAME="muxi-e2e:all-in-one"

# Parse command line arguments
ACTION="test"
TEST_PATH=""
BUILD=false
INTERACTIVE=false
SHELL=false
LOGS=false
CLEAN=false

show_help() {
    echo "Usage: $0 [options] [test-path]"
    echo ""
    echo "Run E2E tests in an all-in-one Docker container"
    echo ""
    echo "Options:"
    echo "  --build         Rebuild the Docker image"
    echo "  --shell         Open interactive shell in container"
    echo "  --logs          Show service logs"
    echo "  --clean         Remove container and volumes"
    echo "  --area N        Run tests for specific area (1-12)"
    echo "  --interactive   Run tests interactively (with -s flag)"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests"
    echo "  $0 --area 1                          # Run foundation tests"
    echo "  $0 e2e/tests/2_memory            # Run memory tests"
    echo "  $0 --shell                           # Open shell in container"
    echo "  $0 --build --area 1                  # Rebuild and run area 1"
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            ;;
        --shell)
            SHELL=true
            shift
            ;;
        --logs)
            LOGS=true
            shift
            ;;
        --clean)
            CLEAN=true
            shift
            ;;
        --area)
            AREA="$2"
            shift 2
            ;;
        --interactive)
            INTERACTIVE=true
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Handle clean action
if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}Cleaning up Docker resources...${NC}"
    docker-compose -f "$COMPOSE_FILE" down -v
    docker rmi "$IMAGE_NAME" 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
    exit 0
fi

# Load environment variables
if [ -f ../e2e/.env ]; then
    echo -e "${GREEN}Loading environment from e2e/.env${NC}"
    set -a
    source ../e2e/.env
    set +a
elif [ -f ../../.env ]; then
    echo -e "${YELLOW}Using root .env file (consider creating e2e/.env)${NC}"
    set -a
    source ../../.env
    set +a
else
    echo -e "${RED}Warning: No e2e/.env or .env file found${NC}"
    echo "API keys may not be available for tests"
fi

# Check for required API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}Error: OPENAI_API_KEY not set${NC}"
    echo "Please set it in .env.e2e or export it"
    exit 1
fi

# Build image if requested or if it doesn't exist
if [ "$BUILD" = true ] || ! docker images | grep -q "$IMAGE_NAME"; then
    echo -e "${BLUE}Building Docker image...${NC}"
    docker-compose -f "$COMPOSE_FILE" build
fi

# Determine test path based on area if specified
if [ -n "$AREA" ]; then
    case $AREA in
        1) TEST_PATH="e2e/tests/1_foundation" ;;
        2) TEST_PATH="e2e/tests/2_memory" ;;
        3) TEST_PATH="e2e/tests/3_multimodal" ;;
        4) TEST_PATH="e2e/tests/4_mcp" ;;
        5) TEST_PATH="e2e/tests/5_artifacts" ;;
        6) TEST_PATH="e2e/tests/6_knowledge" ;;
        7) TEST_PATH="e2e/tests/7_orchestration" ;;
        8) TEST_PATH="e2e/tests/8_clarification" ;;
        9) TEST_PATH="e2e/tests/9_async" ;;
        10) TEST_PATH="e2e/tests/10_streaming" ;;
        11) TEST_PATH="e2e/tests/11_formatting" ;;
        12) TEST_PATH="e2e/tests/12_scheduling" ;;
        *)
            echo -e "${RED}Invalid area: $AREA${NC}"
            exit 1
            ;;
    esac
fi

# Default to all tests if no path specified
if [ -z "$TEST_PATH" ] && [ "$SHELL" = false ] && [ "$LOGS" = false ]; then
    TEST_PATH="e2e/tests"
fi

# Handle different actions
if [ "$LOGS" = true ]; then
    echo -e "${BLUE}Showing service logs...${NC}"
    docker-compose -f "$COMPOSE_FILE" up -d
    docker exec "$CONTAINER_NAME" tail -f /logs/*.log

elif [ "$SHELL" = true ]; then
    echo -e "${BLUE}Starting container with interactive shell...${NC}"
    docker-compose -f "$COMPOSE_FILE" run --rm muxi-e2e-all bash

else
    # Run tests
    echo -e "${GREEN}Starting E2E test environment...${NC}"

    # Start container
    docker-compose -f "$COMPOSE_FILE" up -d

    # Wait for services to be ready
    echo -e "${BLUE}Waiting for services to be ready...${NC}"
    sleep 10

    # Check if container is healthy
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo -e "${RED}Container failed to start${NC}"
        docker-compose -f "$COMPOSE_FILE" logs
        exit 1
    fi

    # Build pytest command
    PYTEST_CMD="pytest $TEST_PATH -v --tb=short --color=yes"

    if [ "$INTERACTIVE" = true ]; then
        PYTEST_CMD="$PYTEST_CMD -s"
    fi

    # Run tests
    echo -e "${GREEN}Running tests: $TEST_PATH${NC}"
    echo "═══════════════════════════════════════════════════════════════"

    docker exec -it "$CONTAINER_NAME" $PYTEST_CMD
    TEST_EXIT_CODE=$?

    echo "═══════════════════════════════════════════════════════════════"

    # Report results
    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo -e "\n${GREEN}✅ All tests passed!${NC}"
    else
        echo -e "\n${RED}❌ Some tests failed${NC}"
        echo -e "${YELLOW}Check logs with: $0 --logs${NC}"
    fi

    # Optionally stop container
    read -p "Stop container? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose -f "$COMPOSE_FILE" down
    else
        echo -e "${YELLOW}Container still running. Stop with: docker-compose -f $COMPOSE_FILE down${NC}"
    fi

    exit $TEST_EXIT_CODE
fi