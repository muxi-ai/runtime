#!/usr/bin/env python3
"""Test 2P4: Revision pinning via ``local/<repo>:<revision>`` slug notation.

The embedding-platform migration introduced reproducible-deployment
slug pinning: ``local/nomic-ai/nomic-embed-text-v1.5:<revision>`` where
``<revision>`` is a HuggingFace commit SHA, tag, or branch name. OneLLM's
``LocalProvider`` forwards the ``revision=`` kwarg to every downstream HF
entry point (``snapshot_download``, ``hf_hub_download``,
``SentenceTransformer``, ``AutoTokenizer``, ``AutoConfig``).

This e2e test verifies the full stack for that slug notation:

1. **Parser correctness.** ``_parse_model_slug`` extracts
   ``("local/nomic-ai/nomic-embed-text-v1.5", "main")`` from the pinned
   slug; slugs without ``:`` round-trip with ``revision=None``; cloud
   slugs (``openai/...``, ``ollama/...:7b``) pass through unchanged; a
   trailing ``:`` with no revision fails fast with
   ``InvalidRequestError``.

2. **Formation loads with the pinned slug.** A formation declaring
   ``- embedding: "local/nomic-ai/nomic-embed-text-v1.5:main"`` starts
   cleanly and records the **full** slug (including ``:main``) on the
   live memory instance. The slug is split into ``(model, revision)``
   only at OneLLM-call time; storage is verbatim.

3. **Probe respects the revision.** ``probe_dimension()`` uses the
   parsed ``(model, revision)`` pair against OneLLM, so the revision
   flows through to the first download.

4. **Round-trip add/search works.** The pinned revision returns a
   usable 768-dim vector (Nomic v1.5 native dim; unchanged across
   revisions), memories land in ``memories_768``, and search hits the
   stored memory.

Uses ``main`` as the revision rather than a commit SHA so the test
stays green even when a new commit lands on Nomic v1.5 upstream. The
cache key ``(repo, "main")`` is distinct from the unpinned
``(repo, None)`` cache entry, so this test exercises a fresh LRU slot
on first run.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest


PINNED_SLUG = "local/nomic-ai/nomic-embed-text-v1.5:main"
BARE_MODEL = "local/nomic-ai/nomic-embed-text-v1.5"
EXPECTED_REVISION = "main"
EXPECTED_DIM = 768


class TestRevisionPinning(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_2p4_revision_pinning",
            test_description=(
                "Test local/<repo>:<revision> slug notation for HuggingFace "
                "revision pinning (Nomic v1.5:main -> 768-dim)"
            ),
            test_area="2_memory",
        )

    async def test_revision_pinning(self):
        start_time = time.time()
        checks_passed = []

        try:
            # -----------------------------------------------------------------
            # Check 1: Parser behaviour (positive + negative cases). These are
            # unit-ish assertions inside the e2e test so a regression in the
            # parser contract surfaces alongside the formation-level checks.
            # -----------------------------------------------------------------
            from muxi.runtime.services.memory.embedding import _parse_model_slug
            from onellm.errors import InvalidRequestError

            model, rev = _parse_model_slug(PINNED_SLUG)
            assert model == BARE_MODEL, f"Expected {BARE_MODEL!r}, got {model!r}"
            assert rev == EXPECTED_REVISION, (
                f"Expected revision {EXPECTED_REVISION!r}, got {rev!r}"
            )
            checks_passed.append(
                f"_parse_model_slug({PINNED_SLUG!r}) -> ({BARE_MODEL!r}, {EXPECTED_REVISION!r})"
            )

            # Unpinned slug: revision=None (resolves to 'main' downstream)
            model_u, rev_u = _parse_model_slug(BARE_MODEL)
            assert model_u == BARE_MODEL and rev_u is None, (
                f"Unpinned slug should return (model, None); got ({model_u!r}, {rev_u!r})"
            )
            checks_passed.append("Unpinned local/* slug returns revision=None")

            # Cloud slug with ':variant' must pass through untouched
            for cloud in ("openai/text-embedding-3-small", "ollama/llama2:7b"):
                m_c, r_c = _parse_model_slug(cloud)
                assert m_c == cloud and r_c is None, (
                    f"Cloud slug {cloud!r} should pass through; got ({m_c!r}, {r_c!r})"
                )
            checks_passed.append("Cloud slugs (incl. ollama/...:7b) pass through untouched")

            # Negative: trailing ':' must raise InvalidRequestError before any
            # network call — operators need a clear error, not a silent
            # fallback to 'main'.
            try:
                _parse_model_slug("local/nomic-ai/nomic-embed-text-v1.5:")
            except InvalidRequestError:
                checks_passed.append("Trailing ':' raises InvalidRequestError")
            else:
                raise AssertionError(
                    "Expected InvalidRequestError for 'local/...:' with empty revision"
                )

            # -----------------------------------------------------------------
            # Check 2: Formation loads with the pinned slug.
            # -----------------------------------------------------------------
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"
            formation_file = formation_dir / "formation-local-revision-pinned.yaml"
            await self.setup_formation(formation_path=formation_file)

            overlord = self.overlord
            ltm = overlord.long_term_memory
            inner = getattr(ltm, "long_term_memory", ltm)

            # The memory layer stores the slug verbatim — with the ':main'
            # suffix intact. Splitting happens only at embed()/probe() call
            # time via _parse_model_slug inside the helper.
            assert inner._embedding_model_name == PINNED_SLUG, (
                f"Expected memory layer to store the full slug {PINNED_SLUG!r}, "
                f"got {inner._embedding_model_name!r}"
            )
            checks_passed.append(
                f"Memory layer stores full pinned slug verbatim: {PINNED_SLUG}"
            )

            # -----------------------------------------------------------------
            # Check 3 + 4: Probe + round-trip. Triggers the lazy dim resolve
            # which hits OneLLM with revision='main' and downloads (or hits
            # the HF cache for) the main snapshot of Nomic v1.5. First run
            # downloads ~275 MB; subsequent runs are cached.
            # -----------------------------------------------------------------
            user_id = "test_user_revision_pinned"
            memory_id = await inner.add(
                content="The Sierra Nevada mountains are full of alpine lakes",
                metadata={"category": "geography"},
                external_user_id=user_id,
            )
            print(f"  Created memory: {memory_id}")
            assert memory_id, "Memory ID should not be empty"
            checks_passed.append(
                "Memory created via pinned-revision path (download/cache round-trip OK)"
            )

            # Probed dim — Nomic v1.5 native is 768. Pinning to 'main' must
            # not change the dim (same commit). If a future Nomic v1.5
            # revision migrates to a different dim, this test will flag it.
            dim = inner.dimension
            print(f"  Embedding dimension: {dim}")
            assert dim == EXPECTED_DIM, (
                f"Expected {EXPECTED_DIM} (Nomic v1.5 native dim), got {dim}"
            )
            checks_passed.append(f"Dimension is {EXPECTED_DIM} for :main revision")

            # Table name follows dim — same as the unpinned path.
            table = inner.MemoryModel.__tablename__
            print(f"  Table name: {table}")
            assert table == f"memories_{EXPECTED_DIM}", (
                f"Expected memories_{EXPECTED_DIM}, got {table}"
            )
            checks_passed.append(f"Table is memories_{EXPECTED_DIM}")

            # Search round-trip — the stored memory should be retrievable.
            results = await inner.search(
                query="alpine lakes mountains",
                limit=5,
                external_user_id=user_id,
            )
            print(f"  Search returned {len(results)} results")
            assert len(results) > 0, "Search should return results"
            found = any(
                "Sierra" in r.get("text", r.get("content", ""))
                for r in results
            )
            assert found, "Stored memory should be found via pinned-revision search"
            checks_passed.append(
                "Search round-trip works with revision-pinned embeddings"
            )

            duration = time.time() - start_time
            print(f"\n  All checks passed ({len(checks_passed)}) in {duration:.1f}s:")
            for c in checks_passed:
                print(f"    - {c}")

            print("\nSUCCESS")
            sys.stdout.flush()
            os._exit(0)

        except Exception as e:
            print(f"\n  FAILED: {e}")
            raise


async def main():
    test = TestRevisionPinning()
    try:
        await test.test_revision_pinning()
    finally:
        await test.cleanup_formation()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
