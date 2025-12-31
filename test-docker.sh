#!/bin/bash
# Test MUXI Runtime Docker image with e2e formation
# This script tests the basic Docker image with a simple foundation test

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MUXI Runtime Docker Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker is not running${NC}"
    exit 1
fi

# Check if image exists
if ! docker image inspect muxi-runtime:latest &> /dev/null; then
    echo -e "${RED}✗ Image muxi-runtime:latest not found${NC}"
    echo "Please build it first: ./build-docker.sh"
    exit 1
fi

echo -e "${GREEN}✓ Docker image found${NC}"
echo ""

# Test 1: Basic import
echo -e "${YELLOW}→${NC} Test 1: Verifying MUXI import..."
if docker run --rm muxi-runtime:latest python -c "from muxi.runtime import Formation; print('✓ Import successful')" &> /dev/null; then
    echo -e "${GREEN}✓ Test 1 passed: MUXI imports correctly${NC}"
else
    echo -e "${RED}✗ Test 1 failed: Import error${NC}"
    exit 1
fi
echo ""

# Test 2: Version check
echo -e "${YELLOW}→${NC} Test 2: Checking version..."
VERSION=$(docker run --rm muxi-runtime:latest python -c "from muxi.runtime.utils.version import get_version; print(get_version())")
echo -e "${GREEN}✓ Test 2 passed: Version ${VERSION}${NC}"
echo ""

# Test 3: Dependencies check
echo -e "${YELLOW}→${NC} Test 3: Verifying key dependencies..."
DEPS_CHECK=$(docker run --rm muxi-runtime:latest python -c "
import sys
deps = ['onellm', 'pydantic', 'fastapi', 'sqlalchemy', 'numpy', 'spacy', 'nltk']
failed = []
for dep in deps:
    try:
        __import__(dep)
    except ImportError:
        failed.append(dep)
if failed:
    print('FAILED: ' + ', '.join(failed))
    sys.exit(1)
else:
    print('ALL PRESENT')
")

if [[ "$DEPS_CHECK" == "ALL PRESENT" ]]; then
    echo -e "${GREEN}✓ Test 3 passed: All key dependencies present${NC}"
else
    echo -e "${RED}✗ Test 3 failed: Missing dependencies${NC}"
    echo "$DEPS_CHECK"
    exit 1
fi
echo ""

# Test 4: Formation validation (without running - just validate YAML)
echo -e "${YELLOW}→${NC} Test 4: Testing formation validation..."
FORMATION_PATH="/app/test_formation.afs"

# Create a minimal test formation
cat > /tmp/test_formation.afs << 'EOF'
schema: "1.0.0"
id: docker-test
description: "Docker test formation"

llm:
  api_keys:
    openai: "sk-test-key"
  models:
    - text: "openai/gpt-4o-mini"

agents:
  - id: assistant
    name: "Test Assistant"
    description: "Test agent"
    system_message: "You are a helpful assistant."
EOF

# Test loading formation (dry run)
VALIDATION_RESULT=$(docker run --rm \
    -v /tmp/test_formation.afs:${FORMATION_PATH}:ro \
    muxi-runtime:latest \
    python -c "
import yaml
import sys
try:
    with open('${FORMATION_PATH}', 'r') as f:
        config = yaml.safe_load(f)
    # Basic validation
    assert 'schema' in config, 'Missing schema'
    assert 'id' in config, 'Missing id'
    assert 'llm' in config, 'Missing llm'
    assert 'agents' in config, 'Missing agents'
    print('VALID')
except Exception as e:
    print(f'INVALID: {e}')
    sys.exit(1)
" 2>&1)

if [[ "$VALIDATION_RESULT" == "VALID" ]]; then
    echo -e "${GREEN}✓ Test 4 passed: Formation YAML is valid${NC}"
else
    echo -e "${RED}✗ Test 4 failed: Formation validation error${NC}"
    echo "$VALIDATION_RESULT"
    exit 1
fi
echo ""

# Test 5: Container filesystem
echo -e "${YELLOW}→${NC} Test 5: Checking container filesystem..."
FS_CHECK=$(docker run --rm muxi-runtime:latest bash -c "
if [ -d /data ] && [ -d /logs ] && [ -d /formations ]; then
    echo 'PRESENT'
else
    echo 'MISSING'
fi
")

if [[ "$FS_CHECK" == "PRESENT" ]]; then
    echo -e "${GREEN}✓ Test 5 passed: Required directories exist${NC}"
else
    echo -e "${RED}✗ Test 5 failed: Missing required directories${NC}"
    exit 1
fi
echo ""

# Test 6: Installed packages list
echo -e "${YELLOW}→${NC} Test 6: Checking installed package count..."
PACKAGE_COUNT=$(docker run --rm muxi-runtime:latest pip list --format=freeze | wc -l)
echo -e "${GREEN}✓ Test 6 passed: ${PACKAGE_COUNT} packages installed${NC}"
echo ""

# Cleanup
rm -f /tmp/test_formation.afs

# Summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ All tests passed!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Docker image is ready to use!"
echo ""
echo "Next steps:"
echo "  • Run with e2e formation: docker run --rm -v \$(pwd)/e2e/tests/1_foundation/formations:/formations muxi-runtime:latest"
echo "  • Start server: docker run -p 8000:8000 muxi-runtime:latest"
echo "  • Build SIF: ./sif/build-sif.sh"
echo ""
