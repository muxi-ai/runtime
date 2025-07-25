#!/usr/bin/env python3
"""Verify that we actually READ data back from FAISSx"""

import sys
sys.path.insert(0, '.')
import time
import numpy as np

def test_faissx_read_write_cycle():
    """Test complete write-then-read cycle to verify data retrieval"""
    print("=== Testing FAISSx Read/Write Cycle ===")

    try:
        import faissx.client as faiss

        # Configure remote
        faiss.configure(server="tcp://localhost:45678", timeout=5.0)

        print("1. Creating fresh index...")
        index = faiss.IndexFlatL2(128)  # Smaller dimension for easier verification
        print(f"   Initial index count: {index.ntotal}")

        # Create distinctive test vectors that we can verify
        print("2. Creating distinctive test vectors...")
        test_vectors = np.array([
            [1.0] + [0.0] * 127,  # Vector 1: [1,0,0,0,...]
            [0.0, 1.0] + [0.0] * 126,  # Vector 2: [0,1,0,0,...]
            [0.0, 0.0, 1.0] + [0.0] * 125,  # Vector 3: [0,0,1,0,...]
        ], dtype=np.float32)

        print(f"   Created {len(test_vectors)} distinctive vectors")
        print(f"   Vector shapes: {test_vectors.shape}")

        # Add vectors to remote index
        print("3. Adding vectors to remote FAISSx...")
        add_start = time.time()
        index.add(test_vectors)
        add_end = time.time()

        print(f"✓ Vectors added in {add_end - add_start:.3f}s")
        print(f"   Index count after add: {index.ntotal}")

        # Now search with a query that should match the first vector
        print("4. Searching for first vector [1,0,0,0,...]...")
        query = np.array([[1.0] + [0.0] * 127], dtype=np.float32)

        search_start = time.time()
        distances, indices = index.search(query, k=3)
        search_end = time.time()

        print(f"✓ Search completed in {search_end - search_start:.3f}s")
        print(f"   Distances: {distances[0]}")
        print(f"   Indices: {indices[0]}")

        # Verify we got back meaningful results
        expected_best_match = 0  # Should be index 0 (first vector)
        got_best_match = indices[0][0] if len(indices[0]) > 0 else -1
        best_distance = distances[0][0] if len(distances[0]) > 0 else float('inf')

        print(f"5. Verifying results...")
        print(f"   Expected best match index: {expected_best_match}")
        print(f"   Got best match index: {got_best_match}")
        print(f"   Best match distance: {best_distance}")
        print(f"   Perfect match (distance=0): {abs(best_distance) < 1e-6}")

        # Test searching for second vector
        print("6. Searching for second vector [0,1,0,0,...]...")
        query2 = np.array([[0.0, 1.0] + [0.0] * 126], dtype=np.float32)
        distances2, indices2 = index.search(query2, k=3)

        expected_match_2 = 1
        got_match_2 = indices2[0][0] if len(indices2[0]) > 0 else -1
        distance_2 = distances2[0][0] if len(distances2[0]) > 0 else float('inf')

        print(f"   Expected match: {expected_match_2}, Got: {got_match_2}")
        print(f"   Distance: {distance_2}")
        print(f"   Perfect match: {abs(distance_2) < 1e-6}")

        return {
            "status": "success",
            "vectors_added": len(test_vectors),
            "index_count": index.ntotal,
            "first_search_correct": got_best_match == expected_best_match,
            "first_search_perfect": abs(best_distance) < 1e-6,
            "second_search_correct": got_match_2 == expected_match_2,
            "second_search_perfect": abs(distance_2) < 1e-6,
            "add_time": add_end - add_start,
            "search_time": search_end - search_start
        }

    except Exception as e:
        print(f"❌ Read/write cycle failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def test_workingemory_read_verification():
    """Test that WorkingMemory actually reads back correct data"""
    print("\n=== Testing WorkingMemory Read Verification ===")

    try:
        # Mock LLM that returns predictable embeddings
        class PredictableLLM:
            def __init__(self):
                self.call_count = 0

            async def embed(self, text):
                self.call_count += 1
                # Return different embeddings based on text content
                if "python" in text.lower():
                    return [1.0] + [0.0] * 1535  # Python = [1,0,0,...]
                elif "javascript" in text.lower():
                    return [0.0, 1.0] + [0.0] * 1534  # JS = [0,1,0,...]
                elif "rust" in text.lower():
                    return [0.0, 0.0, 1.0] + [0.0] * 1533  # Rust = [0,0,1,...]
                else:
                    return [0.5] * 1536  # Default

        from src.muxi.services.memory.working import WorkingMemory

        print("1. Creating WorkingMemory with predictable embeddings...")
        predictable_llm = PredictableLLM()
        buffer = WorkingMemory(
            formation_id="test_formation",
            max_size=5,
            buffer_multiplier=2,
            dimension=1536,
            model=predictable_llm,
            mode="remote",
            remote={"url": "tcp://localhost:45678"}
        )

        # Add distinctive messages
        print("2. Adding distinctive messages...")
        await buffer.add("I love Python programming", {"topic": "python"})
        await buffer.add("JavaScript is great for web dev", {"topic": "javascript"})
        await buffer.add("Rust is fast and safe", {"topic": "rust"})

        print(f"   Added 3 messages, LLM called {predictable_llm.call_count} times")

        # Search for Python - should return the Python message
        print("3. Searching for 'Python'...")
        python_results = await buffer.search("Python programming", limit=3)

        print(f"   Found {len(python_results)} results")
        if len(python_results) > 0:
            top_result = python_results[0]
            print(f"   Top result: {top_result['text'][:50]}...")
            print(f"   Score: {top_result.get('score', 'No score')}")
            print(f"   Metadata: {top_result.get('metadata', {})}")

            # Check if we got the right result
            python_match = "python" in top_result['text'].lower()
            print(f"   Correct match: {python_match}")

        # Search for JavaScript
        print("4. Searching for 'JavaScript'...")
        js_results = await buffer.search("JavaScript web development", limit=3)

        if len(js_results) > 0:
            top_js = js_results[0]
            print(f"   Top result: {top_js['text'][:50]}...")
            js_match = "javascript" in top_js['text'].lower()
            print(f"   Correct match: {js_match}")

        return {
            "status": "success",
            "llm_calls": predictable_llm.call_count,
            "python_results": len(python_results),
            "js_results": len(js_results),
            "python_correct": python_match if 'python_match' in locals() else False,
            "js_correct": js_match if 'js_match' in locals() else False
        }

    except Exception as e:
        print(f"❌ WorkingMemory read test failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}

async def main():
    """Run read verification tests"""
    print("📖 TESTING FAISSx READ OPERATIONS")
    print("=" * 50)
    print("Goal: Verify we actually read data back from FAISSx")

    # Test direct FAISSx read/write
    cycle_result = test_faissx_read_write_cycle()

    # Test WorkingMemory read capability
    workingemory_result = await test_workingemory_read_verification()

    # Summary
    print("\n" + "=" * 50)
    print("📖 READ VERIFICATION SUMMARY")
    print("=" * 50)

    print(f"Direct FAISSx Read/Write: {'✅ PASS' if cycle_result.get('status') == 'success' else '❌ FAIL'}")
    if cycle_result.get("status") == "success":
        print(f"  - Vectors added: {cycle_result.get('vectors_added')}")
        print(f"  - Index count: {cycle_result.get('index_count')}")
        print(f"  - First search correct: {cycle_result.get('first_search_correct')}")
        print(f"  - First search perfect match: {cycle_result.get('first_search_perfect')}")
        print(f"  - Second search correct: {cycle_result.get('second_search_correct')}")
        print(f"  - Second search perfect match: {cycle_result.get('second_search_perfect')}")

    print(f"WorkingMemory Read: {'✅ PASS' if workingemory_result.get('status') == 'success' else '❌ FAIL'}")
    if workingemory_result.get("status") == "success":
        print(f"  - LLM embed calls: {workingemory_result.get('llm_calls')}")
        print(f"  - Python search results: {workingemory_result.get('python_results')}")
        print(f"  - JS search results: {workingemory_result.get('js_results')}")
        print(f"  - Python search correct: {workingemory_result.get('python_correct')}")
        print(f"  - JS search correct: {workingemory_result.get('js_correct')}")

    # Final conclusion
    both_working = (
        cycle_result.get("status") == "success" and
        workingemory_result.get("status") == "success"
    )

    reads_working = (
        cycle_result.get("first_search_correct", False) and
        cycle_result.get("second_search_correct", False) and
        workingemory_result.get("python_correct", False)
    )

    print(f"\n🎯 FINAL VERDICT:")
    if both_working and reads_working:
        print("✅ FAISSx READ OPERATIONS CONFIRMED!")
        print("✅ We successfully write TO and read FROM remote FAISSx")
        print("✅ WorkingMemory retrieves correct data via vector similarity")
        print("✅ Complete bidirectional remote memory operations working")
    elif both_working:
        print("⚠️  FAISSx operations work but read verification needs investigation")
    else:
        print("❌ FAISSx read operations have issues")

    print(f"\n📊 During this test, check FAISSx logs for:")
    print("- Index creation messages")
    print("- add_vectors requests")
    print("- search requests")
    print("- Successful response confirmations")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
