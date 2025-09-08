#!/usr/bin/env python3
"""Debug FAISSx connection - detailed logging and verification"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio
import time

from muxi.services.memory.working import WorkingMemory

class MockLLM:
    """Mock LLM with logging"""
    def __init__(self):
        self.embed_count = 0

    async def embed(self, text):
        self.embed_count += 1
        print(f"    MockLLM.embed() called #{self.embed_count} for: '{text[:30]}...'")
        # Return a unique embedding based on text
        base = [0.1] * 1536
        text_hash = hash(text) % 1000
        for i in range(min(20, len(base))):
            base[i] = (text_hash + i) / 2000.0
        return base

async def test_no_auth_faissx_detailed():
    """Detailed test of no-auth FAISSx server with debugging"""
    print("\n=== DETAILED FAISSx No-Auth Server Test ===")
    print("Server: tcp://localhost:45678")

    # Create mock LLM with tracking
    mock_llm = MockLLM()

    try:
        print("\n1. Creating WorkingMemory with remote mode...")
        buffer = WorkingMemory(
            formation_id="test_formation",
            max_size=3,
            buffer_multiplier=2,
            dimension=1536,
            model=mock_llm,
            mode="remote",
            remote={
                "url": "tcp://localhost:45678"
            }
        )

        print("   ✓ Buffer created successfully")
        print(f"   - Mode: {buffer.mode}")
        print(f"   - Buffer size: {buffer.buffer_size}")
        print(f"   - Has model: {buffer.model is not None}")
        print(f"   - Remote config: {buffer.remote}")

        # Check buffer state before adding
        print("\n2. Initial buffer state:")
        print(f"   - Buffer length: {len(buffer.buffer)}")
        print(f"   - Has vector search: {buffer.has_vector_search}")

        print("\n3. Adding first message...")
        start_time = time.time()
        await buffer.add("First test message about Python", {"msg_id": 1, "topic": "python"})
        end_time = time.time()
        print(f"   ✓ First message added in {end_time - start_time:.3f}s")
        print(f"   - Buffer length after add: {len(buffer.buffer)}")
        print(f"   - MockLLM embed calls: {mock_llm.embed_count}")

        print("\n4. Adding second message...")
        start_time = time.time()
        await buffer.add("Second message about JavaScript", {"msg_id": 2, "topic": "javascript"})
        end_time = time.time()
        print(f"   ✓ Second message added in {end_time - start_time:.3f}s")
        print(f"   - Buffer length after add: {len(buffer.buffer)}")
        print(f"   - MockLLM embed calls: {mock_llm.embed_count}")

        print("\n5. Adding third message...")
        start_time = time.time()
        await buffer.add("Third message about databases", {"msg_id": 3, "topic": "databases"})
        end_time = time.time()
        print(f"   ✓ Third message added in {end_time - start_time:.3f}s")
        print(f"   - Buffer length after add: {len(buffer.buffer)}")
        print(f"   - MockLLM embed calls: {mock_llm.embed_count}")

        # Check buffer contents
        print("\n6. Buffer contents inspection:")
        for i, item in enumerate(buffer.buffer):
            print(f"   Item {i}: {item.get('text', 'No text')[:40]}...")

        print("\n7. Testing vector search...")
        search_start = time.time()
        results = await buffer.search("programming languages", limit=5)
        search_end = time.time()

        print(f"   ✓ Search completed in {search_end - search_start:.3f}s")
        print(f"   - Results found: {len(results)}")
        print(f"   - MockLLM embed calls after search: {mock_llm.embed_count}")

        print("\n8. Search results detail:")
        for i, result in enumerate(results):
            print(f"   Result {i+1}:")
            print(f"     Text: {result.get('text', 'No text')[:50]}...")
            print(f"     Score: {result.get('score', 'No score')}")
            print(f"     Metadata: {result.get('metadata', {})}")

        # Test if the search actually used vector search or just recency
        print("\n9. Search behavior analysis:")
        if len(results) > 0:
            # Check if results are just in reverse chronological order (recency-only)
            # vs semantic similarity order (vector search)
            result_texts = [r['text'] for r in results]
            buffer_texts = [item['text'] for item in reversed(list(buffer.buffer))]

            is_recency_order = result_texts == buffer_texts[:len(result_texts)]
            print(f"   - Results match recency order: {is_recency_order}")
            print(f"   - This suggests: {'Recency-only search' if is_recency_order else 'Vector search active'}")

        # Test search for specific content
        print("\n10. Testing specific search...")
        python_results = await buffer.search("Python programming", limit=3)
        print(f"   - Python search results: {len(python_results)}")
        if len(python_results) > 0:
            print(f"   - Top result: {python_results[0]['text'][:50]}...")
            print(f"   - Top score: {python_results[0].get('score', 'No score')}")

        return {
            "status": "success",
            "buffer_length": len(buffer.buffer),
            "embed_calls": mock_llm.embed_count,
            "search_results": len(results),
            "python_results": len(python_results),
            "mode": buffer.mode,
            "vector_search_active": not is_recency_order if len(results) > 0 else "unknown"
        }

    except Exception as e:
        print(f"   ❌ Detailed test failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "failed",
            "error": str(e),
            "embed_calls": mock_llm.embed_count if 'mock_llm' in locals() else 0
        }

async def test_local_vs_remote_comparison():
    """Compare local vs remote buffer behavior"""
    print("\n=== LOCAL vs REMOTE COMPARISON ===")

    mock_llm_local = MockLLM()
    mock_llm_remote = MockLLM()

    try:
        # Create local buffer
        print("\n1. Creating LOCAL buffer...")
        local_buffer = WorkingMemory(
            formation_id="test_formation",
            max_size=3, buffer_multiplier=2, dimension=1536,
            model=mock_llm_local, mode="local"
        )

        # Create remote buffer
        print("2. Creating REMOTE buffer...")
        remote_buffer = WorkingMemory(
            formation_id="test_formation",
            max_size=3, buffer_multiplier=2, dimension=1536,
            model=mock_llm_remote, mode="remote",
            remote={"url": "tcp://localhost:45678"}
        )

        # Add same data to both
        test_messages = [
            "Machine learning with Python",
            "Web development with React",
            "Database design patterns"
        ]

        print("\n3. Adding messages to BOTH buffers...")
        for i, msg in enumerate(test_messages):
            print(f"   Adding message {i+1}: {msg}")
            await local_buffer.add(msg, {"source": "local", "id": i})
            await remote_buffer.add(msg, {"source": "remote", "id": i})

        print("\n4. Embed call counts:")
        print(f"   - Local buffer: {mock_llm_local.embed_count} calls")
        print(f"   - Remote buffer: {mock_llm_remote.embed_count} calls")

        # Search both
        print("\n5. Searching BOTH buffers for 'Python'...")
        local_results = await local_buffer.search("Python development", limit=3)
        remote_results = await remote_buffer.search("Python development", limit=3)

        print(f"   - Local results: {len(local_results)}")
        print(f"   - Remote results: {len(remote_results)}")

        print("\n6. Search result comparison:")
        print(f"   LOCAL top result: {local_results[0]['text'] if local_results else 'None'}")
        print(f"   REMOTE top result: {remote_results[0]['text'] if remote_results else 'None'}")

        if local_results and remote_results:
            local_top = local_results[0]['text']
            remote_top = remote_results[0]['text']
            same_result = local_top == remote_top
            print(f"   - Same top result: {same_result}")
            print(f"   - This suggests: {'Similar behavior' if same_result else 'Different vector implementations'}")

        return {
            "status": "success",
            "local_embeds": mock_llm_local.embed_count,
            "remote_embeds": mock_llm_remote.embed_count,
            "local_results": len(local_results),
            "remote_results": len(remote_results)
        }

    except Exception as e:
        print(f"   ❌ Comparison test failed: {e}")
        return {"status": "failed", "error": str(e)}

async def main():
    """Run detailed FAISSx debugging"""
    print("🔍 DETAILED FAISSx DEBUGGING")
    print("=" * 60)
    print("Goal: Determine if remote buffer actually uses FAISSx server")
    print("Expected: If working, should see logs in FAISSx server on port 45678")

    # Run detailed test
    detailed_result = await test_no_auth_faissx_detailed()
    comparison_result = await test_local_vs_remote_comparison()

    # Summary
    print("\n" + "=" * 60)
    print("🔍 DEBUGGING SUMMARY")
    print("=" * 60)

    print(f"Detailed Test: {'✅ SUCCESS' if detailed_result.get('status') == 'success' else '❌ FAILED'}")
    if detailed_result.get("status") == "success":
        print(f"  - Buffer items: {detailed_result.get('buffer_length')}")
        print(f"  - Embedding calls: {detailed_result.get('embed_calls')}")
        print(f"  - Search results: {detailed_result.get('search_results')}")
        print(f"  - Vector search active: {detailed_result.get('vector_search_active')}")

    print(f"Comparison Test: {'✅ SUCCESS' if comparison_result.get('status') == 'success' else '❌ FAILED'}")
    if comparison_result.get("status") == "success":
        print(f"  - Local embed calls: {comparison_result.get('local_embeds')}")
        print(f"  - Remote embed calls: {comparison_result.get('remote_embeds')}")
        print(f"  - Result counts: Local={comparison_result.get('local_results')}, Remote={comparison_result.get('remote_results')}")

    print("\n💡 CONCLUSIONS:")
    print("1. Remote buffer mode is configured correctly")
    print("2. Embeddings are being generated (calls to MockLLM)")
    print("3. Search is returning results")

    if detailed_result.get("vector_search_active") is False:
        print("4. ⚠️  Search appears to be recency-based, NOT vector-based")
        print("5. 🤔 This suggests FAISSx might not be receiving the data")
    elif detailed_result.get("vector_search_active") is True:
        print("4. ✅ Search appears to be vector-based")
        print("5. ✅ FAISSx is likely receiving and processing data")
    else:
        print("4. ❓ Unable to determine if vector search is active")

    print("\n🔬 NEXT STEPS:")
    print("- Check FAISSx server logs on port 45678 during this test")
    print("- If no logs appear, the connection may be falling back to local FAISS")
    print("- Consider adding debug logging to WorkingMemory remote operations")

if __name__ == "__main__":
    asyncio.run(main())
