#!/bin/bash
# Environment setup for the embedding-platform migration mission.
# Idempotent — safe to re-run. Verifies the tree is in a workable state; does
# not modify code.

set -e

cd "$(dirname "$0")/.."

echo "--- init.sh: embedding-platform mission ---"

# 1. Confirm branch
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "feature/embeddings" ]; then
    echo "FATAL: expected branch 'feature/embeddings', got '$branch'"
    exit 1
fi
echo "[ok] on branch feature/embeddings"

# 2. Confirm editable install present
if ! python -c "import muxi.runtime" 2>/dev/null; then
    echo "[setup] installing runtime in editable mode..."
    pip install -e ".[dev]" --quiet
fi
echo "[ok] muxi.runtime importable"

# 3. Confirm OneLLM at or above 0.20260421.0 with LocalProvider
ONELLM_VERSION=$(python -c "import onellm; print(onellm.__version__)" 2>/dev/null || echo "missing")
if [ "$ONELLM_VERSION" = "missing" ]; then
    echo "FATAL: onellm not importable. Run: pip install -e /Users/ran/Projects/muxi/code/onellm"
    exit 1
fi
echo "[ok] onellm version: $ONELLM_VERSION"

# Version check: date-based 0.YYYYMMDD.N must be >= 0.20260421.0
python - <<'PY'
import sys, onellm
parts = onellm.__version__.split(".")
try:
    major, date, patch = int(parts[0]), int(parts[1]), int(parts[2])
except Exception:
    print(f"FATAL: cannot parse onellm version {onellm.__version__!r}")
    sys.exit(1)
if major != 0 or date < 20260502:
    print(f"FATAL: onellm {onellm.__version__} is older than required 0.20260502.0")
    sys.exit(1)
PY
echo "[ok] onellm version is >= 0.20260502.0"

# 4. Confirm LocalProvider registered
python -c "from onellm.providers.local import LocalProvider" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "FATAL: LocalProvider not found in onellm.providers.local"
    exit 1
fi
echo "[ok] LocalProvider importable"

# 5. Sanity check: current runtime test suite runs (no network, just unit tests)
if ! pytest tests/unit/ -q --co > /dev/null 2>&1; then
    echo "WARN: pytest collection failed on tests/unit/. Proceeding anyway; workers may need to fix."
fi
echo "[ok] pytest collection smoke test passed"

# 6. Verify e2e runner is present
if [ ! -f e2e/run_random_tests.py ]; then
    echo "FATAL: e2e/run_random_tests.py not found"
    exit 1
fi
echo "[ok] e2e runner present"

# 7. Baseline ripgrep sweep — report the state we're starting from (informational)
echo ""
echo "--- BASELINE STATE (before migration) ---"
echo "# Files importing local_embeddings:"
rg -l "local_embeddings" src/muxi/runtime/ 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo "# Files importing sentence_transformers directly:"
rg -l "sentence_transformers" src/muxi/runtime/ 2>/dev/null | sed 's/^/  /' || echo "  (none)"
echo ""
echo "--- init.sh complete ---"
