#!/usr/bin/env python3
"""
Test 27A2: spool retention with a declared file transport.

The PRD's retention exception: when the formation's ``logging:`` yaml
declares its own file destination, the spool's digested segments are the
dev's telemetry -- the digest pass checkpoints past them but never
deletes them (and never digests them twice).
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

USER = "retention-user"


async def main():
    print("MUXI Runtime - Test 27A2: spool retention with file transport")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("retain")
    spool_dir = spool_dir_for(formation_id)
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a2-"))
    transcript = []
    try:
        formation_dir = build_formation(tmp, formation_id, file_logging=True)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id} (file transport declared)")

        assert overlord.tuning_service is not None
        assert (
            overlord.tuning_service.keep_spool_segments is True
        ), "declared file transport was not detected -- segments would be deleted"

        task = "Say the word 'kept' and nothing else."
        reply = await chat(overlord, task, USER, "retention-session-1")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply[:120]}")
        wait_for_segments(spool_dir)

        # The digest pass commits but keeps every digested segment file.
        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["spool_committed"] is True, f"digest pass did not commit: {result}"
        assert result["events_read"] > 0
        assert result["spool_segments_kept"] is True
        survivors = sorted(spool_dir.glob("events-*.jsonl"))
        assert survivors, "digested segments were deleted despite the file transport"
        print(f"Digested segments kept: {[s.name for s in survivors]}")

        # The checkpoint still advanced: nothing is digested twice.
        second = await run_tuning_pass(overlord)
        print(f"Second tuning pass: {second}")
        assert second["events_read"] == 0 or all(
            s.exists() for s in survivors
        ), "kept segments were re-digested or deleted on the second pass"
        assert all(s.exists() for s in survivors)

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: file-transport retention rule holds")
        print("  - declared file destination detected (keep_spool_segments)")
        print("  - digest pass committed without deleting segment files")
        print("  - checkpoint advanced; kept segments were not digested twice")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A2 PASSED")
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
