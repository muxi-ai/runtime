#!/usr/bin/env python3
"""Test 2P1: Local 384-dim Embeddings (default, no embedding model configured)

Verifies:
1. Table memories_384 is created when no embedding model is configured
2. Memory add/search works with 384-dim local vectors
3. Correct dimension is used end-to-end
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
            test_description="Test local 384-dim embeddings (default fallback)",
            test_area="2_memory",
        )

    async def test_local_384(self):
        start_time = time.time()
        checks_passed = []

        try:
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"
            formation_file = formation_dir / "formation-local-384.yaml"
            await self.setup_formation(formation_path=formation_file)

            overlord = self.overlord

            # Check 1: Verify dimension is 384
            ltm = overlord.long_term_memory
            # Memobase wraps LongTermMemory
            inner = getattr(ltm, "long_term_memory", ltm)
            dim = inner.dimension
            print(f"  Embedding dimension: {dim}")
            assert dim == 384, f"Expected 384, got {dim}"
            checks_passed.append("Dimension is 384")

            # Check 2: Verify table name
            table = inner.MemoryModel.__tablename__
            print(f"  Table name: {table}")
            assert table == "memories_384", f"Expected memories_384, got {table}"
            checks_passed.append("Table is memories_384")

            # Check 3: Add a memory and verify it works
            user_id = "test_user_384"
            memory_id = await inner.add(
                content="I love Python programming and machine learning",
                metadata={"category": "preference"},
                external_user_id=user_id,
            )
            print(f"  Created memory: {memory_id}")
            assert memory_id, "Memory ID should not be empty"
            checks_passed.append("Memory created successfully")

            # Check 4: Search for the memory
            results = await inner.search(
                query="Python programming",
                limit=5,
                external_user_id=user_id,
            )
            print(f"  Search returned {len(results)} results")
            assert len(results) > 0, "Search should return results"
            # Verify the stored memory is found
            found = any("Python" in r.get("text", r.get("content", "")) for r in results)
            assert found, "Stored memory should be found in search results"
            checks_passed.append("Memory search works with 384-dim vectors")

            print(f"  Using local embeddings: {inner._use_local_embeddings}")
            assert inner._use_local_embeddings, "Should use local embeddings"
            checks_passed.append("Uses local embedding model")

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
        await test.test_local_384()
    finally:
        await test.cleanup_formation()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
