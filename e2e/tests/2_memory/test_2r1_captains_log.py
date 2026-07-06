#!/usr/bin/env python3
"""Test 2R1: Captain's Log - Memory Revamp Phase 2

This test validates:
1. The captain's log service is wired into the overlord and the
   captains_log / captains_log_sources / lessons tables are created
   alongside the existing schema
2. Conversation activity produces a captain's log entry queryable
   afterwards (summarization triggered deterministically via a direct
   service call rather than waiting for the daily cadence)
3. Log entries carry source lineage and are exposed with public ids
4. The lessons loop works end to end (record_lesson + session injection)
5. Phase 1 knowledge graph extraction and existing flat-fact behavior
   still work in the same run, mirroring the proven 2Q1 flow
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


class TestCaptainsLog(BaseMemoryTest):
    """Test captain's log summarization alongside graph and flat-fact memory."""

    async def test_captains_log_generation(self):
        """Conversation turns produce a queryable log entry without breaking Phase 1."""
        test_name = "2r1_captains_log"
        self.print_test_header(
            test_name, "Test captain's log entries from conversation + Phase 1 regression"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "log_test_user"

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

            # Check 1: captain's log service is wired into the overlord
            captains_log = getattr(self.overlord, "captains_log", None)
            if captains_log is not None:
                print("  ✓ Captain's log service initialized")
                checks_passed.append("Captain's log service initialized")
            else:
                print("  ✗ Captain's log service missing from overlord")
                all_passed = False

            # Check 2: log tables exist in the same database as the rest of the schema
            if captains_log is not None:
                from sqlalchemy import inspect

                tables = inspect(captains_log.db_manager.engine).get_table_names()
                expected = {"captains_log", "captains_log_sources", "lessons"}
                if expected.issubset(set(tables)):
                    print("  ✓ captains_log, captains_log_sources, and lessons tables created")
                    checks_passed.append("Captain's log tables created")
                else:
                    print(f"  ✗ Captain's log tables missing (found: {tables})")
                    all_passed = False

            # Turn 1: narrative-friendly facts (decision + project + graph facts)
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

            # Turn 2: flat-fact-friendly facts (mirrors 2B1's proven recipe)
            user_msg2 = "My favorite color is blue and I have two cats named Whiskers and Shadow."
            response2 = await self.overlord.chat(
                user_msg2, user_id=user_id, use_async=False, stream=False
            )
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append((user_msg2, response2_text))
            print(f"User: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            # Check 3: turns queue for the periodic digest (extraction is
            # async; poll until the fire-and-forget pass has run)
            if captains_log is not None:
                pending = 0
                for _ in range(12):
                    await asyncio.sleep(5)
                    pending = len(captains_log._pending_turns.get(effective_user_id, []))
                    if pending >= 2:
                        break
                if pending >= 2:
                    print(f"  ✓ Conversation turns queued for summarization ({pending})")
                    checks_passed.append("Turns queued for periodic summarization")
                else:
                    print(f"  ✗ Expected 2+ queued turns, found {pending}")
                    all_passed = False

            # Check 4: trigger the summarization pass deterministically
            # (direct service call instead of waiting for the daily cadence)
            entries = []
            if captains_log is not None:
                model = getattr(self.overlord, "extraction_model", None) or getattr(
                    self.overlord, "default_model", None
                )
                totals = await captains_log.run_periodic_summarization(model)
                print(f"  Digest totals: {totals}")
                entries = await captains_log.get_history(effective_user_id, include_sources=True)
                if totals["entries"] >= 1 and entries:
                    print(f"  ✓ Digest produced a captain's log entry: {entries[0]['summary']}")
                    checks_passed.append("Digest produced a log entry")
                else:
                    print("  ✗ Digest produced no captain's log entry")
                    all_passed = False

            # Check 5: entry is queryable with source lineage and public id
            if entries:
                entry = entries[0]
                has_public_id = isinstance(entry["id"], str) and len(entry["id"]) == 21
                has_sources = bool(entry.get("sources"))
                if has_public_id and has_sources:
                    print(
                        f"  ✓ Entry exposes public id and {len(entry['sources'])} "
                        "source lineage rows"
                    )
                    checks_passed.append("Entry queryable with source lineage")
                else:
                    print(f"  ✗ Entry missing public id or sources: {entry}")
                    all_passed = False

                context_block = await captains_log.get_context_block(effective_user_id)
                indented = context_block.replace("\n", "\n    ")
                print(f"  Log context block:\n    {indented}")
                if context_block.startswith("["):
                    print("  ✓ Log context block renders dated entries")
                    checks_passed.append("Log context block renders")
                else:
                    print("  ✗ Log context block empty despite stored entries")
                    all_passed = False

            # Check 6: lessons loop (record + session injection)
            if captains_log is not None and captains_log.lessons_enabled:
                lesson = await captains_log.record_lesson(
                    effective_user_id,
                    "memory_agent",
                    "Prefer concise answers for this user",
                    context="chat style",
                )
                block = await captains_log.get_lessons_prompt_block(
                    effective_user_id, "memory_agent", "e2e-session"
                )
                if lesson["public_id"] and "Prefer concise answers" in block:
                    print("  ✓ record_lesson stored and injected into the session block")
                    checks_passed.append("Lessons recorded and injected")
                else:
                    print(f"  ✗ Lesson block missing recorded rule: {block!r}")
                    all_passed = False

            # Check 7: Phase 1 knowledge graph still extracts in the same run
            knowledge_graph = getattr(self.overlord, "knowledge_graph", None)
            if knowledge_graph is not None:
                entities = await knowledge_graph.storage.list_entities(effective_user_id)
                entity_names = {e["name"].lower() for e in entities}
                print(f"  Entities: {sorted(entity_names)}")
                if "automaze" in entity_names or "london" in entity_names:
                    print("  ✓ Phase 1 knowledge graph extraction intact")
                    checks_passed.append("Knowledge graph extraction intact")
                else:
                    print("  ✗ Knowledge graph entities missing")
                    all_passed = False
            else:
                print("  ✗ Knowledge graph service missing from overlord")
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
            captains_log = getattr(self.overlord, "captains_log", None)

            # Check 8: captain's log entries persist across restart
            if captains_log is not None:
                persisted = await captains_log.get_history(effective_user_id)
                if persisted:
                    print("  ✓ Captain's log entries persisted across restart")
                    checks_passed.append("Log entries persisted across restart")
                else:
                    print("  ✗ Captain's log entries lost after restart")
                    all_passed = False

            # Check 9: existing flat-fact memory behavior still works
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
                print("  ✗ Flat-fact recall failed after captain's log changes")
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
        print("📔 AREA 2R1: CAPTAIN'S LOG (MEMORY REVAMP PHASE 2)")
        print("=" * 60)

        all_passed = await self.test_captains_log_generation()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Conversation turns queue for the periodic digest and produce log entries")
        print("- Entries carry source lineage and inject as narrative context")
        print("- Lessons record and inject per session; Phase 1 KG + flat facts intact")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestCaptainsLog()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
