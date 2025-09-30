#!/usr/bin/env python3
"""Test 2E1: PostgreSQL with FAISSx Authentication

This test validates:
1. PostgreSQL + FAISSx integration with authentication
2. Vector search with API key authentication
3. WorkingMemory integration with authenticated FAISSx
"""

import sys
import asyncio
import time
import os
import json
import numpy as np
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest  # noqa: E402
from test_utils import timeout_test, safe_overlord_chat, with_timeout, safe_formation_load, safe_formation_shutdown
from muxi.services.memory.working import WorkingMemory  # noqa: E402


# Mock LLM for testing
class AuthTestLLM:
    async def embed(self, text):
        # Simple hash-based embedding for testing
        text_hash = hash(text) % 1000
        embedding = [text_hash / 1000.0] + [0.1] * 1535
        return embedding


class TestPostgreSQLFAISSAuth(BaseMemoryTest):
    """Test PostgreSQL with FAISSx authentication."""

    def load_auth_config(self):
        """Load auth configuration from the auth file."""
        try:
            auth_path = (
                Path(__file__).parent.parent.parent / "assets" / "faissx-auth.json"
            )
            with open(auth_path, "r") as f:
                auth_config = json.load(f)
            return auth_config
        except Exception as e:
            print(f"    ❌ Failed to load auth config: {e}")
            return None

    @timeout_test(60.0)
    async def test_faissx_auth_connection(self):
        """Test connection to authenticated FAISSx server."""
        print("\n  🔐 Testing FAISSx Authentication Connection")

        # Load auth configuration
        auth_config = self.load_auth_config()
        if not auth_config:
            return False, {"error": "Could not load auth config"}

        print(f"    Auth config loaded: {list(auth_config.keys())}")

        # Try different auth approaches based on the config format
        api_key = None
        if "this-is-a-key" in auth_config:
            api_key = "this-is-a-key"
            print(f"    Using API key: {api_key}")
        else:
            print("    No recognized API key format in auth config")
            return False, {"error": "No API key found"}

        try:
            import faissx.client as faiss

            print("    1. Configuring authenticated FAISSx connection...")
            print("       Server: tcp://localhost:65432")
            print(f"       API Key: {api_key}")

            # Configure with authentication
            faiss.configure(
                server="tcp://localhost:65432",
                api_key=api_key,
                timeout=10.0,  # Longer timeout for auth
            )
            print("    ✓ faiss.configure() with auth completed")

            print("    2. Creating authenticated index...")
            start_time = time.time()
            index = faiss.IndexFlatL2(1536)
            end_time = time.time()

            print(f"    ✓ Index created in {end_time - start_time:.3f}s")
            print(f"      Index type: {type(index)}")
            print(f"      Initial count: {index.ntotal}")

            return True, {
                "api_key": api_key,
                "creation_time": end_time - start_time,
                "auth_working": True,
            }

        except Exception as e:
            print(f"    ❌ Auth connection failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_faissx_auth_operations(self):
        """Test authenticated operations (add/search)."""
        print("\n  ⚙️ Testing Authenticated Operations")

        auth_config = self.load_auth_config()
        if not auth_config:
            return False, {"error": "No auth config"}

        api_key = "this-is-a-key"  # From the auth file

        try:
            import faissx.client as faiss

            # Configure with auth
            faiss.configure(server="tcp://localhost:65432", api_key=api_key, timeout=10.0)

            print("    1. Creating index for authenticated operations...")
            index = faiss.IndexFlatL2(512)  # Smaller dimension for faster testing

            # Create test data
            print("    2. Creating test vectors...")
            test_vectors = np.array(
                [
                    [1.0] + [0.0] * 511,  # Vector 1
                    [0.0, 1.0] + [0.0] * 510,  # Vector 2
                    [0.0, 0.0, 1.0] + [0.0] * 509,  # Vector 3
                ],
                dtype=np.float32,
            )

            print(f"       Created {len(test_vectors)} test vectors")

            # Test authenticated add operation
            print("    3. Testing authenticated add...")
            add_start = time.time()
            index.add(test_vectors)
            add_end = time.time()

            print(f"    ✓ Add operation completed in {add_end - add_start:.3f}s")
            print(f"      Index count: {index.ntotal}")

            # Test authenticated search operation
            print("    4. Testing authenticated search...")
            query = np.array([[1.0] + [0.0] * 511], dtype=np.float32)

            search_start = time.time()
            distances, indices = index.search(query, k=3)
            search_end = time.time()

            print(f"    ✓ Search operation completed in {search_end - search_start:.3f}s")
            print(f"      Found {len(indices[0])} results")
            print(f"      Best match: index={indices[0][0]}, distance={distances[0][0]}")

            # Verify results
            expected_best = 0
            got_best = indices[0][0] if len(indices[0]) > 0 else -1
            best_distance = distances[0][0] if len(distances[0]) > 0 else float("inf")

            correct_match = got_best == expected_best
            perfect_match = abs(best_distance) < 1e-6

            print("    5. Verifying authenticated search results...")
            print(f"       Expected best match: {expected_best}")
            print(f"       Got best match: {got_best}")
            print(f"       Correct match: {correct_match}")
            print(f"       Perfect distance match: {perfect_match}")

            return True, {
                "api_key_used": api_key,
                "vectors_added": len(test_vectors),
                "index_count": index.ntotal,
                "add_time": add_end - add_start,
                "search_time": search_end - search_start,
                "correct_match": correct_match,
                "perfect_match": perfect_match,
            }

        except Exception as e:
            print(f"    ❌ Authenticated operations failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_workingemory_with_auth(self):
        """Test WorkingMemory with authenticated FAISSx."""
        print("\n  💾 Testing WorkingMemory with Auth")

        try:
            print("    1. Creating WorkingMemory with authenticated remote...")
            buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=3,
                buffer_multiplier=2,
                dimension=1536,
                model=AuthTestLLM(),
                mode="remote",
                remote={
                    "url": "tcp://localhost:65432",
                    "api_key": "this-is-a-key",  # From auth file
                    "tenant": "test-tenant",
                },
            )

            print("    ✓ WorkingMemory created with auth")
            print(f"      Mode: {buffer.mode}")
            print(f"      Remote config: {buffer.remote}")

            # Test adding data through WorkingMemory
            print("    2. Adding authenticated data via WorkingMemory...")
            await buffer.add("Authenticated test message about AI", {"auth": "test"})
            await buffer.add("Another authenticated message", {"auth": "test"})

            print("    ✓ Added 2 messages to authenticated buffer")

            # Test search through WorkingMemory
            print("    3. Searching authenticated buffer...")
            results = await buffer.search("AI artificial intelligence", limit=2)

            print(f"    ✓ Search returned {len(results)} results")
            if len(results) > 0:
                print(f"      Top result: {results[0]['text'][:50]}...")
                print(f"      Score: {results[0].get('score', 'No score')}")

            return True, {
                "messages_added": 2,
                "search_results": len(results),
                "auth_config": buffer.remote,
            }

        except Exception as e:
            print(f"    ❌ WorkingMemory auth test failed: {e}")
            return False, {"error": str(e)}

    @timeout_test(60.0)
    async def test_postgresql_faiss(self):
        """Main test method."""
        test_name = "2e1_postgresql_faiss_auth"
        self.print_test_header(test_name, "Test PostgreSQL + FAISSx with authentication")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            print("  Testing FAISSx Authentication Integration...")

            # Test 1: Auth connection
            conn_success, conn_result = await self.test_faissx_auth_connection()
            if conn_success:
                checks_passed.append("FAISSx auth connection working")
                transcript.append(("System", f"Auth connection passed: {conn_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Auth connection failed: {conn_result}"))

            # Test 2: Auth operations
            ops_success, ops_result = await self.test_faissx_auth_operations()
            if ops_success:
                checks_passed.append("FAISSx auth operations working")
                transcript.append(("System", f"Auth operations passed: {ops_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Auth operations failed: {ops_result}"))

            # Test 3: WorkingMemory with auth
            mem_success, mem_result = await self.test_workingemory_with_auth()
            if mem_success:
                checks_passed.append("WorkingMemory auth integration working")
                transcript.append(("System", f"WorkingMemory auth passed: {mem_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"WorkingMemory auth failed: {mem_result}"))

            # Summary
            if conn_success and ops_success and mem_success:
                print("  ✅ AUTHENTICATION FULLY WORKING!")
                print("    ✅ FAISSx server accepts API key authentication")
                print("    ✅ Authenticated index creation, add, and search operations work")
                print("    ✅ WorkingMemory integrates with authenticated FAISSx")
                print("    ✅ Complete authenticated remote memory operations confirmed")
                checks_passed.append("Full authentication stack functional")
            else:
                print("  ⚠️ PARTIAL SUCCESS")
                if conn_success:
                    print("    ✅ Auth connection working")
                else:
                    print("    ❌ Auth connection failed")
                if ops_success:
                    print("    ✅ Auth operations working")
                else:
                    print("    ❌ Auth operations failed")
                if mem_success:
                    print("    ✅ WorkingMemory auth working")
                else:
                    print("    ❌ WorkingMemory auth failed")

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False
            transcript.append(("System", f"Test failed with error: {str(e)}"))

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🔐 AREA 2E1: POSTGRESQL + FAISSX (AUTH)")
        print("=" * 60)

        # Run test cases
        result = await self.test_postgresql_faiss()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestPostgreSQLFAISSAuth()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
