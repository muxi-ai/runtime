#!/usr/bin/env python3
"""Test 2P2: Local 768-dim embeddings via the migrated default slug.

Historically this test verified a legacy MUXI-branded 768-dim slug. That
slug is no longer served by the runtime; after the embedding-platform
migration the default 768-dim local slug is
``local/nomic-ai/nomic-embed-text-v1.5`` (the new
``DEFAULT_EMBEDDING_MODEL``). This test now validates:

1. A formation relying on the default embedding slug loads cleanly.
2. The probed dimension is 768 and memories land in ``memories_768``.
3. Memory add/search round-trips work against the local Nomic v1.5
   backend.

The shared ``formation-local-384.yaml`` formation intentionally leaves
``embedding`` unset so the runtime falls back to
``DEFAULT_EMBEDDING_MODEL``. That configuration is what this test
exercises, and the feature description explicitly asks these tests to
"switch to new default slug".
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest


class TestLocal768Embeddings(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_2p2_local_768_embeddings",
            test_description=(
                "Test 768-dim local embeddings via the migrated default slug "
                "(local/nomic-ai/nomic-embed-text-v1.5)"
            ),
            test_area="2_memory",
        )

    async def test_local_768(self):
        start_time = time.time()
        checks_passed = []

        try:
            # Re-uses the default-slug formation. ``formation-local-384.yaml``
            # declares no embedding model, which now resolves to the shared
            # ``DEFAULT_EMBEDDING_MODEL`` (Nomic v1.5, 768-dim).
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"
            formation_file = formation_dir / "formation-local-384.yaml"
            await self.setup_formation(formation_path=formation_file)

            overlord = self.overlord

            ltm = overlord.long_term_memory
            inner = getattr(ltm, "long_term_memory", ltm)

            # Check 1: Slug resolves to the migrated default (Nomic v1.5).
            from muxi.runtime.services.memory.embedding import DEFAULT_EMBEDDING_MODEL

            assert (
                DEFAULT_EMBEDDING_MODEL == "local/nomic-ai/nomic-embed-text-v1.5"
            ), f"Default slug changed unexpectedly: {DEFAULT_EMBEDDING_MODEL!r}"
            assert inner._embedding_model_name == DEFAULT_EMBEDDING_MODEL, (
                f"Expected {DEFAULT_EMBEDDING_MODEL!r}, " f"got {inner._embedding_model_name!r}"
            )
            checks_passed.append(f"Uses migrated default slug {DEFAULT_EMBEDDING_MODEL}")

            # Check 2: Add a memory — triggers the lazy dimension probe.
            user_id = "test_user_768"
            memory_id = await inner.add(
                content="I enjoy hiking in the mountains and photography",
                metadata={"category": "hobby"},
                external_user_id=user_id,
            )
            print(f"  Created memory: {memory_id}")
            assert memory_id, "Memory ID should not be empty"
            checks_passed.append("Memory created with 768-dim embedding")

            # Check 3: Probed dimension is 768 (Nomic v1.5 native).
            dim = inner.dimension
            print(f"  Embedding dimension: {dim}")
            assert dim == 768, f"Expected 768, got {dim}"
            checks_passed.append("Dimension is 768")

            # Check 4: Verify table name.
            table = inner.MemoryModel.__tablename__
            print(f"  Table name: {table}")
            assert table == "memories_768", f"Expected memories_768, got {table}"
            checks_passed.append("Table is memories_768")

            # Check 5: Search returns the stored memory.
            results = await inner.search(
                query="outdoor activities mountains",
                limit=5,
                external_user_id=user_id,
            )
            print(f"  Search returned {len(results)} results")
            assert len(results) > 0, "Search should return results"
            found = any("hiking" in r.get("text", r.get("content", "")).lower() for r in results)
            assert found, "Stored memory should be found in search results"
            checks_passed.append("Memory search works with 768-dim vectors")

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
    test = TestLocal768Embeddings()
    try:
        await test.test_local_768()
    finally:
        await test.cleanup_formation()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
