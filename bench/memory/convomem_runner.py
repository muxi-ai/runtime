#!/usr/bin/env python3
"""ConvoMem benchmark runner (Tier 1, secondary).

Salesforce/ConvoMem evidence files (75K+ QA pairs across 6 evidence
categories); the PRD target is >= 85%. Evidence conversations are
located by matching ``message_evidences`` texts, so scoring is
session(conversation)-level. Defaults: K=5.

The full dataset is CC-BY-NC-4.0 — do not commit it; see
bench/memory/README.md for download instructions.

Usage
-----
::

    uv run python -m bench.memory.convomem_runner --fixture
    uv run python -m bench.memory.convomem_runner --dataset ~/datasets/membench/convomem.json
"""

import sys
from pathlib import Path

if __package__ in (None, ""):  # direct script invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.memory.runner import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main("convomem", default_k=5))
