#!/usr/bin/env python3
"""Download the full Tier 1 benchmark datasets (NOT committed to git).

The committed fixtures under ``bench/memory/fixtures/`` are small
SYNTHETIC samples that follow each dataset's published schema — they
exist so CI and the self-run never depend on downloads or licensing.
Publishable numbers require the full datasets:

- LongMemEval (cleaned): HuggingFace ``xiaowu0162/longmemeval-cleaned``
  — released with the LongMemEval paper (ICLR 2025); check the
  repository license before redistribution.
- LoCoMo: ``snap-research/locomo`` on GitHub — released under
  CC-BY-NC-4.0 (non-commercial research use).
- ConvoMem: HuggingFace ``Salesforce/ConvoMem`` — CC-BY-NC-4.0
  (non-commercial). Download requires the ``huggingface_hub`` /
  ``datasets`` tooling; see the printed instructions.

Licensing note: CC-BY-NC datasets must never be committed to this
repository or redistributed with MUXI artifacts. They are downloaded
to a local data directory for benchmarking only.

Usage
-----
::

    uv run python -m bench.memory.download_datasets --data-dir ~/datasets/membench
    export MUXI_BENCH_DATA_DIR=~/datasets/membench
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

DOWNLOADS = {
    "longmemeval_s_cleaned.json": (
        "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
        "resolve/main/longmemeval_s_cleaned.json"
    ),
    "locomo10.json": (
        "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
    ),
}

CONVOMEM_INSTRUCTIONS = """\
ConvoMem (Salesforce/ConvoMem, CC-BY-NC-4.0) is distributed via the
HuggingFace Hub and is not fetched automatically. To download:

    pip install huggingface_hub
    hf download Salesforce/ConvoMem --repo-type dataset --local-dir {data_dir}/convomem_raw

Then point --dataset at an evidence JSON file (or export a combined
{data_dir}/convomem.json). The loader accepts either a JSON list of
evidence items or an object grouping items by category.
"""


def download(url: str, target: Path) -> None:
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "muxi-membench/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        target.write_bytes(response.read())
    print(f"  -> {target} ({target.stat().st_size / 1_048_576:.1f} MB)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Directory to store the datasets (export as MUXI_BENCH_DATA_DIR).",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-download files that already exist."
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for filename, url in DOWNLOADS.items():
        target = data_dir / filename
        if target.exists() and not args.force:
            print(f"Already present: {target} (use --force to re-download)")
            continue
        try:
            download(url, target)
        except Exception as exc:
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)

    print()
    print(CONVOMEM_INSTRUCTIONS.format(data_dir=data_dir))
    print(f'Set the environment variable:\n    export MUXI_BENCH_DATA_DIR="{data_dir}"')
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
