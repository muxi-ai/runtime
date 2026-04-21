#!/usr/bin/env python3
"""Test 2P1: Default local embeddings (no explicit model configured)

Historically this test exercised a legacy 384-dim MiniLM fallback. After
the embedding-platform migration there is a single default embedding
slug, ``local/nomic-ai/nomic-embed-text-v1.5`` (768-dim, Apache-2.0),
wired up in ``services/memory/embedding.DEFAULT_EMBEDDING_MODEL``. This
test now verifies that default path end-to-end:

1. Formation without an embedding model picks up the new default slug.
2. The ``memories_768`` table is selected after the lazy dimension probe.
3. Memory add/search round-trips work against the default model.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest


class TestLocal384Embeddings(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_2p1_local_384_embeddings",
            test_description=(
                "Test default local embeddings (no explicit model; "
                "falls back to DEFAULT_EMBEDDING_MODEL = Nomic v1.5, 768-dim)"
            ),
            test_area="2_memory",
        )

    async def test_local_default(self):
        start_time = time.time()
        checks_passed = []

        try:
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"
            formation_file = formation_dir / "formation-local-384.yaml"
            await self.setup_formation(formation_path=formation_file)

            overlord = self.overlord

            # Memobase wraps LongTermMemory
            ltm = overlord.long_term_memory
            inner = getattr(ltm, "long_term_memory", ltm)

            # Check 1: Model slug resolves to the default Nomic v1.5 model.
            from muxi.runtime.services.memory.embedding import DEFAULT_EMBEDDING_MODEL

            assert inner._embedding_model_name == DEFAULT_EMBEDDING_MODEL, (
                f"Expected default slug {DEFAULT_EMBEDDING_MODEL!r}, "
                f"got {inner._embedding_model_name!r}"
            )
            checks_passed.append(f"Default embedding slug is {DEFAULT_EMBEDDING_MODEL}")

            # Check 2: Add a memory — triggers the lazy dimension probe.
            user_id = "test_user_default"
            memory_id = await inner.add(
                content="I love Python programming and machine learning",
                metadata={"category": "preference"},
                external_user_id=user_id,
            )
            print(f"  Created memory: {memory_id}")
            assert memory_id, "Memory ID should not be empty"
            checks_passed.append("Memory created successfully")

            # Check 3: Dimension is 768 after lazy probe (Nomic v1.5 native dim).
            dim = inner.dimension
            print(f"  Embedding dimension: {dim}")
            assert dim == 768, f"Expected 768 (Nomic v1.5 native dim), got {dim}"
            checks_passed.append("Dimension is 768 (Nomic v1.5)")

            # Check 4: Table name follows the probed dimension.
            table = inner.MemoryModel.__tablename__
            print(f"  Table name: {table}")
            assert table == "memories_768", f"Expected memories_768, got {table}"
            checks_passed.append("Table is memories_768")

            # Check 5: Search returns the stored memory.
            results = await inner.search(
                query="Python programming",
                limit=5,
                external_user_id=user_id,
            )
            print(f"  Search returned {len(results)} results")
            assert len(results) > 0, "Search should return results"
            found = any("Python" in r.get("text", r.get("content", "")) for r in results)
            assert found, "Stored memory should be found in search results"
            checks_passed.append("Memory search works via the default slug")

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
    test = TestLocal384Embeddings()
    try:
        await test.test_local_default()
    finally:
        await test.cleanup_formation()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
