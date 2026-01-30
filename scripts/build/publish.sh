#!/bin/bash
# Publish MUXI Runtime to PyPI
# Supports both TestPyPI and production PyPI

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "======================================"
echo "MUXI Runtime - PyPI Publisher"
echo "======================================"
echo ""

# Parse arguments
TEST_MODE=false
if [ "$1" == "--test" ] || [ "$1" == "-t" ]; then
    TEST_MODE=true
fi

# Check if dist/ exists
if [ ! -d "dist" ]; then
    echo -e "${RED}ERROR: dist/ directory not found!${NC}"
    echo "Please run ./scripts/build_package.sh first"
    exit 1
fi

# Check if there are files to upload
if [ -z "$(ls -A dist/)" ]; then
    echo -e "${RED}ERROR: No files found in dist/!${NC}"
    echo "Please run ./scripts/build_package.sh first"
    exit 1
fi

# Get version
VERSION_FILE="src/muxi/.version"
VERSION=$(cat "$VERSION_FILE")

# Check if twine is installed
if ! python3 -m pip show twine &> /dev/null; then
    echo -e "${YELLOW}→${NC} Installing twine..."
    python3 -m pip install twine
fi

# Display what will be uploaded
echo -e "${BLUE}Package version:${NC} ${GREEN}$VERSION${NC}"
echo ""
echo -e "${BLUE}Files to upload:${NC}"
ls -lh dist/
echo ""

if [ "$TEST_MODE" = true ]; then
    # TestPyPI upload
    echo -e "${YELLOW}⚠ TEST MODE: Publishing to TestPyPI${NC}"
    echo ""
    echo "Note: You'll need TestPyPI credentials"
    echo "Create an account at: https://test.pypi.org/account/register/"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to cancel..."
    echo ""
    
    echo -e "${YELLOW}→${NC} Uploading to TestPyPI..."
    python3 -m twine upload --repository testpypi dist/*
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "======================================"
        echo -e "${GREEN}UPLOAD TO TESTPYPI SUCCESSFUL${NC}"
        echo "======================================"
        echo ""
        echo "View at: ${BLUE}https://test.pypi.org/project/muxi/${VERSION}/${NC}"
        echo ""
        echo "Test installation:"
        echo "  ${BLUE}pip install --index-url https://test.pypi.org/simple/ muxi${NC}"
        echo ""
    else
        echo -e "${RED}✗${NC} Upload to TestPyPI failed!"
        exit 1
    fi
else
    # Production PyPI upload
    echo -e "${RED}⚠ PRODUCTION MODE: Publishing to PyPI${NC}"
    echo ""
    echo "This will publish version ${GREEN}$VERSION${NC} to PyPI."
    echo "This action CANNOT be undone!"
    echo ""
    echo "Note: You'll need PyPI credentials"
    echo "Create an API token at: https://pypi.org/manage/account/token/"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "Upload cancelled."
        exit 0
    fi
    
    echo ""
    echo -e "${YELLOW}→${NC} Uploading to PyPI..."
    python3 -m twine upload dist/*
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "======================================"
        echo -e "${GREEN}PUBLISH TO PYPI SUCCESSFUL${NC}"
        echo "======================================"
        echo ""
        echo "View at: ${BLUE}https://pypi.org/project/muxi/${VERSION}/${NC}"
        echo ""
        echo "Installation command:"
        echo "  ${BLUE}pip install muxi${NC}"
        echo ""
        echo "Don't forget to:"
        echo "  • Create a GitHub release: ${BLUE}https://github.com/muxi-ai/runtime/releases/new${NC}"
        echo "  • Tag the commit: ${BLUE}git tag v${VERSION} && git push --tags${NC}"
        echo "  • Update documentation"
        echo "  • Announce on social media"
        echo ""
    else
        echo -e "${RED}✗${NC} Upload to PyPI failed!"
        exit 1
    fi
fi
