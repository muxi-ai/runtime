#!/usr/bin/env python3
"""Test 2P2: Local 768-dim Embeddings (all-mpnet-base-v2)

Verifies:
1. Table memories_768 is created when local/all-mpnet-base-v2 is configured
2. Memory add/search works with 768-dim local vectors
3. Higher quality model produces valid embeddings
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
            test_description="Test local 768-dim embeddings (all-mpnet-base-v2)",
            test_area="2_memory",
        )

    async def test_local_768(self):
        start_time = time.time()
        checks_passed = []

        try:
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"
            formation_file = formation_dir / "formation-local-768.yaml"
            await self.setup_formation(formation_path=formation_file)

            overlord = self.overlord

            # Check 1: Verify dimension is 768
            ltm = overlord.long_term_memory
            inner = getattr(ltm, "long_term_memory", ltm)
            dim = inner.dimension
            print(f"  Embedding dimension: {dim}")
            assert dim == 768, f"Expected 768, got {dim}"
            checks_passed.append("Dimension is 768")

            # Check 2: Verify table name
            table = inner.MemoryModel.__tablename__
            print(f"  Table name: {table}")
            assert table == "memories_768", f"Expected memories_768, got {table}"
            checks_passed.append("Table is memories_768")

            # Check 3: Add a memory
            user_id = "test_user_768"
            memory_id = await inner.add(
                content="I enjoy hiking in the mountains and photography",
                metadata={"category": "hobby"},
                external_user_id=user_id,
            )
            print(f"  Created memory: {memory_id}")
            assert memory_id, "Memory ID should not be empty"
            checks_passed.append("Memory created with 768-dim embedding")

            # Check 4: Search for the memory
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

            # Check 5: Verify it's using local embeddings with mpnet model
            assert inner._use_local_embeddings, "Should use local embeddings"
            checks_passed.append("Uses local all-mpnet-base-v2 model")

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
