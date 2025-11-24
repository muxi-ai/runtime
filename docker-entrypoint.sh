#!/bin/bash
# MUXI Runtime - Docker Entrypoint
# This script is the entry point for the MUXI Runtime container

set -e  # Exit on error

echo "======================================"
echo "🚀 MUXI Runtime Container Starting"
echo "======================================"
echo ""

# Function to display usage
show_usage() {
    cat << EOF
MUXI Runtime Container

USAGE:
    docker run -v /path/to/formation:/formation \\
               -e OPENAI_API_KEY=your-key \\
               -p 8000:8000 \\
               muxi-runtime /formation/formation.yaml

ENVIRONMENT VARIABLES:
    OPENAI_API_KEY          OpenAI API key (if using OpenAI models)
    ANTHROPIC_API_KEY       Anthropic API key (if using Claude)
    FORMATION_PORT          Override server port (default: 8000)
    FORMATION_HOST          Override server host (default: 0.0.0.0)

REQUIRED:
    - Formation YAML path as first argument
    - Formation must be mounted as volume
    - API keys must be set via environment variables

EXAMPLES:
    # Run with OpenAI
    docker run -v ./my-formation:/formation \\
               -e OPENAI_API_KEY=sk-... \\
               -p 8000:8000 \\
               muxi-runtime /formation/formation.yaml

    # Run with custom port
    docker run -v ./my-formation:/formation \\
               -e OPENAI_API_KEY=sk-... \\
               -e FORMATION_PORT=9000 \\
               -p 9000:9000 \\
               muxi-runtime /formation/formation.yaml

EOF
}

# Check if formation path is provided
if [ -z "$1" ]; then
    echo "❌ Error: No formation path provided"
    echo ""
    show_usage
    exit 1
fi

FORMATION_PATH="$1"

# Check if formation file exists
if [ ! -f "$FORMATION_PATH" ]; then
    echo "❌ Error: Formation file not found: $FORMATION_PATH"
    echo ""
    echo "Make sure you:"
    echo "  1. Mount your formation directory as a volume"
    echo "  2. Provide the correct path to formation.yaml"
    echo ""
    echo "Example:"
    echo "  docker run -v ./my-formation:/formation \\"
    echo "             muxi-runtime /formation/formation.yaml"
    echo ""
    exit 1
fi

# Get port and host from environment or use defaults
PORT="${PORT:-${FORMATION_PORT:-8000}}"
HOST="${HOST:-${FORMATION_HOST:-127.0.0.1}}"

# Display configuration
echo "📋 Configuration:"
echo "   Formation: $FORMATION_PATH"
echo "   Host: $HOST"
echo "   Port: $PORT"
echo ""

# Check for required API keys (basic check)
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  Warning: No API keys detected"
    echo "   Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable"
    echo ""
fi

# Set up secrets if API keys are provided
mkdir -p ~/.muxi
if [ -n "$OPENAI_API_KEY" ]; then
    echo "🔐 Setting up OPENAI_API_KEY secret..."
    python -m muxi.utils.add_secret OPENAI_API_KEY "$OPENAI_API_KEY" 2>/dev/null || true
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "🔐 Setting up ANTHROPIC_API_KEY secret..."
    python -m muxi.utils.add_secret ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY" 2>/dev/null || true
fi

echo ""
echo "======================================"
echo "🎯 Starting Formation Server..."
echo "======================================"
echo ""

# Run the formation server with port and host overrides
# The formation will load secrets from ~/.muxi/secrets.enc
exec python -m muxi.utils.run_formation "$FORMATION_PATH" --port "$PORT" --host "$HOST"
