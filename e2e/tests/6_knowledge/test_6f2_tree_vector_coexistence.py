"""
Test 6F2: Tree and Vector Sources Coexist in One Agent's Knowledge Base

Verifies the coexistence requirement of the knowledge-reasoning-rag PRD:
one agent declares a large document (tree-indexed via the token threshold)
and a small document (vector-indexed, under threshold). Both retrieval
paths must serve queries in the same knowledge base:
  1. Ingestion: exactly the large file is tree-indexed; the small file has
     vector chunks.
  2. A question against the small FAQ is answered from the vector path.
  3. A question against the large manual is answered from the tree path.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_PATH = Path(__file__).parent / "formations" / "formation-tree-reasoning" / "formation.yaml"


async def test_tree_vector_coexistence():
    print("\n=== Test 6F2: Tree + Vector Coexistence in One Agent ===")
    print("One agent, two sources: large manual (tree) + small FAQ (vector)\n")

    print("Loading formation...")
    formation = Formation()
    await formation.load(str(FORMATION_PATH))
    overlord = await formation.start_overlord()
    print("✓ Formation loaded successfully")

    try:
        librarian = overlord.agents.get("librarian")
        handler = librarian.knowledge_handler
        assert handler is not None

        # --- Check 1: exactly the large file is tree-indexed ---
        tree_paths = list(handler._tree_indexes.keys())
        print(f"Tree-indexed documents: {tree_paths}")
        assert any("starship-manual.md" in p for p in tree_paths), \
            "large manual should be tree-indexed"
        assert not any("fleet-faq.md" in p for p in tree_paths), \
            "small FAQ (under threshold) must stay on the vector path"

        vector_chunks = handler.working_memory.get_items_by_metadata(
            metadata_filter={}, namespace="knowledge"
        )
        faq_chunks = [
            c for c in vector_chunks
            if "fleet-faq" in str(c.get("metadata", {}).get("source", ""))
        ]
        assert faq_chunks, "small FAQ should have vector chunks"
        print(f"✓ FAQ vector chunks: {len(faq_chunks)}; manual tree nodes: "
              f"{next(iter(handler._tree_indexes.values())).node_count}")

        # --- Check 2: vector-backed question (small FAQ) ---
        print("\n--- Vector question ---")
        print("👤 User: What are the fleet support desk hours?")
        response1 = await overlord.chat(
            message="What are the fleet support desk hours according to the FAQ?",
            user_id="test_user_6f2",
            session_id="test_6f2_session_1",
            stream=False,
        )
        text1 = response1.content if hasattr(response1, "content") else str(response1)
        print(f"\n🤖 Overlord: {text1}")
        assert ("09:00" in text1 or "9:00" in text1 or "0900" in text1), \
            "response should quote the FAQ support hours (09:00 to 17:00 UTC)"
        print("✓ Vector-indexed FAQ answered correctly")

        # --- Check 3: tree-backed question (large manual) ---
        print("\n--- Tree question ---")
        print("👤 User: What coolant is approved for the secondary loop?")
        response2 = await overlord.chat(
            message="Per the operations manual, what coolant is approved for the "
                    "secondary loop?",
            user_id="test_user_6f2",
            session_id="test_6f2_session_2",
            stream=False,
        )
        text2 = response2.content if hasattr(response2, "content") else str(response2)
        print(f"\n🤖 Overlord: {text2}")
        assert "ZX-9" in text2, \
            "response should quote the ZX-9 coolant fact from the tree-indexed manual"
        print("✓ Tree-indexed manual answered correctly")

    finally:
        await formation.stop_overlord()

    print("\n=== Test 6F2 Summary ===")
    print("✓ Large manual tree-indexed, small FAQ vector-indexed (same agent)")
    print("✓ Vector question answered from FAQ")
    print("✓ Tree question answered from manual")
    print("\n✅ Test 6F2 PASSED: Tree and vector sources coexist correctly")
    return True


if __name__ == "__main__":
    import os
    try:
        success = asyncio.run(test_tree_vector_coexistence())
        if success:
            print("SUCCESS", flush=True)
        os._exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)
