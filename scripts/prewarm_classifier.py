"""Pre-download the local models the unit suite needs before pytest runs.

Two unit-test areas embed text with real local ONNX models fetched from
the HuggingFace Hub on a cold cache:

* ``test_local_classifier.py`` -> ``Xenova/multilingual-e5-small`` (~95 MB)
* ``test_sops_search.py``      -> ``nomic-ai/nomic-embed-text-v1.5`` (~140 MB)

Running the fetch here (via the authenticated hf_xet client) moves the
one-time download out of the timed tests, retries transient failures,
and primes the on-disk HF cache so the tests are fast and offline. If
every retry fails the script exits non-zero so the failure surfaces here
as a clear "model download failed" signal rather than as an opaque test
error downstream.
"""

from __future__ import annotations

import asyncio
import sys
import time

RETRIES = 3
BACKOFF_SECONDS = 10


async def _warm() -> None:
    from muxi.runtime.services.classification import get_classifier
    from muxi.runtime.services.memory.embedding import DEFAULT_EMBEDDING_MODEL, embed

    classifier = await get_classifier()
    if not classifier.is_warmed:
        raise RuntimeError("classifier reported not warmed after get_classifier()")

    # Prime the default embedding model used by the sops-search tests.
    await embed(DEFAULT_EMBEDDING_MODEL, ["query: warmup"])


def main() -> int:
    for attempt in range(1, RETRIES + 1):
        started = time.monotonic()
        try:
            asyncio.run(_warm())
            elapsed = time.monotonic() - started
            print(f"[prewarm] models ready (attempt {attempt}, {elapsed:.1f}s)")
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
        f"::error::model prewarm failed after {RETRIES} attempts; "
        "the HuggingFace Hub download did not succeed",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
