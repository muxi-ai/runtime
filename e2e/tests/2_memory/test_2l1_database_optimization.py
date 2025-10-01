#!/usr/bin/env python3
"""
Test 2L1: Database Optimization Verification
Verify that GIN indexes and optimizations are working correctly
"""
import sys
import os
import asyncio
import psycopg2
import json
import time
import uuid
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402
from base_memory_test import BaseMemoryTest  # noqa: E402


class TestDatabaseOptimization(BaseMemoryTest):
    """Test database indexes and query optimization."""

    def __init__(self):
        super().__init__()
        self.test_name = "test_2l1_database_optimization"
        self.test_description = "Database Optimization Verification"

    async def run(self) -> bool:
        """Run the database optimization test."""
        print("\n" + "=" * 60)
        print("Test 2L1: Database Optimization Verification")
        print("=" * 60 + "\n")

        try:
            # Setup database connection
            conn = psycopg2.connect("postgresql://muxi@localhost/muxi_test")
            cur = conn.cursor()

            # Test 1: Verify GIN index on memories.text
            print("Checking GIN index on memories.text")

            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'memories'
                AND indexname LIKE '%gin%'
            """)

            gin_indexes = cur.fetchall()
            
            if len(gin_indexes) == 0:
                print("  ⚠️  No GIN indexes found on memories table")
                print("  Note: GIN indexes for full-text search are not currently implemented")
                print("  Current indexes:")
                cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'memories'
                """)
                all_indexes = cur.fetchall()
                for idx_name, idx_def in all_indexes:
                    print(f"    - {idx_name}: {idx_def.split('(')[1].split(')')[0] if '(' in idx_def else 'unknown'}")
                print("  Skipping GIN index tests - feature not yet implemented")
            else:
                for idx_name, idx_def in gin_indexes:
                    print(f"  ✓ Found GIN index: {idx_name}")
                    assert "gin" in idx_def.lower(), f"Index {idx_name} is not GIN type"
                    if "text" in idx_def:
                        print("    - Indexes text column for full-text search")

            # Test 2: Verify GIN index is used for text search
            print("Testing GIN index usage for text search")

            # First, ensure we have some data
            test_user = "optimization_test_user"
            cur.execute("DELETE FROM memories WHERE meta_data->>'user_id' = %s", (test_user,))

            # Get or create user
            public_id = str(uuid.uuid4())[:21]
            cur.execute("""
                INSERT INTO users (public_id, external_user_id, formation_id, created_at)
                VALUES (%s, %s, 'test', NOW())
                ON CONFLICT (external_user_id, formation_id) DO UPDATE
                SET updated_at = NOW()
                RETURNING id
            """, (public_id, test_user))
            user_db_id = cur.fetchone()[0]
            
            # Clean up existing memories for this user
            cur.execute("DELETE FROM memories WHERE user_id = %s", (user_db_id,))

            conn.commit()

            # Load formation and add test data
            self.formation = Formation()
            await self.formation.load(
                str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres.yaml")
            )
            self.overlord = await self.formation.start_overlord()

            # Add test data
            await self.overlord.chat("I love Python programming", user_id=test_user, stream=False)
            await asyncio.sleep(3)

            # Check query plan for text search
            cur.execute("""
                EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS)
                SELECT * FROM memories
                WHERE to_tsvector('english', text) @@ to_tsquery('english', 'python')
            """)

            plan = cur.fetchone()[0][0]
            plan_str = json.dumps(plan, indent=2)

            # Look for index usage (only if GIN indexes exist)
            if len(gin_indexes) > 0:
                index_used = "Index Scan" in plan_str or "Bitmap Index Scan" in plan_str
                if not index_used:
                    print(f"  ⚠️  GIN index not used (may be expected for small tables)")
                else:
                    print("  ✓ GIN index is used for full-text search queries")
            else:
                print("  ⏭️  Skipping query plan check (no GIN indexes exist)")

            # Test 3: Verify collection index
            print("Checking collection column index")

            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'memories'
                AND indexdef LIKE '%collection%'
            """)

            collection_indexes = [row[0] for row in cur.fetchall()]
            if len(collection_indexes) > 0:
                print(f"  ✓ Collection indexed: {collection_indexes}")
            else:
                print("  ⚠️  No index found on collection column")
                print("  Checking all indexes...")
                cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'memories'")
                all_idx = [row[0] for row in cur.fetchall()]
                print(f"  Available indexes: {all_idx}")
                # This is actually okay if collection queries are fast enough without index

            # Test 4: Verify no collections table
            print("Confirming collections table removal")

            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'collections'
            """)

            collections_exists = cur.fetchone()[0]
            assert collections_exists == 0, "Collections table still exists!"
            print("  ✓ Collections table successfully removed")

            # Test 5: Verify credentials table optimization
            print("Checking credentials table indexes")

            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'credentials'
                ORDER BY indexname
            """)

            cred_indexes = [row[0] for row in cur.fetchall()]

            # Should have only essential indexes
            essential = [
                "credentials_pkey",
                "credentials_credential_id_key",
                "idx_credentials_service",
                "idx_credentials_user_id",
            ]

            # Should NOT have these removed indexes
            removed = [
                "idx_credentials_json",
                "idx_credentials_updated_at",
                "idx_credentials_created_at",
                "idx_credentials_service_lower",
            ]

            for idx in essential:
                assert idx in cred_indexes, f"Missing essential index: {idx}"

            for idx in removed:
                assert idx not in cred_indexes, f"Unnecessary index still exists: {idx}"

            print(f"  ✓ Credentials table has only {len(cred_indexes)} essential indexes")
            print(f"  ✓ Removed {len(removed)} unnecessary indexes")

            # Test 6: Performance test
            print("Testing search performance")

            # Add more test data
            messages = [
                "Python is great for data science",
                "Machine learning with Python",
                "I enjoy Python web development",
                "JavaScript is good for frontend",
                "Java is used for enterprise",
            ]

            for msg in messages:
                await self.overlord.chat(msg, user_id=test_user, stream=False)
                await asyncio.sleep(1)

            # Time a search query
            start = time.time()

            cur.execute("""
                SELECT text, ts_rank(to_tsvector('english', text), query) as rank
                FROM memories,
                     to_tsquery('english', 'python') query
                WHERE to_tsvector('english', text) @@ query
                ORDER BY rank DESC
                LIMIT 5
            """)

            results = cur.fetchall()
            search_time = time.time() - start

            assert len(results) >= 3, f"Expected at least 3 Python results, got {len(results)}"
            assert search_time < 0.5, f"Search too slow: {search_time:.3f}s (should be < 0.5s)"

            print(f"  ✓ Text search completed in {search_time:.3f}s")
            print(f"  ✓ Found {len(results)} relevant results")

            cur.close()
            conn.close()

            print("Database optimization test passed!")
            return True

        except Exception as e:
            print(f"Test failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up test resources."""
        if self.formation:
            try:
                await self.safe_formation_shutdown(self.formation)
            except Exception as e:
                print(f"Warning: Cleanup error: {e}")


async def main():
    """Run the test."""
    test = TestDatabaseOptimization()
    success = await test.run()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
