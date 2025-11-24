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

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "2. Creating virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "2. Virtual environment exists"
fi
echo ""

# Activate virtual environment
echo "3. Activating virtual environment..."
source .venv/bin/activate
echo "✅ Activated"
echo ""

# Install dependencies if needed
echo "4. Checking dependencies..."
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -e . > /dev/null 2>&1
    echo "✅ Dependencies installed"
else
    echo "✅ Dependencies OK"
fi
echo ""

# Note: Formation secrets are handled by the formation itself
# The test formation (e2e/tests/1_foundation/formations/formation-base/)
# has its secrets configured via symlinks to e2e/assets/secrets.enc
echo "5. Note: Secrets handled by formation"
echo "   Using: e2e/tests/1_foundation/formations/formation-base/"
echo ""

# The test formation should have its own secrets configured
# We just check that the formation exists
echo "6. Checking test formation..."
if [ ! -f "examples/test-formation.yaml" ]; then
    echo "❌ Error: examples/test-formation.yaml not found"
    exit 1
fi
echo "✅ Test formation exists"
echo ""

# Run the server
echo "7. Starting formation server..."
echo "   Formation: e2e/tests/1_foundation/formations/formation-base/formation.yaml"
echo "   Port: 8271 (configured in formation)"
echo ""
echo "   Press Ctrl+C to stop"
echo ""
echo "=========================================="
echo ""

python -m muxi.utils.run_formation e2e/tests/1_foundation/formations/formation-base/formation.yaml
