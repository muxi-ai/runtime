"""Pre-download and warm the local classifier model before the test suite.

The unit suite's ``test_local_classifier.py`` embeds text with the real
``Xenova/multilingual-e5-small`` ONNX model, which is fetched from the
HuggingFace Hub on a cold cache (~95 MB). When that download stalls
(rate limits, XET transfer hiccups) it hangs *inside* a pytest-timeout
window and takes the whole matrix job down.

Running this warmup before pytest moves the download out of the timed
test, retries transient failures, and primes the on-disk HF cache so the
tests themselves are fast and offline. A persistent failure here is
logged as a warning and exits 0 on purpose: the test fixture skips
gracefully when the Hub is unreachable, so CI reports "skipped" rather
than a false red.
"""

from __future__ import annotations

import asyncio
import sys
import time

RETRIES = 3
BACKOFF_SECONDS = 10


async def _warm() -> None:
    from muxi.runtime.services.classification import get_classifier

    classifier = await get_classifier()
    if not classifier.is_warmed:
        raise RuntimeError("classifier reported not warmed after get_classifier()")


def main() -> int:
    for attempt in range(1, RETRIES + 1):
        started = time.monotonic()
        try:
            asyncio.run(_warm())
            elapsed = time.monotonic() - started
            print(f"[prewarm] classifier model ready (attempt {attempt}, {elapsed:.1f}s)")
            return 0
        except Exception as exc:  # noqa: BLE001 - report any failure and retry
            elapsed = time.monotonic() - started
            print(
                f"[prewarm] attempt {attempt}/{RETRIES} failed after "
                f"{elapsed:.1f}s: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if attempt < RETRIES:
                time.sleep(BACKOFF_SECONDS)

    print(
        "::warning::classifier model prewarm failed after "
        f"{RETRIES} attempts; model-download tests will skip if the Hub "
        "stays unreachable",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
