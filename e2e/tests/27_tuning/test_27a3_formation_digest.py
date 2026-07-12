#!/usr/bin/env python3
"""
Test 27A3: formation digest (Self-Improving Formation, Phase 1 step 1).

Seeded multi-user traffic -> one tuning pass digests the spool into a
formation-scope captain's log entry (real LLM) -> the entry is visible
in a DIFFERENT user's context injection, and the privacy lint holds: the
seeded user ids never reach the shared narrative.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from tuning_common import (
    build_formation,
    chat,
    load_formation,
    run_tuning_pass,
    spool_dir_for,
    teardown,
    unique_formation_id,
    wait_for_segments,
)

ALICE = "alice-digest-e2e"
BOB = "bob-digest-e2e"
CAROL = "carol-digest-e2e"

SEED_TURNS = [
    (ALICE, "alice-session", "What is the capital of France? One word."),
    (ALICE, "alice-session", "And of Japan? One word."),
    (BOB, "bob-session", "What is 12 * 12? Digits only."),
]

CAROL_TASK = "What is the capital of Italy? One word."


async def main():
    print("MUXI Runtime - Test 27A3: formation digest into the captain's log")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("digest")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a3-"))
    transcript = []
    try:
        formation_dir = build_formation(tmp, formation_id)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id}")

        # 1. Seed multi-user traffic.
        for user, session, task in SEED_TURNS:
            reply = await chat(overlord, task, user, session)
            transcript.append((f"{user}: {task}", reply))
            print(f"User ({user}): {task}\nSystem: {reply[:100]}")
        wait_for_segments(spool_dir_for(formation_id))

        # 2. One tuning pass digests the spool into a formation entry.
        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["events_read"] > 0, f"no events were digested: {result}"
        assert (
            result["entries_written"] == 1
        ), f"the digest did not produce a formation log entry: {result}"
        assert result["spool_committed"] is True

        # 3. The formation-scope entry exists and the privacy lint holds:
        #    seeded user ids never reach the shared narrative.
        block = await overlord.captains_log.get_formation_context_block()
        assert block.strip(), "formation context block is empty after the digest"
        print(f"Formation operations log:\n{block}")
        for user_id in (ALICE, BOB):
            assert (
                user_id not in block
            ), f"privacy lint failed: user id {user_id!r} leaked into the formation log"

        # 4. Visible in a DIFFERENT user's context injection: the agent-
        #    bound context bundle built for a user who never chatted
        #    before carries the formation operations log. (Asking the
        #    agent to quote its context trips the prompt-extraction
        #    security analyzer by design, so the bundle -- what the
        #    agent's LLM call actually receives -- is the assertion
        #    surface.)
        bundle = await overlord.chat_orchestrator._build_clean_chat_context(
            current_user_message=CAROL_TASK,
            user_id=CAROL,
            session_id="carol-session",
        )
        profile_text = bundle["user_profile_text"]
        assert "Formation operations log:" in profile_text, (
            "the formation operations log was not injected into another "
            f"user's context: {profile_text[:400]!r}"
        )
        first_sentence = block.split(". ")[0].split("] ", 1)[-1]
        assert (
            first_sentence in profile_text
        ), "the injected block does not carry the digest content"
        print("Formation operations log present in carol's context bundle")

        # A normal turn for that user still works end to end.
        reply = await chat(overlord, CAROL_TASK, CAROL, "carol-session")
        transcript.append((f"{CAROL}: {CAROL_TASK}", reply))
        print(f"User ({CAROL}): {CAROL_TASK}\nSystem: {reply}")
        assert "rome" in reply.lower(), f"carol's turn failed: {reply!r}"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: formation digest works end-to-end")
        print("  - seeded multi-user traffic was digested into one formation entry")
        print("  - privacy lint kept seeded user ids out of the shared narrative")
        print("  - a different user's context injection carries the operations log")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A3 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation, formation_id)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
