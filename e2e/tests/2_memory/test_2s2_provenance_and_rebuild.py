#!/usr/bin/env python3
"""Test 2S2: Memory Provenance, GDPR Forgetting, and Legacy Backfill

Memory Event Substrate Phases 2b-2d, exercised on a real conversation:
1. A conversation produces knowledge graph facts whose provenance chains
   resolve back to the interaction.turn events that caused them
   ("why do you think X?")
2. Rebuild-from-events reproduces the prior projections (wipe-and-replay
   equality on the knowledge graph after real chat traffic)
3. GDPR selective forgetting: soft-deleting an imported source's events
   and rebuilding removes exactly that source's derived facts while
   conversation-derived facts survive
4. Legacy backfill: a pre-event-log row (direct write, no provenance)
   gets a synthetic legacy event and becomes replayable
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest  # noqa: E402


async def snapshot_graph(knowledge_graph, user_id):
    """Structural knowledge-graph state keyed by entity names."""
    entities = await knowledge_graph.storage.list_entities(user_id, status=None, limit=1000)
    names = {e["id"]: (e["type"], e["name"]) for e in entities}
    relationships = await knowledge_graph.storage.list_relationships(
        user_id, status=None, limit=1000
    )
    return (
        {names[e["id"]]: (e["confidence"], e["status"]) for e in entities},
        {
            (names[r["from_entity_id"]], r["type"], names[r["to_entity_id"]]): (
                r["confidence"],
                r["status"],
            )
            for r in relationships
        },
    )


class TestMemoryProvenanceAndRebuild(BaseMemoryTest):
    """Provenance chains, GDPR forgetting, and legacy backfill end to end."""

    async def test_provenance_and_rebuild(self):
        test_name = "2s2_provenance_and_rebuild"
        self.print_test_header(
            test_name, "Test provenance chains, GDPR forgetting, and legacy backfill"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "provenance_test_user"

        try:
            # Fresh database for deterministic assertions.
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Conversation producing graph facts...")
            await self.setup_memory_formation("sqlite")
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            memory_events = getattr(self.overlord, "memory_events", None)
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
            if memory_events is None or knowledge_graph is None:
                print("  ✗ Memory event substrate or knowledge graph missing")
                raise RuntimeError("substrate not wired")

            user_msg = (
                "My name is Jordan and I live in London. I founded a company "
                "called Automaze and we are building the MUXI project."
            )
            response = await self.overlord.chat(
                user_msg, user_id=user_id, use_async=False, stream=False
            )
            response_text = response.content if hasattr(response, "content") else str(response)
            transcript.append((user_msg, response_text))
            print(f"User: {user_msg}")
            print(f"Assistant: {response_text[:200]}...")

            # Extraction is fire-and-forget; wait for graph events to land.
            graph_events = []
            for _ in range(12):
                await asyncio.sleep(5)
                graph_events = await memory_events.list_events(
                    effective_user_id, event_types=["graph.extracted"]
                )
                if graph_events:
                    break

            if graph_events:
                print(f"  ✓ Conversation produced {len(graph_events)} graph.extracted event(s)")
                checks_passed.append("Graph extraction events recorded")
            else:
                print("  ✗ No graph.extracted events recorded")
                all_passed = False

            # Check 1: provenance query on a real conversation entity.
            print("\n🔎 Phase 2: Provenance query ('why do you think X?')...")
            from muxi.runtime.services.memory.events.provenance import entity_provenance

            entities = await knowledge_graph.storage.list_entities(effective_user_id, limit=100)
            target = next(
                (e for e in entities if e["name"].lower() != "user"),
                entities[0] if entities else None,
            )
            provenance = None
            if target is not None:
                provenance = await entity_provenance(
                    memory_events,
                    knowledge_graph,
                    effective_user_id,
                    target["name"],
                    decay=memory_events.decay,
                )
            if provenance is not None and provenance["entity"]["events"]:
                print(
                    f"  ✓ Entity '{target['name']}' resolves to "
                    f"{len(provenance['entity']['events'])} event chain(s)"
                )
                checks_passed.append("Entity provenance resolves to events")
            else:
                print(f"  ✗ No provenance for entity {target}")
                all_passed = False

            chain_ok = False
            if provenance is not None:
                for chains in [provenance["entity"]["events"]] + [
                    fact["events"] for fact in provenance["facts"]
                ]:
                    for chain in chains:
                        types = [event["event_type"] for event in chain]
                        if types[0] == "interaction.turn" and types[-1] == "graph.extracted":
                            chain_ok = True
                            print(f"  ✓ Causation chain root-first: {' -> '.join(types)}")
                            break
                    if chain_ok:
                        break
            if chain_ok:
                checks_passed.append("Chain traces fact to its interaction turn")
            else:
                print("  ✗ No chain traced back to an interaction.turn event")
                all_passed = False

            # Check 2: rebuild-from-events reproduces the projections.
            print("\n🔄 Phase 3: Rebuild reproduces prior projections...")
            before = await snapshot_graph(knowledge_graph, effective_user_id)
            report = await memory_events.rebuild(effective_user_id, projection="knowledge_graph")
            after = await snapshot_graph(knowledge_graph, effective_user_id)
            if report["knowledge_graph"]["failed"] == 0 and after == before:
                print(
                    f"  ✓ Rebuild replayed {report['knowledge_graph']['applied']} events "
                    "into an identical graph"
                )
                checks_passed.append("Rebuild reproduces prior projections")
            else:
                print(f"  ✗ Rebuild diverged: {report}\n    {before}\n    {after}")
                all_passed = False

            # Check 3: GDPR selective forgetting of an imported source.
            print("\n🗑  Phase 4: GDPR forgetting of an imported source...")
            await knowledge_graph.store_extraction(
                effective_user_id,
                {
                    "entities": [{"name": "MailCorp", "type": "company", "confidence": 0.9}],
                    "relationships": [],
                },
                source="gmail",
            )
            stored = await knowledge_graph.storage.get_entity(
                effective_user_id, "company", "MailCorp"
            )
            if stored is not None:
                checks_passed.append("Imported source fact stored")
            else:
                print("  ✗ Imported fact did not store")
                all_passed = False

            forget = await memory_events.forget_source(effective_user_id, "gmail", reason="gdpr")
            await memory_events.rebuild(effective_user_id, projection="knowledge_graph")
            gone = await knowledge_graph.storage.get_entity(
                effective_user_id, "company", "MailCorp"
            )
            survivors = await knowledge_graph.storage.list_entities(effective_user_id, limit=100)
            audit = await memory_events.list_events(
                effective_user_id, event_types=["user.deletion"]
            )
            if forget["deleted_events"] >= 1 and gone is None and survivors and audit:
                print(
                    f"  ✓ Forgot {forget['deleted_events']} gmail event(s); rebuild removed "
                    f"the derived fact; {len(survivors)} conversation facts survive; "
                    "audit event recorded"
                )
                checks_passed.append("GDPR forget + rebuild removes derived state")
            else:
                print(
                    f"  ✗ Forgetting failed (deleted={forget['deleted_events']}, "
                    f"gone={gone is None}, survivors={len(survivors)}, audit={len(audit)})"
                )
                all_passed = False

            # Check 4: legacy backfill makes a pre-event-log row replayable.
            print("\n🧱 Phase 5: Legacy backfill (synthetic events)...")
            legacy_row = await knowledge_graph.storage.upsert_entity(
                effective_user_id, "company", "LegacyCorp", confidence=0.8
            )
            if not legacy_row["derived_from_event_ids"]:
                checks_passed.append("Legacy row created without provenance")
            backfill_report = await memory_events.backfill_user(effective_user_id)
            stamped = await knowledge_graph.storage.get_entity(
                effective_user_id, "company", "LegacyCorp"
            )
            legacy_events = await memory_events.list_events(effective_user_id, source="legacy")
            if (
                backfill_report.get("knowledge_graph", 0) >= 1
                and stamped["derived_from_event_ids"]
                and legacy_events
            ):
                print(
                    f"  ✓ Backfill synthesized {backfill_report['knowledge_graph']} legacy "
                    "event(s) and stamped provenance in place"
                )
                checks_passed.append("Backfill synthesizes legacy events")
            else:
                print(f"  ✗ Backfill failed: {backfill_report}, row={stamped}")
                all_passed = False

            await memory_events.rebuild(effective_user_id, projection="knowledge_graph")
            replayed = await knowledge_graph.storage.get_entity(
                effective_user_id, "company", "LegacyCorp"
            )
            if replayed is not None and replayed["confidence"] == 0.8:
                print("  ✓ Rebuild reproduced the legacy row from its synthetic event")
                checks_passed.append("Legacy row survives rebuild via synthetic event")
            else:
                print(f"  ✗ Legacy row lost on rebuild: {replayed}")
                all_passed = False

            # Check 5: recall still works after all the rebuilds.
            recall_msg = "Which company did I found?"
            recall = await self.overlord.chat(
                recall_msg, user_id=user_id, use_async=False, stream=False
            )
            recall_text = recall.content if hasattr(recall, "content") else str(recall)
            transcript.append((recall_msg, recall_text))
            print(f"\nUser: {recall_msg}")
            print(f"Assistant: {recall_text[:300]}...")
            if "automaze" in recall_text.lower():
                print("  ✓ Recall intact after forget + backfill + rebuilds")
                checks_passed.append("Recall intact after rebuild cycle")
            else:
                print("  ✗ Recall failed after rebuild cycle")
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
        print("🧾 AREA 2S2: MEMORY PROVENANCE, FORGETTING, AND BACKFILL")
        print("=" * 60)

        all_passed = await self.test_provenance_and_rebuild()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- 'Why do you think X?' resolves any graph fact to its interaction turn")
        print("- Forgetting a source + rebuild recomputes memory as if it never existed")
        print("- Legacy rows become replayable through synthetic backfill events")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryProvenanceAndRebuild()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
