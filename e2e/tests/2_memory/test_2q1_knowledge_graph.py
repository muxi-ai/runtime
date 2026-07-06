#!/usr/bin/env python3
"""Test 2Q1: Knowledge Graph - Memory Revamp Phase 1

This test validates:
1. A conversation turn produces knowledge graph rows (entities + relationships)
   queryable afterwards via the KnowledgeGraphService
2. The kg_entities / kg_relationships tables are created alongside the
   existing schema
3. Existing memory behavior (flat-fact extraction, recall across restart)
   still works in the same run, mirroring the proven 2B1 flow
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest


class TestKnowledgeGraph(BaseMemoryTest):
    """Test knowledge graph extraction alongside flat-fact memory."""

    async def test_knowledge_graph_extraction(self):
        """A conversation turn populates the graph without breaking flat facts."""
        test_name = "2q1_knowledge_graph"
        self.print_test_header(
            test_name, "Test knowledge graph rows from conversation + flat-fact recall"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "kg_test_user"

        try:
            # Start from a fresh database so schema and row assertions are
            # deterministic (the sqlite formation stores memory_test.db in
            # this test's working directory).
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Storing information...")
            await self.setup_memory_formation("sqlite")

            # SQLite runs in single-user mode: every external user id is
            # normalized to "0" before extraction sees it.
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            # Check 1: knowledge graph service is wired into the overlord
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
            if knowledge_graph is not None:
                print("  ✓ Knowledge graph service initialized")
                checks_passed.append("Knowledge graph service initialized")
            else:
                print("  ✗ Knowledge graph service missing from overlord")
                all_passed = False

            # Check 2: kg tables exist in the same database as the rest of the schema
            if knowledge_graph is not None:
                from sqlalchemy import inspect

                tables = inspect(knowledge_graph.db_manager.engine).get_table_names()
                if "kg_entities" in tables and "kg_relationships" in tables:
                    print("  ✓ kg_entities and kg_relationships tables created")
                    checks_passed.append("Knowledge graph tables created")
                else:
                    print(f"  ✗ Knowledge graph tables missing (found: {tables})")
                    all_passed = False

            # Turn 1: unambiguous graph facts (entities + relationships)
            user_msg1 = (
                "My name is Jordan. I founded a company called Automaze " "and I live in London."
            )
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, use_async=False, stream=False
            )
            response1_text = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            # Turn 2: flat-fact-friendly facts (mirrors 2B1's proven recipe)
            user_msg2 = "My favorite color is blue and I have two cats named Whiskers and Shadow."
            response2 = await self.overlord.chat(
                user_msg2, user_id=user_id, use_async=False, stream=False
            )
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append((user_msg2, response2_text))
            print(f"User: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            # Check 3: graph rows appear (extraction is async; poll up to 60s)
            entities, relationships = [], []
            if knowledge_graph is not None:
                for _ in range(12):
                    await asyncio.sleep(5)
                    entities = await knowledge_graph.storage.list_entities(effective_user_id)
                    relationships = await knowledge_graph.storage.list_relationships(
                        effective_user_id
                    )
                    if entities and relationships:
                        break

                entity_names = {e["name"].lower() for e in entities}
                print(f"  Entities: {sorted(entity_names)}")
                print(f"  Relationships: {[r['type'] for r in relationships]}")

                if entities and ("automaze" in entity_names or "london" in entity_names):
                    print("  ✓ Conversation produced knowledge graph entities")
                    checks_passed.append("Graph entities extracted from conversation")
                else:
                    print("  ✗ No expected knowledge graph entities extracted")
                    all_passed = False

                if relationships:
                    print("  ✓ Conversation produced knowledge graph relationships")
                    checks_passed.append("Graph relationships extracted from conversation")
                else:
                    print("  ✗ No knowledge graph relationships extracted")
                    all_passed = False

            # Check 4: graph is queryable (context block rendering)
            if knowledge_graph is not None and relationships:
                context_block = await knowledge_graph.get_context_block(effective_user_id)
                indented = context_block.replace("\n", "\n    ")
                print(f"  Graph context block:\n    {indented}")
                if "-[" in context_block:
                    print("  ✓ Graph context block renders relationship facts")
                    checks_passed.append("Graph queryable via context block")
                else:
                    print("  ✗ Graph context block empty despite stored relationships")
                    all_passed = False

            # Wait for flat-fact extraction to complete (2B1 pattern), then
            # restart the formation to verify persistence + recall.
            await asyncio.sleep(20)
            await self.cleanup()
            print("  ✓ Formation shutdown complete")

            print("\n🔄 Phase 2: Restarting formation...")
            await asyncio.sleep(2)
            await self.setup_memory_formation("sqlite")
            print("  ✓ Formation restarted with SQLite")
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)

            # Check 5: knowledge graph rows persist across restart
            if knowledge_graph is not None:
                persisted_entities = await knowledge_graph.storage.list_entities(effective_user_id)
                if persisted_entities:
                    print("  ✓ Knowledge graph rows persisted across restart")
                    checks_passed.append("Graph rows persisted across restart")
                else:
                    print("  ✗ Knowledge graph rows lost after restart")
                    all_passed = False

            # Check 6: existing flat-fact memory behavior still works
            # (recall after restart, exactly like 2B1)
            recall_msg = "What is my favorite color and what pets do I have?"
            recall_response = await self.overlord.chat(
                recall_msg, user_id=user_id, use_async=False, stream=False
            )
            recall_text = (
                recall_response.content
                if hasattr(recall_response, "content")
                else str(recall_response)
            )
            transcript.append((recall_msg, recall_text))
            print(f"\nUser: {recall_msg}")
            print(f"Assistant: {recall_text[:300]}...")

            recall_lower = recall_text.lower()
            if any(marker in recall_lower for marker in ("blue", "whiskers", "shadow", "cat")):
                print("  ✓ Existing flat-fact recall still works across restart")
                checks_passed.append("Flat-fact recall unaffected")
            else:
                print("  ✗ Flat-fact recall failed after knowledge graph changes")
                all_passed = False

        except Exception as e:
            import traceback

            print(f"  ✗ Test failed with error: {e}")
            traceback.print_exc()
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🕸️ AREA 2Q1: KNOWLEDGE GRAPH (MEMORY REVAMP PHASE 1)")
        print("=" * 60)

        all_passed = await self.test_knowledge_graph_extraction()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Conversation turns populate kg_entities / kg_relationships")
        print("- Graph runs alongside flat-fact extraction, never instead of it")
        print("- Graph rows and flat facts both persist across formation restarts")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestKnowledgeGraph()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
