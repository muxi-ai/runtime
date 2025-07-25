#!/usr/bin/env python3
"""Test FAISSx configure function and remote connection"""

import sys
import asyncio
sys.path.insert(0, '.')
import time
import traceback

async def test_faissx_import():
    """Test basic faissx import and structure"""
    print("=== Testing FAISSx Import ===")
    try:
        import faissx.client as faiss
        print(f"✓ faissx imported successfully")
        print(f"  Version: {getattr(faiss, '__version__', 'unknown')}")
        print(f"  Available methods: {len(dir(faiss))} methods")
        return True
    except Exception as e:
        print(f"❌ faissx import failed: {e}")
        return False

async def test_faissx_configure_no_auth():
    """Test faiss.configure with no-auth server"""
    print("\n=== Testing FAISSx Configure (No Auth) ===")
    try:
        import faissx.client as faiss

        print("1. Configuring for remote server (no auth)...")
        print("   Server: tcp://localhost:45678")

        # This should configure the global client
        faiss.configure(
            server="tcp://localhost:45678",
            timeout=5.0
        )
        print("✓ faiss.configure() completed without error")

        print("2. Creating IndexFlatL2 (should use remote server)...")
        start_time = time.time()
        index = faiss.IndexFlatL2(1536)
        end_time = time.time()

        print(f"✓ IndexFlatL2 created in {end_time - start_time:.3f}s")
        print(f"  Index type: {type(index)}")
        print(f"  Index dimension: {index.d}")
        print(f"  Index count: {index.ntotal}")

        return {
            "status": "success",
            "creation_time": end_time - start_time,
            "index_type": str(type(index)),
            "dimension": index.d
        }

    except Exception as e:
        print(f"❌ No-auth configure failed: {e}")
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def test_faissx_operations():
    """Test actual add/search operations on remote index"""
    print("\n=== Testing FAISSx Remote Operations ===")
    try:
        import faissx.client as faiss
        import numpy as np

        # Configure for remote (should already be done, but let's be explicit)
        faiss.configure(server="tcp://localhost:45678", timeout=5.0)

        print("1. Creating index and adding vectors...")
        index = faiss.IndexFlatL2(1536)

        # Create test vectors
        vectors = np.random.random((5, 1536)).astype(np.float32)
        print(f"   Created {vectors.shape[0]} test vectors of dimension {vectors.shape[1]}")

        # Add vectors to index (this should send data to FAISSx server)
        print("2. Adding vectors to remote index...")
        start_time = time.time()
        index.add(vectors)
        end_time = time.time()

        print(f"✓ Vectors added in {end_time - start_time:.3f}s")
        print(f"  Index count after add: {index.ntotal}")

        # Search the index (this should query the FAISSx server)
        print("3. Searching remote index...")
        query_vector = np.random.random((1, 1536)).astype(np.float32)

        search_start = time.time()
        distances, indices = index.search(query_vector, k=3)
        search_end = time.time()

        print(f"✓ Search completed in {search_end - search_start:.3f}s")
        print(f"  Results found: {len(indices[0])}")
        print(f"  Distances: {distances[0][:3]}")
        print(f"  Indices: {indices[0][:3]}")

        return {
            "status": "success",
            "vectors_added": vectors.shape[0],
            "add_time": end_time - start_time,
            "search_time": search_end - search_start,
            "index_count": index.ntotal,
            "results_found": len(indices[0])
        }

    except Exception as e:
        print(f"❌ Remote operations failed: {e}")
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def test_faissx_local_vs_remote():
    """Compare local vs remote behavior"""
    print("\n=== Comparing Local vs Remote Behavior ===")

    try:
        import faissx.client as faiss
        import numpy as np

        # Test 1: Local mode (reset configuration)
        print("1. Testing LOCAL mode...")
        # Note: There might not be a way to "unconfigure" faissx
        # Let's see what happens if we create indexes without configure

        # Test 2: Remote mode
        print("2. Testing REMOTE mode...")
        faiss.configure(server="tcp://localhost:45678", timeout=5.0)

        remote_index = faiss.IndexFlatL2(128)
        test_vector = np.random.random((1, 128)).astype(np.float32)

        add_start = time.time()
        remote_index.add(test_vector)
        add_end = time.time()

        search_start = time.time()
        distances, indices = remote_index.search(test_vector, k=1)
        search_end = time.time()

        print(f"✓ Remote operations:")
        print(f"  Add time: {add_end - add_start:.3f}s")
        print(f"  Search time: {search_end - search_start:.3f}s")
        print(f"  Index count: {remote_index.ntotal}")

        return {
            "status": "success",
            "remote_add_time": add_end - add_start,
            "remote_search_time": search_end - search_start
        }

    except Exception as e:
        print(f"❌ Comparison test failed: {e}")
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

def main():
    """Run all FAISSx configuration tests"""
    print("🔧 TESTING FAISSx CONFIGURATION AND REMOTE CONNECTION")
    print("=" * 70)
    print("Goal: Determine why remote mode falls back to local FAISS")
    print("Expected: If working, should see activity in FAISSx server logs")

    # Run tests
    import_result = test_faissx_import()
    configure_result = test_faissx_configure_no_auth()
    operations_result = test_faissx_operations()
    comparison_result = test_faissx_local_vs_remote()

    # Summary
    print("\n" + "=" * 70)
    print("🔧 FAISSX CONFIGURATION TEST SUMMARY")
    print("=" * 70)

    print(f"Import Test: {'✅ PASS' if import_result else '❌ FAIL'}")
    print(f"Configure Test: {'✅ PASS' if configure_result.get('status') == 'success' else '❌ FAIL'}")
    if configure_result.get("status") == "success":
        print(f"  - Index creation time: {configure_result.get('creation_time', 0):.3f}s")

    print(f"Operations Test: {'✅ PASS' if operations_result.get('status') == 'success' else '❌ FAIL'}")
    if operations_result.get("status") == "success":
        print(f"  - Vectors added: {operations_result.get('vectors_added')}")
        print(f"  - Add time: {operations_result.get('add_time', 0):.3f}s")
        print(f"  - Search time: {operations_result.get('search_time', 0):.3f}s")
        print(f"  - Index count: {operations_result.get('index_count')}")

    print(f"Comparison Test: {'✅ PASS' if comparison_result.get('status') == 'success' else '❌ FAIL'}")

    # Key insights
    all_passed = all([
        import_result,
        configure_result.get("status") == "success",
        operations_result.get("status") == "success",
        comparison_result.get("status") == "success"
    ])

    print(f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    print(f"\n💡 KEY INSIGHTS:")
    if all_passed:
        print("✅ FAISSx configuration is working")
        print("✅ Remote operations are successful")
        print("🔍 Check FAISSx server logs during this test to confirm remote usage")
        print("❓ If no server logs, there may be a silent fallback mechanism")
    else:
        print("❌ FAISSx configuration has issues")
        print("💡 This explains why WorkingMemory falls back to local FAISS")

    print(f"\n🔍 DEBUGGING STEPS:")
    print("1. Monitor FAISSx server logs at tcp://localhost:45678 during this test")
    print("2. Check if server receives add/search operations")
    print("3. If no activity, investigate faissx client configuration")
    print("4. Consider testing with environment variables instead of configure()")

if __name__ == "__main__":
    main()
