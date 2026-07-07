#!/usr/bin/env python3
"""LoCoMo benchmark runner (Tier 1, secondary).

1,986 multi-hop QA pairs over 10 long conversations; the PRD target
is R@10 >= 85% (turn-level evidence, no rerank). Defaults: K=10.
Adversarial questions (category 5) are unanswerable by design and are
excluded from retrieval aggregates (counted as abstentions).

Usage
-----
::

    uv run python -m bench.memory.locomo_runner --fixture
    MUXI_BENCH_DATA_DIR=~/datasets/membench \\
        uv run python -m bench.memory.locomo_runner --mode combined
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.memory.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main("locomo", default_k=10))
