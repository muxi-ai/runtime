#!/usr/bin/env python3
"""Test 2S1: Memory Event Substrate

This test validates:
1. The memory event substrate is wired into the overlord and the
   memory_events / projection_checkpoints tables are created alongside
   the existing schema
2. Conversation activity records immutable events with provenance
   (interaction.turn plus extraction events linked via caused_by)
3. The captain's log digest dual-writes a log.entry event
4. Wipe-and-replay: wiping a projection and rebuilding it from the
   event log reproduces the same queryable memory state (knowledge
   graph, captain's log, flat facts)
5. Existing memory behavior is intact after a full rebuild (flat-fact
   recall still answers from persistent memory)
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


def normalize_metadata(metadata):
    """Drop storage-assigned write timestamps before state comparison."""
    metadata = dict(metadata or {})
    metadata.pop("timestamp", None)
    return metadata


async def snapshot_graph(knowledge_graph, user_id):
    """Structural knowledge-graph state keyed by entity names."""
    entities = await knowledge_graph.storage.list_entities(user_id, status=None, limit=1000)
    names = {e["id"]: (e["type"], e["name"]) for e in entities}
    relationships = await knowledge_graph.storage.list_relationships(
        user_id, status=None, limit=1000
    )
    return (
        {
            names[e["id"]]: (
                e["confidence"],
                e["status"],
                tuple(e["derived_from_event_ids"]),
            )
            for e in entities
        },
        {
            (names[r["from_entity_id"]], r["type"], names[r["to_entity_id"]]): (
                r["confidence"],
                r["status"],
                tuple(r["derived_from_event_ids"]),
            )
            for r in relationships
        },
    )


async def snapshot_log(captains_log, user_id):
    """Structural captain's-log state keyed by entry date."""
    entries = await captains_log.storage.list_entries(user_id, limit=100)
    sources = await captains_log.storage.get_sources_for_logs([e["id"] for e in entries])
    return {
        e["date"]: (
            e["summary"],
            tuple(e["decisions"]),
            tuple(e["projects"]),
            tuple(e["derived_from_event_ids"]),
            tuple(sorted((s["source_type"], s["source_id"]) for s in sources.get(e["id"], []))),
        )
        for e in entries
    }


def snapshot_flat_facts(long_term_memory, internal_user_id):
    """Extraction-derived flat-fact rows straight from the SQLite table."""
    rows = long_term_memory.conn.execute(
        f"""
        SELECT text, collection, metadata FROM {long_term_memory.memories_table}
        WHERE user_id = ? AND json_extract(metadata, '$.source') = 'extraction'
        ORDER BY text
        """,
        (internal_user_id,),
    ).fetchall()
    import json

    return [
        (text, collection, tuple(sorted(normalize_metadata(json.loads(metadata or "{}")).items())))
        for text, collection, metadata in rows
    ]


