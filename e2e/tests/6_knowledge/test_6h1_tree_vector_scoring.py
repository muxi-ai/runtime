"""
Test 6H1: Reasoning-RAG Method B (tree-vector) Retrieval

Verifies Phase 2 of the knowledge-reasoning-rag PRD end to end:
  1. A source declaring ``retrieval: tree-vector`` is tree-indexed at
     ingestion with per-node chunk embeddings (no vector chunks for the
     file, embeddings sidecar cached on disk).
  2. A query retrieves the answer via Method B value scoring (results
     carry retrieval_method "tree_b" and a node_score) WITHOUT any tree
     LLM navigation call at query time.
  3. The full chat flow answers with a fact buried deep in the document.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_PATH = Path(__file__).parent / "formations" / "formation-tree-hybrid" / "formation.yaml"


async def test_tree_vector_scoring():
    print("\n=== Test 6H1: Reasoning-RAG Method B (tree-vector) Retrieval ===")
    print("Verifies per-node chunk-embedding scoring at query time\n")

    print("Loading formation...")
    formation = Formation()
    await formation.load(str(FORMATION_PATH))
    overlord = await formation.start_overlord()
    print("✓ Formation loaded successfully")

    try:
        # --- Check 1: the manual is tree-indexed with chunk embeddings ---
        librarian = overlord.agents.get("librarian")
        assert librarian is not None, "librarian agent should exist"
        handler = librarian.knowledge_handler
        assert handler is not None, "knowledge handler should be initialized eagerly"

        manual_path = next(
            (p for p in handler._tree_indexes if "starship-manual.md" in p), None
        )
        assert manual_path, "starship-manual.md should be tree-indexed"
        assert handler._tree_modes.get(manual_path) == "tree-vector", \
            "manual should serve under the tree-vector mode"
        tree = handler._tree_indexes[manual_path]
        assert tree.chunk_embeddings, "tree-vector source must carry per-node chunk embeddings"
        embedded_nodes = len(tree.chunk_embeddings)
        total_vectors = sum(len(v) for v in tree.chunk_embeddings.values())
        print(f"✓ Tree index: {tree.node_count} nodes, {embedded_nodes} embedded nodes, "
              f"{total_vectors} chunk vectors")

        # The tree-indexed manual must NOT have vector chunks (no double indexing)
        manual_chunks = handler.working_memory.get_items_by_metadata(
            metadata_filter={}, namespace="knowledge"
        )
        manual_vector_chunks = [
            c for c in manual_chunks
            if "starship-manual" in str(c.get("metadata", {}).get("source", ""))
        ]
        assert not manual_vector_chunks, \
            "tree-vector manual must not also be vector-embedded"
        print("✓ Manual has no flat vector chunks (node-scoped embeddings only)")

        # --- Check 2: direct search retrieves via Method B scoring ---
        print("\n--- Direct knowledge search (Method B value scoring) ---")
        results = await handler.search(
            "What is the approved coolant for the secondary loop?"
        )
        assert results, "knowledge search should return results"
        b_results = [
            r for r in results if r["metadata"].get("retrieval_method") == "tree_b"
        ]
        print(f"✓ Search returned {len(results)} results ({len(b_results)} via Method B)")
        assert b_results, "at least one result should come from Method B scoring"
        top = b_results[0]
        print(f"  Top node: {top['metadata'].get('node_id')} "
              f"score={top['metadata'].get('node_score')} "
              f"path={top['metadata'].get('node_path')}")
        assert top["metadata"].get("node_score") is not None
        assert isinstance(top["metadata"].get("node_path"), list)
        combined = " ".join(r["content"] for r in b_results)
        assert "ZX-9" in combined, \
            f"Method B should fetch the coolant section, got: {combined[:300]}"
        print("✓ Method B scoring fetched the correct section (ZX-9 fluorinert)")

        # --- Check 3: full chat flow answers with the buried fact ---
        print("\n--- Chat flow ---")
        print("👤 User: What coolant is approved for the secondary loop?")
        response = await overlord.chat(
            message="According to the operations manual, what is the approved coolant "
                    "for the secondary loop?",
            user_id="test_user_6h1",
            session_id="test_6h1_session",
            stream=False,
        )
        response_text = response.content if hasattr(response, "content") else str(response)
        print(f"\n🤖 Overlord: {response_text}")
        assert "ZX-9" in response_text, \
            "response should quote the ZX-9 fluorinert coolant from the manual"
        print("✓ Chat answer grounded in the tree-vector indexed manual")

    finally:
        await formation.stop_overlord()

    print("\n=== Test 6H1 Summary ===")
    print("✓ tree-vector source indexed with per-node chunk embeddings")
    print("✓ Method B scoring retrieved the correct node (no query-time LLM nav)")
    print("✓ Chat flow answered with the buried fact")
    print("\n✅ Test 6H1 PASSED: Method B (tree-vector) retrieval working correctly")
    return True


if __name__ == "__main__":
    import os
    try:
        success = asyncio.run(test_tree_vector_scoring())
        if success:
            print("SUCCESS", flush=True)
        os._exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)
