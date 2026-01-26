#!/bin/bash
# Test script to run the formation server locally before dockerizing

set -e  # Exit on error

echo "=== Testing MUXI Runtime Server Locally ==="
echo ""

# Check if we're in the runtime directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: Must run from runtime directory"
    exit 1
fi

# Check Python version
echo "1. Checking Python version..."
python3 --version || { echo "❌ Python 3 not found"; exit 1; }
echo "✅ Python OK"
echo ""

# Check if dependencies are installed
echo "2. Checking dependencies..."
if ! python3 -c "import muxi" 2>/dev/null; then
    echo "❌ Error: MUXI package not found"
    echo "   Install with: pip3 install -e ."
    exit 1
fi
echo "✅ Dependencies OK"
echo ""

# Note: Formation secrets are handled by the formation itself
# The test formation (e2e/tests/1_foundation/formations/formation-base/)
# has its secrets configured via symlinks to e2e/assets/secrets.enc
echo "3. Note: Secrets handled by formation"
echo "   Using: e2e/tests/1_foundation/formations/formation-base/"
echo ""

# Run the server
echo "4. Starting formation server..."
echo "   Formation: e2e/tests/1_foundation/formations/formation-base/formation.afs"
echo "   Port: 8271 (configured in formation)"
echo ""
echo "   Press Ctrl+C to stop"
echo ""
echo "=========================================="
echo ""

python3 -m muxi.utils.run_formation e2e/tests/1_foundation/formations/formation-base/formation.afs
