#!/bin/bash

# E2E Test Runner Script for MUXI Runtime
# This script sets up required services and runs E2E tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.e2e.yml"
ENV_FILE=".env.e2e"
TEST_DIR="e2e/tests"
WAIT_TIMEOUT=60

# Parse command line arguments
AREA=""
SPECIFIC_TEST=""
SKIP_SERVICES=false
CLEANUP=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --area)
            AREA="$2"
            shift 2
            ;;
        --test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        --skip-services)
            SKIP_SERVICES=true
            shift
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --area AREA          Run tests for specific area (1-12)"
            echo "  --test TEST_FILE     Run specific test file"
            echo "  --skip-services      Skip starting Docker services"
            echo "  --no-cleanup         Don't stop services after tests"
            echo "  --help              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to wait for service
wait_for_service() {
    local service=$1
    local url=$2
    local timeout=${3:-$WAIT_TIMEOUT}

    echo -n "Waiting for $service..."

    for i in $(seq 1 $timeout); do
        if curl -f -s "$url" > /dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        sleep 1
        echo -n "."
    done

    echo -e " ${RED}✗${NC}"
    echo "Service $service failed to start within $timeout seconds"
    return 1
}

# Function to cleanup services
cleanup_services() {
    if [ "$CLEANUP" = true ] && [ "$SKIP_SERVICES" = false ]; then
        echo -e "\n${YELLOW}Stopping services...${NC}"
        docker-compose -f "$COMPOSE_FILE" down
    fi
}

# Set trap for cleanup
trap cleanup_services EXIT

# Check for required files
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Warning: $ENV_FILE not found${NC}"
    echo "Creating from example..."
    if [ -f ".env.e2e.example" ]; then
        cp .env.e2e.example "$ENV_FILE"
        echo -e "${YELLOW}Please edit $ENV_FILE with your actual API keys${NC}"
        exit 1
    else
        echo -e "${RED}Error: .env.e2e.example not found${NC}"
        exit 1
    fi
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Start services if not skipped
if [ "$SKIP_SERVICES" = false ]; then
    echo -e "${GREEN}Starting test services...${NC}"
    docker-compose -f "$COMPOSE_FILE" up -d

    # Wait for services to be healthy
    echo -e "\n${GREEN}Waiting for services to be ready...${NC}"

    wait_for_service "PostgreSQL" "http://localhost:5432" || exit 1
    wait_for_service "FAISSx (no auth)" "http://localhost:45678/health" || exit 1
    wait_for_service "FAISSx (with auth)" "http://localhost:65432/health" || exit 1
    wait_for_service "Webhook" "http://localhost:8080" || exit 1
    wait_for_service "A2A Registry" "http://localhost:8090/health" || exit 1

    echo -e "${GREEN}All services are ready!${NC}\n"
fi

# Determine which tests to run
if [ -n "$SPECIFIC_TEST" ]; then
    TEST_PATH="$SPECIFIC_TEST"
    echo -e "${GREEN}Running specific test: $TEST_PATH${NC}"
elif [ -n "$AREA" ]; then
    # Map area number to directory name
    case $AREA in
        1) TEST_PATH="$TEST_DIR/1_foundation" ;;
        2) TEST_PATH="$TEST_DIR/2_memory" ;;
        3) TEST_PATH="$TEST_DIR/3_multimodal" ;;
        4) TEST_PATH="$TEST_DIR/4_mcp" ;;
        5) TEST_PATH="$TEST_DIR/5_artifacts" ;;
        6) TEST_PATH="$TEST_DIR/6_knowledge" ;;
        7) TEST_PATH="$TEST_DIR/7_orchestration" ;;
        8) TEST_PATH="$TEST_DIR/8_clarification" ;;
        9) TEST_PATH="$TEST_DIR/9_async" ;;
        10) TEST_PATH="$TEST_DIR/10_streaming" ;;
        11) TEST_PATH="$TEST_DIR/11_formatting" ;;
        12) TEST_PATH="$TEST_DIR/12_scheduling" ;;
        *)
            echo -e "${RED}Invalid area: $AREA${NC}"
            exit 1
            ;;
    esac
    echo -e "${GREEN}Running tests for Area $AREA${NC}"
else
    TEST_PATH="$TEST_DIR"
    echo -e "${GREEN}Running all E2E tests${NC}"
fi

# Run tests
echo -e "\n${GREEN}Starting test execution...${NC}"
echo "═══════════════════════════════════════════════════════════════"

# Use pytest with nice output
pytest "$TEST_PATH" \
    -v \
    --tb=short \
    --color=yes \
    --durations=10 \
    --capture=no \
    -p no:warnings

TEST_EXIT_CODE=$?

echo "═══════════════════════════════════════════════════════════════"

# Report results
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
else
    echo -e "\n${RED}❌ Some tests failed${NC}"
fi

exit $TEST_EXIT_CODE
