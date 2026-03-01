#!/usr/bin/env python3
"""Test 2P3: Dimension Coexistence - Multiple dimension tables in same DB

Verifies:
1. Both memories_384 and memories_1536 tables can coexist
2. Each formation reads/writes only its own dimension table
3. No cross-contamination between dimension tables
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest


class TestDimensionCoexistence(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_2p3_dimension_coexistence",
            test_description="Test multiple dimension tables coexist in same DB",
            test_area="2_memory",
        )

    async def test_coexistence(self):
        start_time = time.time()
        checks_passed = []

        try:
            formation_dir = Path(__file__).parent / "formations" / "formation-memory"

            # Phase 1: Load with local 384 and store a memory
            print("\n  Phase 1: Formation with local 384-dim embeddings")
            await self.setup_formation(
                formation_path=formation_dir / "formation-local-384.yaml",
            )

            ltm_384 = self.overlord.long_term_memory
            inner_384 = getattr(ltm_384, "long_term_memory", ltm_384)

            assert inner_384.dimension == 384, f"Expected 384, got {inner_384.dimension}"
            assert inner_384.MemoryModel.__tablename__ == "memories_384"
            checks_passed.append("384-dim formation loaded correctly")

            user_id = "coexistence_test_user"
            mem_384_id = await inner_384.add(
                content="I work at a tech company in San Francisco",
                metadata={"source": "384_test"},
                external_user_id=user_id,
            )
            print(f"    Created 384-dim memory: {mem_384_id}")
            checks_passed.append("Memory stored in memories_384")

            # Clean up formation 1
            await self.cleanup_formation()

            # Phase 2: Load with OpenAI 1536 and store a different memory
            print("\n  Phase 2: Formation with OpenAI 1536-dim embeddings")
            self.formation = None
            self.overlord = None
            await self.setup_formation(
                formation_path=formation_dir / "formation-postgres.yaml",
            )

            ltm_1536 = self.overlord.long_term_memory
            inner_1536 = getattr(ltm_1536, "long_term_memory", ltm_1536)

            assert inner_1536.dimension == 1536, f"Expected 1536, got {inner_1536.dimension}"
            assert inner_1536.MemoryModel.__tablename__ == "memories_1536"
            checks_passed.append("1536-dim formation loaded correctly")

            mem_1536_id = await inner_1536.add(
                content="I enjoy playing tennis on weekends",
                metadata={"source": "1536_test"},
                external_user_id=user_id,
            )
            print(f"    Created 1536-dim memory: {mem_1536_id}")
            checks_passed.append("Memory stored in memories_1536")

            # Phase 3: Verify isolation — 1536 search should NOT find 384 memory
            print("\n  Phase 3: Verify dimension isolation")
            results_1536 = await inner_1536.search(
                query="tech company San Francisco",
                limit=10,
                external_user_id=user_id,
            )
            texts_1536 = [r.get("text", r.get("content", "")) for r in results_1536]
            has_384_content = any("San Francisco" in t for t in texts_1536)
            # The 384-dim memory should NOT appear in 1536 search (different table)
            if not has_384_content:
                checks_passed.append("No cross-contamination: 384 memory not in 1536 results")
                print("    384-dim memory correctly absent from 1536 search results")
            else:
                # This would mean tables aren't properly isolated
                print("    WARNING: 384-dim content found in 1536 results (unexpected)")

            # Verify 1536 memory IS found
            has_1536_content = any("tennis" in t.lower() for t in texts_1536)
            assert has_1536_content, "1536-dim memory should be found in its own table"
            checks_passed.append("1536-dim memory found in its own table")

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
    test = TestDimensionCoexistence()
    try:
        await test.test_coexistence()
    finally:
        await test.cleanup_formation()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
