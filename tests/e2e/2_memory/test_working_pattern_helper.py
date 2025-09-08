#!/usr/bin/env python3
"""Test the exact pattern used by WorkingMemory"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import time
import numpy as np

async def test_workingemory_exact_pattern():
    """Replicate the exact pattern used by WorkingMemory"""
    print("=== Replicating WorkingMemory Pattern ===")

    try:
        # Import exactly as WorkingMemory does
        from faissx import client as faiss

        print("1. Setting up remote configuration...")
        mode = "remote"
        remote = {
            "url": "tcp://localhost:45678",
            "api_key": None,
            "tenant": None
        }
        dimension = 1536

        # Configure FAISS for remote mode (exact WorkingMemory code)
        if mode == "remote" and remote:
            print("   Calling faiss.configure() with:")
            print(f"   - server: {remote.get('url')}")
            print(f"   - api_key: {remote.get('api_key')}")
            print(f"   - tenant_id: {remote.get('tenant')}")

            faiss.configure(
                server=remote.get("url"),
                api_key=remote.get("api_key"),
                tenant_id=remote.get("tenant"),
            )
            print("✓ faiss.configure() completed")

        # Initialize vector storage (exact WorkingMemory code)
        print("2. Creating IndexFlatL2...")
        index = faiss.IndexFlatL2(dimension)
        print(f"✓ Index created: {type(index)}")

        # Test add operation (similar to WorkingMemory._add_embedding)
        print("3. Testing add operation...")
        embedding = [0.1] * dimension  # Mock embedding
        embedding_array = np.array([embedding], dtype=np.float32)

        add_start = time.time()
        index.add(embedding_array)
        add_end = time.time()

        print(f"✓ Add completed in {add_end - add_start:.3f}s")
        print(f"  Index count: {index.ntotal}")

        # Test search operation (similar to WorkingMemory._vector_search_faiss)
        print("4. Testing search operation...")
        query_embedding = [0.1] * dimension
        query_array = np.array([query_embedding], dtype=np.float32)

        search_start = time.time()
        distances, indices = index.search(query_array, k=1)
        search_end = time.time()

        print(f"✓ Search completed in {search_end - search_start:.3f}s")
        print(f"  Results: distances={distances[0]}, indices={indices[0]}")

        return {
            "status": "success",
            "add_time": add_end - add_start,
            "search_time": search_end - search_start,
            "index_count": index.ntotal
        }

    except Exception as e:
        print(f"❌ Pattern test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def test_multiple_configure_calls():
    """Test if multiple configure calls interfere with each other"""
    print("\n=== Testing Multiple Configure Calls ===")

    try:
        from faissx import client as faiss

        print("1. First configure call...")
        faiss.configure(server="tcp://localhost:45678")
        index1 = faiss.IndexFlatL2(128)

        print("2. Second configure call (same server)...")
        faiss.configure(server="tcp://localhost:45678")  # Same as first
        index2 = faiss.IndexFlatL2(128)

        print("3. Testing both indexes...")
        test_vec = np.random.random((1, 128)).astype(np.float32)

        index1.add(test_vec)
        index2.add(test_vec)

        print(f"✓ Index1 count: {index1.ntotal}")
        print(f"✓ Index2 count: {index2.ntotal}")

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Multiple configure test failed: {e}")
        return {"status": "failed", "error": str(e)}

async def test_with_actual_workingemory():
    """Test with actual WorkingMemory class"""
    print("\n=== Testing Actual WorkingMemory Class ===")

    try:
        # Mock LLM
        class MockLLM:
            async def embed(self, text):
                return [0.1] * 1536

        from muxi.services.memory.working import WorkingMemory

        print("1. Creating WorkingMemory with remote mode...")
        buffer = WorkingMemory(
            formation_id="test_formation",
            max_size=3,
            buffer_multiplier=2,
            dimension=1536,
            model=MockLLM(),
            mode="remote",
            remote={"url": "tcp://localhost:45678"}
        )

        print("✓ WorkingMemory created")
        print(f"  Mode: {buffer.mode}")
        print(f"  Remote config: {buffer.remote}")
        print(f"  Index type: {type(buffer.index)}")

        # Check if index is truly remote by looking at its class
        index_class = str(type(buffer.index))
        is_remote_class = "faissx" in index_class.lower()
        print(f"  Is remote index class: {is_remote_class}")

        # Test direct index operations
        print("2. Testing direct index operations...")
        test_embedding = np.array([[0.1] * 1536], dtype=np.float32)

        add_start = time.time()
        buffer.index.add(test_embedding)
        add_end = time.time()

        print(f"✓ Direct index.add() in {add_end - add_start:.3f}s")
        print(f"  Index count: {buffer.index.ntotal}")

        # Test search
        search_start = time.time()
        distances, indices = buffer.index.search(test_embedding, k=1)
        search_end = time.time()

        print(f"✓ Direct index.search() in {search_end - search_start:.3f}s")
        print(f"  Results: {distances[0]}, {indices[0]}")

        return {
            "status": "success",
            "is_remote_class": is_remote_class,
            "add_time": add_end - add_start,
            "search_time": search_end - search_start,
            "index_count": buffer.index.ntotal
        }

    except Exception as e:
        print(f"❌ WorkingMemory test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def main():
    """Run all pattern tests"""
    print("🔍 TESTING WORKING MEMORY FAISSX PATTERN")
    print("=" * 60)
    print("Goal: Replicate exact WorkingMemory usage and find the issue")

    # Run tests
    pattern_result = test_workingemory_exact_pattern()
    configure_result = test_multiple_configure_calls()
    workingemory_result = test_with_actual_workingemory()

    # Summary
    print("\n" + "=" * 60)
    print("🔍 PATTERN TEST SUMMARY")
    print("=" * 60)

    print(f"Pattern Replication: {'✅ PASS' if pattern_result.get('status') == 'success' else '❌ FAIL'}")
    if pattern_result.get("status") == "success":
        print(f"  - Add time: {pattern_result.get('add_time', 0):.3f}s")
        print(f"  - Search time: {pattern_result.get('search_time', 0):.3f}s")

    print(f"Multiple Configure: {'✅ PASS' if configure_result.get('status') == 'success' else '❌ FAIL'}")

    print(f"Actual WorkingMemory: {'✅ PASS' if workingemory_result.get('status') == 'success' else '❌ FAIL'}")
    if workingemory_result.get("status") == "success":
        print(f"  - Remote index class: {workingemory_result.get('is_remote_class')}")
        print(f"  - Add time: {workingemory_result.get('add_time', 0):.3f}s")
        print(f"  - Search time: {workingemory_result.get('search_time', 0):.3f}s")

    # Conclusions
    all_passed = all([
        pattern_result.get("status") == "success",
        configure_result.get("status") == "success",
        workingemory_result.get("status") == "success"
    ])

    print("\n🎯 CONCLUSIONS:")
    if all_passed:
        remote_class = workingemory_result.get('is_remote_class', False)
        if remote_class:
            print("✅ WorkingMemory IS using remote FAISSx indexes")
            print("✅ The remote configuration is working correctly")
            print("🔍 If no server logs, check server logging configuration")
        else:
            print("❌ WorkingMemory is NOT using remote FAISSx indexes")
            print("🐛 This explains the fallback to local behavior")
    else:
        print("❌ Pattern replication failed - configuration issues detected")

    print("\n💡 NEXT STEPS:")
    print("1. Check FAISSx server logs during this test")
    print("2. If logs appear, remote operations are working")
    print("3. If no logs, investigate FAISSx server configuration")
    print("4. Consider adding debug logging to WorkingMemory")

if __name__ == "__main__":
    main()
