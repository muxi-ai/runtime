"""
Test 6H2: Reasoning-RAG Hybrid Retrieval + Agent-Level Tree

Verifies Phases 3-4 of the knowledge-reasoning-rag PRD end to end:
  1. A source declaring ``retrieval: hybrid`` with an ``agent_tree`` block
     builds a persistent agent-level tree in <formation>/.knowledge-trees/
     (tree + kv + embeddings + meta.json) at formation load.
  2. A query runs the parallel A+B hybrid path: results carry hybrid cost
     metadata (llm_calls / evaluator_rounds) and source_type "agent_tree".
  3. The full chat flow answers with a fact buried deep in the handbook.
  4. A second formation load with unchanged content reuses the persisted
     tree (on-source-change trigger, no rebuild).
"""
import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, '../../..')

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-tree-hybrid"
FORMATION_PATH = FORMATION_DIR / "formation.yaml"
TREES_DIR = FORMATION_DIR / ".knowledge-trees"


async def test_hybrid_retrieval():
    print("\n=== Test 6H2: Reasoning-RAG Hybrid Retrieval + Agent-Level Tree ===")
    print("Verifies parallel A+B, sufficiency evaluation, and tree persistence\n")

    # Start clean so the first load provably builds the agent tree
    shutil.rmtree(TREES_DIR, ignore_errors=True)

    print("Loading formation (first load - builds the agent tree)...")
    formation = Formation()
    await formation.load(str(FORMATION_PATH))
    overlord = await formation.start_overlord()
    print("✓ Formation loaded successfully")

    try:
        # --- Check 1: agent-level tree persisted in the formation dir ---
        librarian = overlord.agents.get("librarian")
        assert librarian is not None, "librarian agent should exist"
        handler = librarian.knowledge_handler
        assert handler is not None, "knowledge handler should be initialized eagerly"

        handbook_path = next(
            (p for p in handler._tree_indexes if "colony-handbook.md" in p), None
        )
        assert handbook_path, "colony-handbook.md should be tree-indexed"
        assert handler._tree_modes.get(handbook_path) == "hybrid"
        tree = handler._tree_indexes[handbook_path]
        assert tree.scope == "agent", "handbook should be an agent-level tree"
        assert tree.chunk_embeddings, "hybrid tree must carry Method B embeddings"
        print(f"✓ Agent tree: {tree.node_count} nodes, scope={tree.scope}")

        persisted = sorted(p.name for p in TREES_DIR.iterdir())
        print(f"✓ Persisted files: {persisted}")
        for suffix in (".json", ".kv.jsonl", ".emb.jsonl", ".meta.json"):
            assert any(name.endswith(suffix) for name in persisted), \
                f"expected a {suffix} file in .knowledge-trees/"

        # --- Check 2: hybrid search with cost metadata ---
        print("\n--- Direct knowledge search (hybrid A+B + sufficiency) ---")
        results = await handler.search(
            "When does Tier-2 water rationing begin and what is the household limit?"
        )
        assert results, "knowledge search should return results"
        hybrid_results = [r for r in results if r["metadata"].get("hybrid")]
        print(f"✓ Search returned {len(results)} results ({len(hybrid_results)} via hybrid)")
        assert hybrid_results, "at least one result should come from the hybrid path"
        top = hybrid_results[0]
        cost = top["metadata"].get("cost") or {}
        print(f"  Top node: {top['metadata'].get('node_id')} "
              f"source_type={top['metadata'].get('source_type')} cost={cost}")
        assert top["metadata"].get("source_type") == "agent_tree"
        assert cost.get("llm_calls", 0) >= 1, "hybrid cost metadata should count LLM calls"
        combined = " ".join(r["content"] for r in hybrid_results)
        assert "40 percent" in combined and "85 liters" in combined, \
            f"hybrid retrieval should fetch the rationing section, got: {combined[:300]}"
        print("✓ Hybrid retrieval fetched the rationing rules (40 percent / 85 liters)")

        # --- Check 3: full chat flow answers with the buried fact ---
        # Phrased as one simple factual question (like 6G1/6H1): multi-part
        # "retrieve X and Y" phrasing makes the planner decompose and
        # delegate to the knowledge-less generalist instead of answering
        # directly from the injected context.
        print("\n--- Chat flow ---")
        print("👤 User: How many liters per day under Tier-2 rationing?")
        response = await overlord.chat(
            message="According to the colony operations handbook, how many liters of "
                    "water per day may a household use under Tier-2 rationing?",
            user_id="test_user_6h2",
            session_id="test_6h2_session",
            stream=False,
        )
        response_text = response.content if hasattr(response, "content") else str(response)
        print(f"\n🤖 Overlord: {response_text}")
        assert "85" in response_text, \
            "response should quote the 85 liter household limit from the handbook"
        print("✓ Chat answer grounded in the hybrid agent tree")

    finally:
        await formation.stop_overlord()

    # --- Check 4: unchanged source -> persisted tree reused on reload ---
    print("\n--- Second load (on-source-change: unchanged content, no rebuild) ---")
    meta_file = next(TREES_DIR.glob("*.meta.json"))
    first_meta = meta_file.read_text()

    formation2 = Formation()
    await formation2.load(str(FORMATION_PATH))
    overlord2 = await formation2.start_overlord()
    try:
        handler2 = overlord2.agents["librarian"].knowledge_handler
        handbook_path2 = next(
            (p for p in handler2._tree_indexes if "colony-handbook.md" in p), None
        )
        assert handbook_path2, "reloaded formation should serve the persisted agent tree"
        assert handler2._tree_indexes[handbook_path2].scope == "agent"
        second_meta = meta_file.read_text()
        assert first_meta == second_meta, \
            "unchanged source must not rebuild (meta.json must be untouched)"
        print("✓ Persisted agent tree reused without rebuild (meta.json unchanged)")
    finally:
        await formation2.stop_overlord()
        # Leave the repo clean: the persisted tree is a test artifact here
        shutil.rmtree(TREES_DIR, ignore_errors=True)

    print("\n=== Test 6H2 Summary ===")
    print("✓ Agent-level tree built and persisted (.knowledge-trees/ + meta.json)")
    print("✓ Hybrid A+B retrieval served with cost metadata")
    print("✓ Chat flow answered with the buried fact")
    print("✓ Unchanged source reused the persisted tree on reload")
    print("\n✅ Test 6H2 PASSED: Hybrid retrieval + agent trees working correctly")
    return True


if __name__ == "__main__":
    import os
    try:
        success = asyncio.run(test_hybrid_retrieval())
        if success:
            print("SUCCESS", flush=True)
        os._exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        os._exit(1)
