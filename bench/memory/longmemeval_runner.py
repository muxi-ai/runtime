#!/usr/bin/env python3
"""LongMemEval benchmark runner (Tier 1, primary).

500 questions across 6 types; the PRD target is R@5 >= 94% in
combined mode. Defaults: K=5, session-level scoring is the headline.

Usage
-----
::

    # Committed fixture sample (CI-safe, no dataset download)
    uv run python -m bench.memory.longmemeval_runner --fixture

    # Full dataset (see bench/memory/README.md for the download)
    export MUXI_BENCH_DATA_DIR=~/datasets/membench
    uv run python -m bench.memory.longmemeval_runner --mode combined --split holdout
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.memory.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main("longmemeval", default_k=5))