class TestMemoryEventSubstrate(BaseMemoryTest):
    """Test event recording, provenance, and wipe-and-replay rebuilds."""

    async def test_event_substrate(self):
        """Events record with provenance; wipe-and-replay reproduces state."""
        test_name = "2s1_memory_event_substrate"
        self.print_test_header(
            test_name, "Test memory event recording, provenance, and projection rebuild"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "event_test_user"

        try:
            # Start from a fresh database so schema and row assertions are
            # deterministic (the sqlite formation stores memory_test.db in
            # this test's working directory).
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Recording conversation events...")
            await self.setup_memory_formation("sqlite")

            # SQLite runs in single-user mode: every external user id is
            # normalized to "0" before extraction sees it.
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            # Check 1: substrate service is wired into the overlord
            memory_events = getattr(self.overlord, "memory_events", None)
            if memory_events is not None:
                print("  ✓ Memory event substrate initialized")
                checks_passed.append("Memory event substrate initialized")
            else:
                print("  ✗ Memory event substrate missing from overlord")
                all_passed = False

            # Check 2: substrate tables exist alongside the rest of the schema
            if memory_events is not None:
                from sqlalchemy import inspect

                tables = inspect(memory_events.db_manager.engine).get_table_names()
                expected = {"memory_events", "projection_checkpoints"}
                if expected.issubset(set(tables)):
                    print("  ✓ memory_events and projection_checkpoints tables created")
                    checks_passed.append("Substrate tables created")
                else:
                    print(f"  ✗ Substrate tables missing (found: {tables})")
                    all_passed = False

                registered = sorted(memory_events.projectors)
                core = {"captains_log", "flat_facts", "knowledge_graph"}
                if core.issubset(set(registered)):
                    print(f"  ✓ Projectors registered: {registered}")
                    checks_passed.append("Core projectors registered")
                else:
                    print(f"  ✗ Unexpected projector registry: {registered}")
                    all_passed = False

            # Conversation turns: graph-friendly and flat-fact-friendly facts
            user_msg1 = (
                "My name is Jordan. I founded a company called Automaze and I live in "
                "London. Today we decided to launch the MUXI project next month."
            )
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, use_async=False, stream=False
            )
            response1_text = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            user_msg2 = "My favorite color is blue and I have two cats named Whiskers and Shadow."
            response2 = await self.overlord.chat(
                user_msg2, user_id=user_id, use_async=False, stream=False
            )
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append((user_msg2, response2_text))
            print(f"User: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            # Check 3: events recorded with provenance (extraction is
            # fire-and-forget; poll until the passes have run)
            events = []
            if memory_events is not None:
                for _ in range(12):
                    await asyncio.sleep(5)
                    events = await memory_events.list_events(effective_user_id)
                    types = {e["event_type"] for e in events}
                    if "interaction.turn" in types and "fact.extracted" in types:
                        break

                types = {e["event_type"] for e in events}
                if "interaction.turn" in types:
                    print(f"  ✓ Interaction turns recorded as events ({len(events)} total)")
                    checks_passed.append("Interaction turns recorded")
                else:
                    print(f"  ✗ No interaction.turn events found (types: {types})")
                    all_passed = False

                derived = [e for e in events if e["event_type"] != "interaction.turn"]
                linked = [e for e in derived if e["caused_by"] is not None]
                if derived and linked:
                    print(
                        f"  ✓ Extraction events carry caused_by provenance "
                        f"({len(linked)}/{len(derived)} linked)"
                    )
                    checks_passed.append("Events carry causation provenance")
                else:
                    print(f"  ✗ No extraction events with caused_by links ({len(derived)} derived)")
                    all_passed = False

                scoped = all(
                    e["scope_type"] == "user" and e["scope_id"] == effective_user_id for e in events
                )
                if events and scoped:
                    print("  ✓ Every event carries the forward-compatible user scope")
                    checks_passed.append("Events carry scope columns")
                else:
                    print("  ✗ Events missing scope_type/scope_id values")
                    all_passed = False

            # Check 4: captain's log digest dual-writes a log.entry event
            captains_log = getattr(self.overlord, "captains_log", None)
            if memory_events is not None and captains_log is not None:
                model = getattr(self.overlord, "extraction_model", None) or getattr(
                    self.overlord, "default_model", None
                )
                totals = await captains_log.run_periodic_summarization(model)
                print(f"  Digest totals: {totals}")
                log_events = await memory_events.list_events(
                    effective_user_id, event_types=["log.entry"]
                )
                if totals["entries"] >= 1 and log_events:
                    print("  ✓ Digest recorded a log.entry event alongside the projection write")
                    checks_passed.append("Digest dual-writes log.entry events")
                else:
                    print("  ✗ Digest produced no log.entry event")
                    all_passed = False

            # Give the fire-and-forget flat-fact extraction time to finish
            # before snapshotting (2B1 pattern).
            await asyncio.sleep(20)

            print("\n🔄 Phase 2: Wipe-and-replay rebuild...")
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
            long_term_memory = getattr(self.overlord, "long_term_memory", None)
            internal_user_id = await long_term_memory.get_or_create_user(effective_user_id)

            graph_before = await snapshot_graph(knowledge_graph, effective_user_id)
            log_before = await snapshot_log(captains_log, effective_user_id)
            facts_before = snapshot_flat_facts(long_term_memory, internal_user_id)
            print(
                f"  State before: {len(graph_before[0])} entities, "
                f"{len(graph_before[1])} relationships, {len(log_before)} log entries, "
                f"{len(facts_before)} extracted facts"
            )
            if graph_before[0] and facts_before and log_before:
                checks_passed.append("All three projections populated")
            else:
                print("  ✗ Expected all projections to be populated before the rebuild")
                all_passed = False

            # Check 5: wiping a projection leaves it empty (proves the
            # rebuild below starts from nothing, not from leftovers)
            await memory_events.projectors["knowledge_graph"].reset(effective_user_id)
            wiped = await snapshot_graph(knowledge_graph, effective_user_id)
            if not wiped[0] and not wiped[1]:
                print("  ✓ Knowledge graph projection wiped")
                checks_passed.append("Projection wipe empties derived state")
            else:
                print(f"  ✗ Projection wipe left rows behind: {wiped}")
                all_passed = False

            # Check 6: full rebuild replays every projection from events.
            # The three core projections must have replayed events; other
            # registered projections (artifact_metadata) may legitimately
            # have none in this conversation but must not fail.
            report = await memory_events.rebuild(effective_user_id)
            print(f"  Rebuild report: {report}")
            core = {"knowledge_graph", "captains_log", "flat_facts"}
            replayed = all(
                report[name]["applied"] > 0 and report[name]["failed"] == 0 for name in core
            )
            clean = all(section["failed"] == 0 for section in report.values())
            if core.issubset(set(report)) and replayed and clean:
                print("  ✓ Rebuild replayed events into all core projections")
                checks_passed.append("Rebuild replays all projections")
            else:
                print("  ✗ Rebuild report incomplete or contains failures")
                all_passed = False

            graph_after = await snapshot_graph(knowledge_graph, effective_user_id)
            log_after = await snapshot_log(captains_log, effective_user_id)
            facts_after = snapshot_flat_facts(long_term_memory, internal_user_id)

            if graph_after == graph_before:
                print("  ✓ Knowledge graph state identical after replay")
                checks_passed.append("Knowledge graph replay-equivalent")
            else:
                print(f"  ✗ Knowledge graph diverged:\n    {graph_before}\n    {graph_after}")
                all_passed = False

            if log_after == log_before:
                print("  ✓ Captain's log state identical after replay")
                checks_passed.append("Captain's log replay-equivalent")
            else:
                print(f"  ✗ Captain's log diverged:\n    {log_before}\n    {log_after}")
                all_passed = False

            if facts_after == facts_before:
                print("  ✓ Flat-fact state identical after replay")
                checks_passed.append("Flat facts replay-equivalent")
            else:
                print(f"  ✗ Flat facts diverged:\n    {facts_before}\n    {facts_after}")
                all_passed = False

            # Check 7: existing memory behavior intact after the rebuild
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
                print("  ✓ Flat-fact recall works from the rebuilt projections")
                checks_passed.append("Recall intact after rebuild")
            else:
                print("  ✗ Recall failed after projection rebuild")
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
        print("🧾 AREA 2S1: MEMORY EVENT SUBSTRATE")
        print("=" * 60)

        all_passed = await self.test_event_substrate()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Every memory write lands in the immutable event log first")
        print("- Extraction events trace back to their interaction.turn via caused_by")
        print("- Wipe-and-replay reproduces identical graph, log, and flat-fact state")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryEventSubstrate()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
