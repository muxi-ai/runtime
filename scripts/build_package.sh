#!/bin/bash
# Build PyPI distribution packages for MUXI Runtime
# This creates both wheel (.whl) and source distribution (.tar.gz)

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "======================================"
echo "MUXI Runtime - PyPI Package Builder"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}ERROR: pyproject.toml not found!${NC}"
    echo "Please run this script from the runtime directory."
    exit 1
fi

# Check if version file exists
VERSION_FILE="src/muxi/.version"
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}ERROR: Version file not found: $VERSION_FILE${NC}"
    exit 1
fi

VERSION=$(cat "$VERSION_FILE")
echo -e "${BLUE}Building version:${NC} ${GREEN}$VERSION${NC}"
echo ""

# Clean previous builds
echo -e "${YELLOW}→${NC} Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info src/*.egg-info
echo -e "${GREEN}✓${NC} Cleaned build artifacts"
echo ""

# Check if build tools are installed
echo -e "${YELLOW}→${NC} Checking build dependencies..."
if ! python3 -m pip show build &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  'build' package not found, installing..."
    python3 -m pip install build
fi

if ! python3 -m pip show twine &> /dev/null; then
    echo -e "${YELLOW}⚠${NC}  'twine' package not found, installing..."
    python3 -m pip install twine
fi
echo -e "${GREEN}✓${NC} Build dependencies ready"
echo ""

# Build the package
echo -e "${YELLOW}→${NC} Building distribution packages..."
python3 -m build

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Build completed successfully!"
    echo ""
    
    # List the created files
    echo -e "${BLUE}Generated packages:${NC}"
    ls -lh dist/
    echo ""
    
    # Verify the package
    echo -e "${YELLOW}→${NC} Verifying package integrity..."
    python3 -m twine check dist/*
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Package verification passed!"
        echo ""
        echo "======================================"
        echo -e "${GREEN}BUILD SUCCESSFUL${NC}"
        echo "======================================"
        echo ""
        echo "Distribution files ready in: ${BLUE}dist/${NC}"
        echo ""
        echo "Next steps:"
        echo "  • Test locally:  ${BLUE}pip install dist/muxi-${VERSION}-py3-none-any.whl${NC}"
        echo "  • Test on PyPI:  ${BLUE}./scripts/publish_package.sh --test${NC}"
        echo "  • Publish:       ${BLUE}./scripts/publish_package.sh${NC}"
        echo ""
    else
        echo -e "${RED}✗${NC} Package verification failed!"
        exit 1
    fi
else
    echo -e "${RED}✗${NC} Build failed!"
    exit 1
fi
