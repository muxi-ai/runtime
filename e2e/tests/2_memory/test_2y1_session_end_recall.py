#!/usr/bin/env python3
"""Test 2Y1: Session-End Digest + Time-Anchored Recall (Episodic Gaps)

This test validates the two closable gaps from the muxi#32 episodic
memory audit:

1. Session-end digest trigger: conversation turns stamp a (user, session)
   activity clock; when the session goes idle past the configurable
   threshold, the idle sweep ends the session (emitting session.ended)
   and digests the user's pending turns through the existing Captain's
   Log pipeline -- no waiting for the daily tick, and no double digest
   afterwards.
2. recall_history built-in tool: an agent-facing, read-only, user-scoped
   tool that turns a date-anchored recall question into a date-ranged
   query over the Captain's Log entries, dispatched through the real
   agent tool path.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest


class TestSessionEndRecall(BaseMemoryTest):
    """Test the session-end digest trigger and the recall_history tool."""

    async def test_session_end_and_recall(self):
        """An idled session is digested and recallable by date via the tool."""
        test_name = "2y1_session_end_recall"
        self.print_test_header(test_name, "Test session-end digest trigger + recall_history tool")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "session_end_user"
        session_id = "e2e-session-end"

        try:
            # Start from a fresh database so row assertions are deterministic
            # (the sqlite formation stores memory_test.db in this directory).
            for suffix in ("", "-wal", "-shm"):
                stale = Path.cwd() / f"memory_test.db{suffix}"
                if stale.exists():
                    stale.unlink()

            print("\n📝 Phase 1: Seeding a short session...")
            await self.setup_memory_formation("sqlite")

            # SQLite runs in single-user mode: every external user id is
            # normalized to "0" before extraction sees it.
            effective_user_id = user_id if self.overlord.is_multi_user else "0"

            captains_log = getattr(self.overlord, "captains_log", None)
            if captains_log is None:
                print("  ✗ Captain's log service missing from overlord")
                raise RuntimeError("captains_log service not initialized")

            # Check 1: the session-end trigger is configured by default
            if captains_log.session_idle_seconds > 0:
                minutes = captains_log.session_idle_seconds / 60
                print(f"  ✓ Session-end trigger on by default ({minutes:.0f}m idle threshold)")
                checks_passed.append("Session-end trigger enabled by default")
            else:
                print("  ✗ Session-end trigger disabled by default")
                all_passed = False

            # A short, distinctive conversation that would previously wait
            # for the daily tick to be persisted.
            user_msg1 = (
                "Quick sync: we decided to codename the secret rollout project "
                "'Bluebird' and ship it on Friday."
            )
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, session_id=session_id, use_async=False, stream=False
            )
            response1_text = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            # Check 2: the turn queued AND stamped the session activity clock
            # (extraction is async; poll until the fire-and-forget pass ran)
            stamped = False
            for _ in range(12):
                await asyncio.sleep(5)
                pending = len(captains_log._pending_turns.get(effective_user_id, []))
                stamped = any(key[0] == effective_user_id for key in captains_log._session_activity)
                if pending >= 1 and stamped:
                    break
            if pending >= 1 and stamped:
                print(f"  ✓ Turn queued ({pending}) and session activity stamped")
                checks_passed.append("Turn queued and session activity stamped")
            else:
                print(
                    f"  ✗ Expected queued turn + activity stamp (pending={pending}, stamped={stamped})"
                )
                all_passed = False

            print("\n💤 Phase 2: Idling the session...")
            # Shrink the idle threshold so the session ends deterministically,
            # then run the sweep the background loop would run (the loop
            # ticks at a 60s floor -- calling the sweep directly mirrors how
            # 2R1 triggers the daily digest without waiting a day).
            captains_log.session_idle_seconds = 1.0
            await asyncio.sleep(2)
            model = getattr(self.overlord, "extraction_model", None) or getattr(
                self.overlord, "default_model", None
            )
            totals = await captains_log.sweep_idle_sessions(model)
            print(f"  Sweep totals: {totals}")

            # Check 3: the sweep ended the session and digested the turns
            if totals["sessions"] >= 1 and totals["entries"] >= 1:
                print("  ✓ Idle sweep ended the session and digested its turns")
                checks_passed.append("Idle sweep digested the session")
            else:
                print("  ✗ Idle sweep did not digest the idled session")
                all_passed = False

            # Check 4: exactly once -- a second sweep finds nothing, and the
            # pending queue is empty so the daily tick cannot double-digest
            second = await captains_log.sweep_idle_sessions(model)
            drained = not captains_log._pending_turns.get(effective_user_id)
            if second["sessions"] == 0 and second["entries"] == 0 and drained:
                print("  ✓ Session ended exactly once; no turns left for a double digest")
                checks_passed.append("No double digest after the sweep")
            else:
                print(f"  ✗ Second sweep re-digested (totals={second}, drained={drained})")
                all_passed = False

            # Check 5: the digest is queryable for today's date
            today = datetime.now(timezone.utc).date().isoformat()
            entries = await captains_log.get_history(
                effective_user_id, date_from=today, date_to=today
            )
            entry_text = " ".join(
                " ".join(
                    [entry["summary"] or "", entry["context"] or ""]
                    + [str(d) for d in (entry["decisions"] or [])]
                    + [str(p) for p in (entry["projects"] or [])]
                )
                for entry in entries
            ).lower()
            if entries and "bluebird" in entry_text:
                print(f"  ✓ Session digest stored for {today}: {entries[0]['summary']}")
                checks_passed.append("Session digest persisted with the seeded content")
            else:
                print(f"  ✗ No dated digest mentioning the session (entries={entries})")
                all_passed = False

            print("\n🔎 Phase 3: Time-anchored recall via the tool...")
            # Dispatch recall_history through the real agent tool path (the
            # same invoke_tool route the LLM's tool call takes).
            agent = next(iter(self.overlord.agents.values()))
            tool_result = await agent.invoke_tool(
                "recall_history",
                {"date_from": today, "date_to": today},
                user_id=effective_user_id,
            )
            print(f"  Tool result: {tool_result}")

            # Check 6: the tool returns the date-filtered entry
            recalled = " ".join(str(entry) for entry in tool_result.get("entries", [])).lower()
            if tool_result.get("success") and "bluebird" in recalled:
                print("  ✓ recall_history returned the dated session digest")
                checks_passed.append("recall_history returned the dated digest")
            else:
                print("  ✗ recall_history missed the session digest")
                all_passed = False

            # Check 7: the tool is user-scoped (another user sees nothing)
            other_result = await agent.invoke_tool(
                "recall_history",
                {"date_from": today, "date_to": today},
                user_id="someone_else",
            )
            if other_result.get("success") and other_result.get("count") == 0:
                print("  ✓ recall_history is user-scoped (other user sees nothing)")
                checks_passed.append("recall_history respects user isolation")
            else:
                print(f"  ✗ Cross-user recall leaked entries: {other_result}")
                all_passed = False

            # Check 8: a date-anchored chat question recalls the session
            # (the log context block and/or the tool supply the answer).
            # One simple factual question -- multi-clause "check X and Y"
            # phrasing gets hijacked by the workflow planner.
            recall_msg = f"What codename did we pick for the rollout project on {today}?"
            recall_response = await self.overlord.chat(
                recall_msg,
                user_id=user_id,
                session_id="e2e-recall-session",
                use_async=False,
                stream=False,
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
            if any(marker in recall_lower for marker in ("bluebird", "friday")):
                print("  ✓ Date-anchored question recalled the ended session")
                checks_passed.append("Date-anchored chat recall works")
            else:
                print("  ✗ Date-anchored recall failed")
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
        print("📔 AREA 2Y1: SESSION-END DIGEST + TIME-ANCHORED RECALL")
        print("=" * 60)

        all_passed = await self.test_session_end_and_recall()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Idle sessions are digested at session end, not the next daily tick")
        print("- session.ended fires exactly once per idle session; no double digest")
        print("- recall_history answers date-anchored questions, user-scoped")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestSessionEndRecall()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
