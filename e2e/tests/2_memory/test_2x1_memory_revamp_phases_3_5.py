#!/usr/bin/env python3
"""Test 2X1: Memory Revamp Phases 3-5 (Context Optimization, Knowledge Index, Lint)

This test validates:
1. The phase 3-5 services wire into the overlord from formation config:
   pre-compaction flush (attached to the buffer's eviction path), cache-TTL
   context pruner, knowledge index, and the memory lint background loop
2. Pre-compaction flush SURVIVES EVICTION: buffer items evicted by the
   working memory's FIFO cleanup are digested into the captain's log (and
   knowledge graph) via the silent turn BEFORE they are dropped, so the
   facts remain queryable after the buffer no longer holds them
3. Knowledge index injection is observable in a real turn: the agent's
   assembled system message for a subsequent chat turn carries the
   "[Memory Index" blob (entities / captain's log catalog), within the
   configured token cap
4. Lint runs on demand: the report covers the audit checks and its
   findings feed back into the knowledge index
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


class TestMemoryRevampPhases35(BaseMemoryTest):
    """Test context optimization, knowledge index, and lint end to end."""

    async def test_memory_revamp(self):
        test_name = "2x1_memory_revamp_phases_3_5"
        self.print_test_header(
            test_name, "Test pre-compaction flush, knowledge index injection, and lint"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "revamp_test_user"

        try:
            # Fresh database for deterministic schema/row assertions.
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_revamp_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\nPhase 1: Loading formation with phases 3-5 configured...")
            await self.setup_memory_formation("memory_revamp")
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            # Check 1: all phase 3-5 services wired into the overlord
            flush = getattr(self.overlord, "precompaction_flush", None)
            pruner = getattr(self.overlord, "context_pruner", None)
            memory_index = getattr(self.overlord, "memory_index", None)
            memory_lint = getattr(self.overlord, "memory_lint", None)
            wired = (
                flush is not None
                and pruner is not None
                and memory_index is not None
                and memory_lint is not None
            )
            if wired:
                print("  ✓ Flush, pruner, knowledge index, and lint services wired")
                checks_passed.append("Phase 3-5 services wired")
            else:
                print(
                    f"  ✗ Missing services: flush={flush} pruner={pruner} "
                    f"index={memory_index} lint={memory_lint}"
                )
                all_passed = False

            # Check 2: the flush listener is attached to the buffer and the
            # lint background loop is running (shared lifecycle pattern)
            buffer_memory = self.overlord.buffer_memory
            listener_attached = (
                buffer_memory is not None and buffer_memory._eviction_listener is not None
            )
            lint_running = (
                memory_lint is not None
                and memory_lint._task is not None
                and not memory_lint._task.done()
            )
            if listener_attached and lint_running:
                print("  ✓ Eviction listener attached; lint loop running beside scheduler")
                checks_passed.append("Lifecycle wiring correct")
            else:
                print(
                    f"  ✗ listener_attached={listener_attached} lint_running={lint_running}"
                )
                all_passed = False

            # Conversation turn with distinctive facts destined for eviction.
            user_msg1 = (
                "My name is Jordan. I founded a company called Automaze and today "
                "we decided to launch the MUXI project next month."
            )
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, use_async=False, stream=False
            )
            response1_text = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((user_msg1, response1_text))
            print(f"\nUser: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            # Give the fire-and-forget buffer writes time to land.
            await asyncio.sleep(5)

            print("\nPhase 2: Forcing FIFO eviction (pre-compaction flush)...")
            # Shrink the budget so the stored turns exceed it, then run the
            # REAL eviction path. The flush must capture the items first.
            buffer_before = [
                item["text"]
                for item in buffer_memory.buffer
                if item.get("namespace", "buffer") == "buffer"
            ]
            print(f"  Buffer items before eviction: {len(buffer_before)}")
            buffer_memory.max_memory_mb = 0.000001
            buffer_memory.check_memory_usage_and_cleanup()

            buffer_after = [
                item["text"]
                for item in buffer_memory.buffer
                if item.get("namespace", "buffer") == "buffer"
            ]
            evicted = len(buffer_before) - len(buffer_after)

            # Check 3: eviction actually removed buffer items
            if buffer_before and evicted > 0:
                print(f"  ✓ FIFO eviction removed {evicted} buffer item(s)")
                checks_passed.append("FIFO eviction removed items")
            else:
                print(f"  ✗ Eviction removed nothing (before={len(buffer_before)})")
                all_passed = False

            # Check 4: the silent flush turn persisted the evicted content
            # to the captain's log BEFORE it was dropped (poll: the flush
            # runs a real LLM digest in the background).
            entries = []
            captains_log = self.overlord.captains_log
            for _ in range(24):
                await asyncio.sleep(5)
                entries = await captains_log.get_history(effective_user_id, include_sources=True)
                if entries:
                    break
            if entries:
                summary = (entries[0]["summary"] or "").lower()
                fact_survived = any(
                    marker in summary for marker in ("muxi", "automaze", "launch", "jordan")
                )
                if fact_survived:
                    print(f"  ✓ Flush survived eviction - log entry: {entries[0]['summary']}")
                    checks_passed.append("Pre-compaction flush survived eviction")
                else:
                    print(f"  ✗ Log entry exists but lost the facts: {entries[0]['summary']}")
                    all_passed = False
                if entries[0].get("sources"):
                    print(f"  ✓ Flushed entry carries {len(entries[0]['sources'])} source rows")
                    checks_passed.append("Flushed entry has source lineage")
            else:
                print("  ✗ No captain's log entry produced by the pre-compaction flush")
                all_passed = False

            print("\nPhase 3: Knowledge index injection in a real turn...")
            # Check 5: the index blob renders the flushed knowledge
            index_block = await memory_index.get_index_block(effective_user_id)
            print(f"  Index block:\n    {index_block.replace(chr(10), chr(10) + '    ')}")
            if index_block.startswith("[Memory Index") and len(index_block) <= (
                memory_index.max_chars
            ):
                print(f"  ✓ Index blob rendered within cap ({len(index_block)} chars)")
                checks_passed.append("Index blob rendered within size cap")
            else:
                print("  ✗ Index blob missing or over the size cap")
                all_passed = False

            # Check 6: a real chat turn carries the index at retrieval
            # start. Both context representations are inspected via a
            # pass-through spy on the orchestrator's enhancement step: the
            # marker-formatted analyzer blob (=== MEMORY INDEX ===) and the
            # clean bundle's profile text ([Memory Index blob).
            orchestrator = self.overlord.chat_orchestrator
            captured = {}
            original_enhance = orchestrator._enhance_message_with_context
            original_clean = orchestrator._build_clean_chat_context

            async def spy_enhance(*args, **kwargs):
                result = await original_enhance(*args, **kwargs)
                captured["enhanced"] = result.enhanced
                return result

            async def spy_clean(*args, **kwargs):
                bundle = await original_clean(*args, **kwargs)
                captured["clean_profile"] = bundle.get("user_profile_text", "")
                return bundle

            orchestrator._enhance_message_with_context = spy_enhance
            orchestrator._build_clean_chat_context = spy_clean
            try:
                recall_msg = "What do you know about my projects?"
                recall_response = await self.overlord.chat(
                    recall_msg, user_id=user_id, use_async=False, stream=False
                )
            finally:
                orchestrator._enhance_message_with_context = original_enhance
                orchestrator._build_clean_chat_context = original_clean
            recall_text = (
                recall_response.content
                if hasattr(recall_response, "content")
                else str(recall_response)
            )
            transcript.append((recall_msg, recall_text))
            print(f"\nUser: {recall_msg}")
            print(f"Assistant: {recall_text[:200]}...")

            in_enhanced = "=== MEMORY INDEX ===" in captured.get(
                "enhanced", ""
            ) and "[Memory Index" in captured.get("enhanced", "")
            in_clean = "[Memory Index" in captured.get("clean_profile", "")
            if in_enhanced and in_clean:
                print("  ✓ Memory index injected into the real turn's context")
                print("    (analyzer blob AND clean chat bundle)")
                checks_passed.append("Index injection observable in a real turn")
            else:
                print(f"  ✗ Index missing: enhanced={in_enhanced} clean={in_clean}")
                all_passed = False

            print("\nPhase 4: On-demand lint run...")
            report = await memory_lint.run_lint(user_id=effective_user_id)
            print(f"  Lint report: {report}")
            expected_keys = {
                "users",
                "unresolved_conflicts",
                "superseded_deleted",
                "orphans_removed",
                "log_gaps",
                "stale_artifacts",
                "index_regenerated",
                "findings",
            }
            if expected_keys.issubset(report.keys()) and report["users"] == 1:
                print("  ✓ Lint audited the user and returned the full health report")
                checks_passed.append("Lint on-demand run works")
            else:
                print("  ✗ Lint report incomplete")
                all_passed = False

            # Check 8: lint findings feed the knowledge index store
            findings = await memory_index.get_lint_findings(effective_user_id)
            stored_findings = report["findings"].get(effective_user_id, [])
            if findings == stored_findings:
                print(f"  ✓ Lint findings fed back into the index ({len(findings)} finding(s))")
                checks_passed.append("Lint findings feed the index")
            else:
                print(f"  ✗ Index findings {findings} != report findings {stored_findings}")
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
        print("AREA 2X1: MEMORY REVAMP PHASES 3-5")
        print("=" * 60)

        all_passed = await self.test_memory_revamp()

        print("\n" + "=" * 60)
        print(
            f"OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\nKEY INSIGHTS:")
        print("- Buffer items run a silent digest turn before FIFO eviction drops them")
        print("- The knowledge index catalogs memory and injects at retrieval start")
        print("- Lint audits the store on demand and feeds findings into the index")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestMemoryRevampPhases35()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
