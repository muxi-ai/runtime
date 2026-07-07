"""Make the repository root importable so ``bench.memory.*`` resolves.

The bench package lives outside ``src/`` (it is a harness, not part of
the shipped runtime), so unit tests add the repo root to ``sys.path``
regardless of how pytest was invoked.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
