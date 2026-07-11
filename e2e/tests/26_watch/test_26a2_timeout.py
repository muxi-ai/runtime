#!/usr/bin/env python3
"""
Test 26A2: watch_job timeout path.

The fixture job never reaches a terminal status (--polls-to-done 0), so
the watch must resolve as timed_out at the formation-configured deadline
and re-enter the conversation with that status -- nothing silently
vanishes. Registered through the service surface for deterministic
timing (the full agent loop is covered by 26A1).
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from watch_common import (
    build_formation,
    load_formation,
    start_watch_directly,
    teardown,
    wait_for_reentry,
    wait_for_terminal,
)


async def main():
    print("MUXI Runtime - Test 26A2: watch_job timeout path")
    print("=" * 60)

    formation = None
    tmp = Path(tempfile.mkdtemp(prefix="muxi-watch-26a2-"))
    try:
        formation_dir = build_formation(tmp, interval=1, timeout=5, polls_to_done=0)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation.formation_id}")

        result = await start_watch_directly(overlord, user="watch-user", label="stalled job")
        print(f"Watch registered: {result['job_id']} (deadline 5s, job never finishes)")

        job = await wait_for_terminal(overlord, result["job_id"], "watch-user", timeout=60)
        assert job.status == "timed_out", f"expected timed_out, got {job.status}"
        assert job.polls >= 1, "the watch timed out without ever polling"
        assert "deadline" in (job.error or ""), f"missing deadline detail: {job.error!r}"
        print(f"Watch timed out after {job.polls} poll(s): {job.error}")

        # The timeout re-enters the conversation (the user learns the job
        # stalled).
        await wait_for_reentry(overlord, result["job_id"], "watch-user")

        # /jobs shows the terminal state.
        listing = await overlord.watch_service.list_user_jobs("watch-user")
        assert listing[0]["status"] == "timed_out", listing

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: watch timeout path works end-to-end")
        print("  - non-terminal job hit the formation-configured deadline")
        print("  - watch resolved as timed_out with the deadline detail")
        print("  - timeout re-entered the conversation (nothing vanished)")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: (service) watch a job that never finishes")
        print(f"System: watch {result['job_id']} resolved as timed_out and re-entered")

        print("\nTest 26A2 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
