#!/bin/bash
# Run E2E tests in Docker with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TEST_PATH=""
PARALLEL=false
VERBOSE=false
COVERAGE=false
TIMEOUT=300
WORKERS=4
AREA=""
PATTERN=""
REBUILD=false
INTERACTIVE=false

# Function to print usage
usage() {
    echo "Usage: $0 [OPTIONS] [TEST_PATH]"
    echo ""
    echo "Run MUXI E2E tests in Docker container"
    echo ""
    echo "Options:"
    echo "  -a, --area NUM       Run tests for specific area (1-12)"
    echo "  -p, --parallel       Run tests in parallel"
    echo "  -v, --verbose        Verbose output"
    echo "  -c, --coverage       Generate coverage report"
    echo "  -t, --timeout SEC    Test timeout in seconds (default: 300)"
    echo "  -w, --workers NUM    Number of parallel workers (default: 4)"
    echo "  -k, --pattern PAT    Run tests matching pattern"
    echo "  -r, --rebuild        Rebuild Docker image before running"
    echo "  -i, --interactive    Drop into bash after tests"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Test Areas:"
    echo "  1 - Foundation (formation loading, basic chat)"
    echo "  2 - Memory (buffer, persistent, vector)"
    echo "  3 - Multimodal (images, audio, documents)"
    echo "  4 - MCP (Model Context Protocol tools)"
    echo "  5 - Artifacts (file generation)"
    echo "  6 - Knowledge (knowledge base)"
    echo "  7 - Orchestration (multi-agent)"
    echo "  8 - Clarification (parameter collection)"
    echo "  9 - Async (async operations)"
    echo "  10 - Streaming (response streaming)"
    echo "  11 - Formatting (output formatting)"
    echo "  12 - Scheduling (task scheduling)"
    echo ""
    echo "Examples:"
    echo "  $0                           # Run all tests"
    echo "  $0 -a 1                      # Run foundation tests"
    echo "  $0 -p -w 8                   # Run all tests in parallel with 8 workers"
    echo "  $0 -k test_memory -v         # Run tests matching 'test_memory' verbosely"
    echo "  $0 e2e/tests/1_foundation    # Run specific test directory"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--area)
            AREA="$2"
            shift 2
            ;;
        -p|--parallel)
            PARALLEL=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -w|--workers)
            WORKERS="$2"
            shift 2
            ;;
        -k|--pattern)
            PATTERN="$2"
            shift 2
            ;;
        -r|--rebuild)
            REBUILD=true
            shift
            ;;
        -i|--interactive)
            INTERACTIVE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            TEST_PATH="$1"
            shift
            ;;
    esac
done

# Navigate to runtime directory
cd "$(dirname "$0")/../.."

# Map area number to test path
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
            echo -e "${RED}Invalid area number: $AREA${NC}"
            exit 1
            ;;
    esac
fi

# Default to all tests if no path specified
TEST_PATH=${TEST_PATH:-"e2e/tests"}

# Load environment variables
if [ -f .env ]; then
    echo -e "${YELLOW}Loading environment from .env${NC}"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check for required API keys
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}Error: No API keys found!${NC}"
    echo "Please set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env file"
    exit 1
fi

# Rebuild image if requested
if [ "$REBUILD" = true ]; then
    echo -e "${GREEN}Rebuilding Docker image...${NC}"
    ./e2e/scripts/docker-build.sh --build-only
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to rebuild Docker image${NC}"
        exit 1
    fi
fi

# Check if image exists
if ! docker image inspect muxi-e2e:latest >/dev/null 2>&1; then
    echo -e "${YELLOW}Docker image not found. Building...${NC}"
    ./e2e/scripts/docker-build.sh --build-only
fi

# Build pytest command
PYTEST_CMD="pytest $TEST_PATH"

# Add pytest options
if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -vv"
else
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$PARALLEL" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -n $WORKERS"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=muxi.runtime --cov-report=term-missing --cov-report=html"
fi

if [ -n "$PATTERN" ]; then
    PYTEST_CMD="$PYTEST_CMD -k '$PATTERN'"
fi

PYTEST_CMD="$PYTEST_CMD --timeout=$TIMEOUT --tb=short"

# Print test configuration
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}E2E Test Configuration:${NC}"
echo -e "  Test Path: ${GREEN}$TEST_PATH${NC}"
echo -e "  Parallel: $PARALLEL (Workers: $WORKERS)"
echo -e "  Verbose: $VERBOSE"
echo -e "  Coverage: $COVERAGE"
echo -e "  Timeout: ${TIMEOUT}s"
if [ -n "$PATTERN" ]; then
    echo -e "  Pattern: $PATTERN"
fi
echo -e "${BLUE}========================================${NC}"

# Stop and remove existing container
echo -e "${YELLOW}Cleaning up existing container...${NC}"
docker stop muxi-e2e-test 2>/dev/null || true
docker rm muxi-e2e-test 2>/dev/null || true

# Run tests
echo -e "${GREEN}Running tests...${NC}"
echo -e "${YELLOW}Command: $PYTEST_CMD${NC}"

# Create results directory
mkdir -p e2e/results
mkdir -p e2e/logs

# Run with docker-compose
docker-compose -f e2e/docker/docker-compose.yml \
    run --rm \
    -e PYTEST_TIMEOUT=$TIMEOUT \
    -e TEST_PARALLEL_WORKERS=$WORKERS \
    muxi-e2e \
    bash -c "$PYTEST_CMD"

TEST_EXIT_CODE=$?

# Drop into interactive shell if requested
if [ "$INTERACTIVE" = true ]; then
    echo -e "${YELLOW}Dropping into interactive shell...${NC}"
    docker-compose -f e2e/docker/docker-compose.yml \
        run --rm muxi-e2e bash
fi

# Print results summary
echo -e "${BLUE}========================================${NC}"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed (exit code: $TEST_EXIT_CODE)${NC}"
fi
echo -e "${BLUE}========================================${NC}"

# Print log locations
echo -e "${YELLOW}Logs available at:${NC}"
echo "  - Test results: e2e/results/"
echo "  - Service logs: e2e/logs/"
if [ "$COVERAGE" = true ]; then
    echo "  - Coverage report: htmlcov/index.html"
fi

exit $TEST_EXIT_CODE