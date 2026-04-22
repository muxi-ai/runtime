#!/bin/bash
# MUXI Runtime - Docker Entrypoint
# This script is the entry point for the MUXI Runtime container

set -e  # Exit on error

# In SIF (Singularity / Apptainer) mode the runtime is sealed off from the
# network. Model weights live on the HOST at ~/.muxi/server/cache and are
# bind-mounted in at /opt/hf-cache by muxi-server. The SIF itself ships no
# weights (see Dockerfile R3) — an empty /opt/hf-cache therefore guarantees
# a runtime failure at the first embedding call. We fail fast here with an
# actionable error instead of surfacing a confusing "model not found" from
# inside the application later.
if [ -n "$APPTAINER_CONTAINER" ] || [ -n "$SINGULARITY_CONTAINER" ] || [ "$MUXI_SIF_MODE" = "1" ]; then
    export HF_HUB_OFFLINE=1
    export TRANSFORMERS_OFFLINE=1

    # Apptainer sets LD_LIBRARY_PATH to only /.singularity.d/libs, which hides
    # system libraries installed via apt-get in the Docker image (e.g. libpoppler,
    # libtesseract). Append the standard system paths so they remain discoverable.
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:/usr/lib:/usr/lib64:/usr/local/lib:/usr/lib/x86_64-linux-gnu:/usr/lib/aarch64-linux-gnu"

    # Cache assertion: at least one ``models--*`` directory must be present.
    # Using ``find`` rather than shell globbing keeps the check portable and
    # avoids nullglob / literal-glob pitfalls.
    model_count=$(find /opt/hf-cache -maxdepth 1 -name 'models--*' -type d 2>/dev/null | wc -l)
    if [ "$model_count" -eq 0 ]; then
        echo "======================================" >&2
        echo "ERROR: HuggingFace cache is empty" >&2
        echo "======================================" >&2
        echo "" >&2
        echo "The SIF runtime runs offline (HF_HUB_OFFLINE=1) and ships no" >&2
        echo "embedding model weights. /opt/hf-cache must be populated by the" >&2
        echo "host at launch time via bind-mount." >&2
        echo "" >&2
        echo "Expected: at least one models--* directory under /opt/hf-cache." >&2
        echo "" >&2
        echo "If launched via muxi-server, this indicates the host cache at" >&2
        echo "~/.muxi/server/cache is empty. Populate it with:" >&2
        echo "" >&2
        echo "  HF_HUB_CACHE=~/.muxi/server/cache \\" >&2
        echo "    HF_HOME=~/.muxi/server/cache \\" >&2
        echo "    onellm download local/nomic-ai/nomic-embed-text-v1.5" >&2
        echo "" >&2
        echo "For ad-hoc apptainer runs, bind-mount the host cache yourself:" >&2
        echo "" >&2
        echo "  apptainer run \\" >&2
        echo "    --bind \${HOME}/.muxi/server/cache:/opt/hf-cache \\" >&2
        echo "    <sif-path> <formation-path>" >&2
        echo "" >&2
        exit 1
    fi
fi

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
               muxi-runtime /formation/formation.afs

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
               muxi-runtime /formation/formation.afs

    # Run with custom port
    docker run -v ./my-formation:/formation \\
               -e OPENAI_API_KEY=sk-... \\
               -e FORMATION_PORT=9000 \\
               -p 9000:9000 \\
               muxi-runtime /formation/formation.afs

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
shift  # Remove formation path from args

# Parse remaining arguments (--port, --host)
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            CLI_PORT="$2"
            shift 2
            ;;
        --host)
            CLI_HOST="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Check if formation file exists
if [ ! -f "$FORMATION_PATH" ]; then
    echo "❌ Error: Formation file not found: $FORMATION_PATH"
    echo ""
    echo "Make sure you:"
    echo "  1. Mount your formation directory as a volume"
    echo "  2. Provide the correct path to formation.afs"
    echo ""
    echo "Example:"
    echo "  docker run -v ./my-formation:/formation \\"
    echo "             muxi-runtime /formation/formation.afs"
    echo ""
    exit 1
fi

# Priority: CLI args > environment vars > defaults
PORT="${CLI_PORT:-${PORT:-${FORMATION_PORT:-8000}}}"
HOST="${CLI_HOST:-${HOST:-${FORMATION_HOST:-127.0.0.1}}}"

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
    python -m muxi.runtime.utils.add_secret OPENAI_API_KEY "$OPENAI_API_KEY" 2>/dev/null || true
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "🔐 Setting up ANTHROPIC_API_KEY secret..."
    python -m muxi.runtime.utils.add_secret ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY" 2>/dev/null || true
fi

echo ""
echo "======================================"
echo "🎯 Starting Formation Server..."
echo "======================================"
echo ""

# Run the formation server with port and host overrides
# The formation will load secrets from ~/.muxi/secrets.enc
exec python -m muxi.runtime.utils.run_formation "$FORMATION_PATH" --port "$PORT" --host "$HOST"
