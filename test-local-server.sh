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

# Check for OPENAI_API_KEY
echo "5. Checking for OPENAI_API_KEY..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY not set in environment"
    echo "   The formation will fail to start without it."
    echo ""
    echo "   Set it with: export OPENAI_API_KEY='your-key-here'"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✅ OPENAI_API_KEY is set"
fi
echo ""

# Check if secrets exist
echo "6. Checking secrets..."
if [ ! -f "$HOME/.muxi/secrets.enc" ]; then
    echo "⚠️  Secrets file not found at ~/.muxi/secrets.enc"
    echo "   Creating and initializing..."
    
    # Create directory
    mkdir -p "$HOME/.muxi"
    
    # Add secret (this will create the file)
    if [ -n "$OPENAI_API_KEY" ]; then
        echo "$OPENAI_API_KEY" | python -m muxi.utils.add_secret OPENAI_API_KEY
        echo "✅ Secret added"
    else
        echo "⚠️  Skipping secret initialization (no OPENAI_API_KEY)"
    fi
else
    echo "✅ Secrets file exists"
fi
echo ""

# Run the server
echo "7. Starting formation server..."
echo "   Formation: examples/test-formation.yaml"
echo "   Port: 8000 (default)"
echo ""
echo "   Press Ctrl+C to stop"
echo ""
echo "=========================================="
echo ""

python -m muxi.utils.run_formation examples/test-formation.yaml
