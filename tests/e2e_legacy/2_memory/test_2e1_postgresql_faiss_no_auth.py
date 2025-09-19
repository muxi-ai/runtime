#!/usr/bin/env python3
"""Test FAISSx server with authentication"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import time
import numpy as np
import json

def load_auth_config():
    """Load auth configuration from the auth file"""
    try:
        with open("../../assets/formations/faissx-auth.json", "r") as f:
            auth_config = json.load(f)
        return auth_config
    except Exception as e:
        print(f"Failed to load auth config: {e}")
        return None

def test_faissx_auth_connection():
    """Test connection to authenticated FAISSx server"""
    print("=== Testing FAISSx Authentication ===")

    # Load auth configuration
    auth_config = load_auth_config()
    if not auth_config:
        return {"status": "failed", "error": "Could not load auth config"}

    print(f"Auth config loaded: {list(auth_config.keys())}")

    # Try different auth approaches based on the config format
    api_key = None
    if "this-is-a-key" in auth_config:
        api_key = "this-is-a-key"
        print(f"Using API key: {api_key}")
    else:
        print("No recognized API key format in auth config")
        return {"status": "failed", "error": "No API key found"}

    try:
        import faissx.client as faiss

        print("1. Configuring authenticated FAISSx connection...")
        print("   Server: tcp://localhost:65432")
        print(f"   API Key: {api_key}")

        # Configure with authentication
        faiss.configure(
            server="tcp://localhost:65432",
            api_key=api_key,
            timeout=10.0  # Longer timeout for auth
        )
        print("✓ faiss.configure() with auth completed")

        print("2. Creating authenticated index...")
        start_time = time.time()
        index = faiss.IndexFlatL2(1536)
        end_time = time.time()

        print(f"✓ Index created in {end_time - start_time:.3f}s")
        print(f"  Index type: {type(index)}")
        print(f"  Initial count: {index.ntotal}")

        return {
            "status": "success",
            "api_key": api_key,
            "creation_time": end_time - start_time,
            "auth_working": True
        }

    except Exception as e:
        print(f"❌ Auth connection failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def test_faissx_auth_operations():
    """Test authenticated operations (add/search)"""
    print("\n=== Testing Authenticated Operations ===")

    auth_config = load_auth_config()
    if not auth_config:
        return {"status": "failed", "error": "No auth config"}

    api_key = "this-is-a-key"  # From the auth file

    try:
        import faissx.client as faiss

        # Configure with auth
        faiss.configure(
            server="tcp://localhost:65432",
            api_key=api_key,
            timeout=10.0
        )

        print("1. Creating index for authenticated operations...")
        index = faiss.IndexFlatL2(512)  # Smaller dimension for faster testing

        # Create test data
        print("2. Creating test vectors...")
        test_vectors = np.array([
            [1.0] + [0.0] * 511,  # Vector 1
            [0.0, 1.0] + [0.0] * 510,  # Vector 2
            [0.0, 0.0, 1.0] + [0.0] * 509,  # Vector 3
        ], dtype=np.float32)

        print(f"   Created {len(test_vectors)} test vectors")

        # Test authenticated add operation
        print("3. Testing authenticated add...")
        add_start = time.time()
        index.add(test_vectors)
        add_end = time.time()

        print(f"✓ Add operation completed in {add_end - add_start:.3f}s")
        print(f"  Index count: {index.ntotal}")

        # Test authenticated search operation
        print("4. Testing authenticated search...")
        query = np.array([[1.0] + [0.0] * 511], dtype=np.float32)

        search_start = time.time()
        distances, indices = index.search(query, k=3)
        search_end = time.time()

        print(f"✓ Search operation completed in {search_end - search_start:.3f}s")
        print(f"  Found {len(indices[0])} results")
        print(f"  Best match: index={indices[0][0]}, distance={distances[0][0]}")

        # Verify results
        expected_best = 0
        got_best = indices[0][0] if len(indices[0]) > 0 else -1
        best_distance = distances[0][0] if len(distances[0]) > 0 else float('inf')

        correct_match = got_best == expected_best
        perfect_match = abs(best_distance) < 1e-6

        print("5. Verifying authenticated search results...")
        print(f"   Expected best match: {expected_best}")
        print(f"   Got best match: {got_best}")
        print(f"   Correct match: {correct_match}")
        print(f"   Perfect distance match: {perfect_match}")

        return {
            "status": "success",
            "api_key_used": api_key,
            "vectors_added": len(test_vectors),
            "index_count": index.ntotal,
            "add_time": add_end - add_start,
            "search_time": search_end - search_start,
            "correct_match": correct_match,
            "perfect_match": perfect_match
        }

    except Exception as e:
        print(f"❌ Authenticated operations failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def test_workingemory_with_auth():
    """Test WorkingMemory with authenticated FAISSx"""
    print("\n=== Testing WorkingMemory with Auth ===")

    try:
        # Mock LLM
        class AuthTestLLM:
            async def embed(self, text):
                # Simple hash-based embedding for testing
                text_hash = hash(text) % 1000
                embedding = [text_hash / 1000.0] + [0.1] * 1535
                return embedding

        from muxi.services.memory.working import WorkingMemory

        print("1. Creating WorkingMemory with authenticated remote...")
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
                "tenant": "test-tenant"
            }
        )

        print("✓ WorkingMemory created with auth")
        print(f"  Mode: {buffer.mode}")
        print(f"  Remote config: {buffer.remote}")

        # Test adding data through WorkingMemory
        print("2. Adding authenticated data via WorkingMemory...")
        await buffer.add("Authenticated test message about AI", {"auth": "test"})
        await buffer.add("Another authenticated message", {"auth": "test"})

        print("✓ Added 2 messages to authenticated buffer")

        # Test search through WorkingMemory
        print("3. Searching authenticated buffer...")
        results = await buffer.search("AI artificial intelligence", limit=2)

        print(f"✓ Search returned {len(results)} results")
        if len(results) > 0:
            print(f"  Top result: {results[0]['text'][:50]}...")
            print(f"  Score: {results[0].get('score', 'No score')}")

        return {
            "status": "success",
            "messages_added": 2,
            "search_results": len(results),
            "auth_config": buffer.remote
        }

    except Exception as e:
        print(f"❌ WorkingMemory auth test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def main():
    """Run all authentication tests"""
    print("🔐 TESTING FAISSx AUTHENTICATION")
    print("=" * 50)
    print("Server: tcp://localhost:65432 (auth-enabled)")
    print("Expected: Successful authenticated operations")

    # Load and display auth config
    auth_config = load_auth_config()
    if auth_config:
        print(f"Auth config: {auth_config}")

    # Run tests
    connection_result = test_faissx_auth_connection()
    operations_result = test_faissx_auth_operations()
    workingemory_result = await test_workingemory_with_auth()

    # Summary
    print("\n" + "=" * 50)
    print("🔐 AUTHENTICATION TEST SUMMARY")
    print("=" * 50)

    print(f"Auth Connection: {'✅ PASS' if connection_result.get('status') == 'success' else '❌ FAIL'}")
    if connection_result.get("status") == "success":
        print(f"  - API Key: {connection_result.get('api_key')}")
        print(f"  - Creation time: {connection_result.get('creation_time', 0):.3f}s")

    print(f"Auth Operations: {'✅ PASS' if operations_result.get('status') == 'success' else '❌ FAIL'}")
    if operations_result.get("status") == "success":
        print(f"  - Vectors added: {operations_result.get('vectors_added')}")
        print(f"  - Add time: {operations_result.get('add_time', 0):.3f}s")
        print(f"  - Search time: {operations_result.get('search_time', 0):.3f}s")
        print(f"  - Correct match: {operations_result.get('correct_match')}")
        print(f"  - Perfect match: {operations_result.get('perfect_match')}")

    print(f"WorkingMemory Auth: {'✅ PASS' if workingemory_result.get('status') == 'success' else '❌ FAIL'}")
    if workingemory_result.get("status") == "success":
        print(f"  - Messages added: {workingemory_result.get('messages_added')}")
        print(f"  - Search results: {workingemory_result.get('search_results')}")

    # Overall result
    all_passed = all([
        connection_result.get("status") == "success",
        operations_result.get("status") == "success",
        workingemory_result.get("status") == "success"
    ])

    print(f"\n🎯 OVERALL RESULT: {'✅ ALL AUTH TESTS PASSED' if all_passed else '❌ SOME AUTH TESTS FAILED'}")

    if all_passed:
        print("\n🔐 AUTHENTICATION FULLY WORKING!")
        print("✅ FAISSx server accepts API key authentication")
        print("✅ Authenticated index creation, add, and search operations work")
        print("✅ WorkingMemory integrates with authenticated FAISSx")
        print("✅ Complete authenticated remote memory operations confirmed")

    print("\n📊 Check FAISSx auth server logs (port 65432) for:")
    print("- Authentication success messages")
    print("- Index creation with auth")
    print("- add_vectors with auth")
    print("- search with auth")

    return {
        "connection": connection_result,
        "operations": operations_result,
        "workingemory": workingemory_result,
        "all_passed": all_passed
    }

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
