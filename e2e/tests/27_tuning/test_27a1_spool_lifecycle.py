#!/usr/bin/env python3
"""
Test 27A1: event spool lifecycle (Self-Improving Formation, Phase 1).

The retention contract against a real formation with NO observability
config: the spool is written by default; a digest pass (the tuning
loop's single-consumer read) deletes the digested segments and leaves a
checkpoint; traffic after the pass opens a fresh segment; and an
undigested segment survives a formation restart to be digested by the
next pass.
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

USER = "spool-user"


async def main():
    print("MUXI Runtime - Test 27A1: event spool lifecycle")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("spool")
    spool_dir = spool_dir_for(formation_id)
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a1-"))
    transcript = []
    try:
        formation_dir = build_formation(tmp, formation_id)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id}")

        # 1. The spool is written by default -- no observability config.
        task = "Say the word 'ready' and nothing else."
        reply = await chat(overlord, task, USER, "spool-session-1")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply[:120]}")
        segments = wait_for_segments(spool_dir)
        print(f"Spool segments written by default: {[s.name for s in segments]}")

        # 2. A digest pass deletes the digested segments (no file
        #    transport declared) and leaves a checkpoint behind.
        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["spool_committed"] is True, f"digest pass did not commit: {result}"
        assert result["events_read"] > 0, f"digest pass read no events: {result}"
        assert result["spool_segments_kept"] is False
        leftover = [s.name for s in segments if s.exists()]
        assert not leftover, f"digested segments were not deleted: {leftover}"
        assert (spool_dir / "checkpoint.json").exists(), "no checkpoint was written"
        print("Digested segments deleted; checkpoint written")

        # 3. Traffic after the pass opens a fresh segment (never resumes
        #    a checkpointed one).
        task = "Say the word 'again' and nothing else."
        reply = await chat(overlord, task, USER, "spool-session-1")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply[:120]}")
        new_segments = wait_for_segments(spool_dir)
        print(f"Fresh segment after digest: {[s.name for s in new_segments]}")

        # 4. The undigested segment survives a formation restart...
        await teardown(formation)
        formation = None
        print("Formation stopped (undigested segment left behind)")
        survivors = sorted(spool_dir.glob("events-*.jsonl"))
        assert survivors, "undigested segments did not survive the restart"

        formation, overlord = await load_formation(formation_dir)
        print("Formation restarted")

        # ... and the next digest pass consumes it.
        result = await run_tuning_pass(overlord)
        print(f"Post-restart tuning pass: {result}")
        assert result["spool_committed"] is True, f"post-restart pass did not commit: {result}"
        assert result["events_read"] > 0, "post-restart pass read no surviving events"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: event spool lifecycle works end-to-end")
        print("  - spool written by default with no observability config")
        print("  - digest pass deleted digested segments and checkpointed")
        print("  - post-digest traffic opened a fresh segment")
        print("  - undigested segment survived restart and was digested next pass")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A1 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation, formation_id)
        else:
            import shutil

            shutil.rmtree(Path.home() / ".muxi" / formation_id, ignore_errors=True)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
