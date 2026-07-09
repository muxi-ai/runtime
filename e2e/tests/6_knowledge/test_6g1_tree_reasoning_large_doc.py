"""
Test 6G1: Reasoning-RAG Tree Indexing of a Large Document

Verifies Phase 1 of the knowledge-reasoning-rag PRD end to end:
  1. A knowledge file above ``reasoning_threshold`` gets tree-indexed at
     ingestion (tree registry populated, no vector chunks for that file).
  2. A query retrieves the answer via Method A tree navigation (results
     carry source_type "tree" and a node breadcrumb).
  3. The full chat flow answers with a fact buried deep in the document.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_PATH = Path(__file__).parent / "formations" / "formation-tree-reasoning" / "formation.yaml"


async def test_tree_reasoning_large_doc():
    print("\n=== Test 6G1: Reasoning-RAG Tree Indexing of a Large Document ===")
    print("Verifies tree indexing at ingestion and Method A retrieval at query time\n")

    print("Loading formation...")
    formation = Formation()
    await formation.load(str(FORMATION_PATH))
    overlord = await formation.start_overlord()
    print("✓ Formation loaded successfully")

    try:
        # --- Check 1: the large manual is tree-indexed at ingestion ---
        librarian = overlord.agents.get("librarian")
        assert librarian is not None, "librarian agent should exist"
        handler = librarian.knowledge_handler
        assert handler is not None, "knowledge handler should be initialized eagerly"

        tree_paths = list(handler._tree_indexes.keys())
        print(f"\nTree-indexed documents: {tree_paths}")
        assert any("starship-manual.md" in p for p in tree_paths), \
            "starship-manual.md (above threshold) should be tree-indexed"

        tree = next(t for p, t in handler._tree_indexes.items() if "starship-manual.md" in p)
        print(f"✓ Tree index: {tree.node_count} nodes, "
              f"{tree.token_count} doc tokens, {tree.tree_token_count} tree tokens")
        assert tree.node_count > 5, "manual should produce a multi-node tree"
        assert tree.tree_token_count < tree.token_count, \
            "compressed tree must be much smaller than the document"

        # The tree-indexed manual must NOT have vector chunks (no double indexing)
        manual_chunks = handler.working_memory.get_items_by_metadata(
            metadata_filter={}, namespace="knowledge"
        )
        manual_vector_chunks = [
            c for c in manual_chunks
            if "starship-manual" in str(c.get("metadata", {}).get("source", ""))
        ]
        assert not manual_vector_chunks, \
            "tree-indexed manual must not also be vector-embedded"
        print("✓ Manual has no vector chunks (tree-only indexing confirmed)")

        # --- Check 2: direct search retrieves via tree navigation ---
        print("\n--- Direct knowledge search (Method A navigation) ---")
        results = await handler.search("How often must the warp coil be recalibrated?")
        assert results, "knowledge search should return results"
        tree_results = [r for r in results if r["metadata"].get("source_type") == "tree"]
        print(f"✓ Search returned {len(results)} results ({len(tree_results)} via tree)")
        assert tree_results, "at least one result should come from tree navigation"
        top = tree_results[0]
        print(f"  Top tree node: {top['metadata'].get('node_id')} "
              f"path={top['metadata'].get('node_path')}")
        assert top["metadata"].get("retrieval_method") == "tree_a"
        assert isinstance(top["metadata"].get("node_path"), list)
        combined = " ".join(r["content"] for r in tree_results)
        assert "47 days" in combined, \
            f"tree navigation should fetch the recalibration section, got: {combined[:300]}"
        print("✓ Tree navigation fetched the correct section (47 days)")

        # --- Check 3: full chat flow answers with the buried fact ---
        print("\n--- Chat flow ---")
        print("👤 User: How often must the warp coil be recalibrated?")
        response = await overlord.chat(
            message="According to the operations manual, how often must the warp coil "
                    "be recalibrated?",
            user_id="test_user_6g1",
            session_id="test_6g1_session",
            stream=False,
        )
        response_text = response.content if hasattr(response, "content") else str(response)
        print(f"\n🤖 Overlord: {response_text}")
        assert "47" in response_text, \
            "response should quote the 47-day recalibration interval from the manual"
        print("✓ Chat answer grounded in the tree-indexed manual")

    finally:
        await formation.stop_overlord()

    print("\n=== Test 6G1 Summary ===")
    print("✓ Large document tree-indexed at ingestion (no vector double-indexing)")
    print("✓ Method A navigation retrieved the correct node")
    print("✓ Chat flow answered with the buried fact")
    print("\n✅ Test 6G1 PASSED: Reasoning-RAG tree retrieval working correctly")
    return True


if __name__ == "__main__":
    import os
    try:
        success = asyncio.run(test_tree_reasoning_large_doc())
        if success:
            print("SUCCESS", flush=True)
        os._exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)
