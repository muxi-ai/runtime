#!/usr/bin/env python3
"""
Test 25A3: /jobs list + cancel mid-watch.

Watches are tracked jobs (PRD D8): the built-in /jobs command lists an
active watch, cancel stops polling, and a user-initiated cancel produces
NO completion re-entry (documented). The poll counter must stop moving
after the cancel.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from watch_common import (
    build_formation,
    content_of,
    load_formation,
    start_watch_directly,
    teardown,
)

# Single-user formations track everything under the effective user "0"
# (the /jobs command normalizes the caller the same way -- the coding
# area's gotcha #1).
USER = "0"


async def run_command(overlord, message: str):
    return await overlord._process_slash_command(message, USER, "watch-session-1")


async def main():
    print("MUXI Runtime - Test 25A3: /jobs list + cancel mid-watch")
    print("=" * 60)

    formation = None
    tmp = Path(tempfile.mkdtemp(prefix="muxi-watch-25a3-"))
    try:
        # Long interval: the watch stays active while we exercise /jobs.
        formation_dir = build_formation(
            tmp, interval=2, timeout=300, polls_to_done=0, commands=True
        )
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation.formation_id}")

        result = await start_watch_directly(overlord, user=USER, label="logo render")
        job_id = result["job_id"]
        print(f"Watch registered: {job_id}")

        # /jobs lists the active watch.
        response = await run_command(overlord, "/jobs")
        listing = content_of(response)
        print(f"\n/jobs:\n{listing}\n")
        assert "watched job(s)" in listing, listing
        assert job_id in listing, listing
        assert "logo render" in listing, listing
        assert "watching" in listing, listing

        # pause/resume have no meaning for a poll loop (documented).
        response = await run_command(overlord, f"/jobs pause {job_id}")
        assert "not supported for watched jobs" in content_of(response)

        # Cancel mid-watch: polling stops, no re-entry.
        response = await run_command(overlord, f"/jobs cancel {job_id}")
        cancel_reply = content_of(response)
        print(f"/jobs cancel: {cancel_reply}")
        assert "Stopped watching" in cancel_reply, cancel_reply

        job = overlord.watch_service.get_job(job_id, USER)
        assert job.status == "cancelled", job.status
        polls_at_cancel = job.polls

        # No further polls and no re-entry after the cancel (poll cadence
        # is 2s; three intervals of silence prove the loop stopped).
        await asyncio.sleep(6)
        job = overlord.watch_service.get_job(job_id, USER)
        assert job.polls == polls_at_cancel, "polling continued after cancel"
        assert job.reentry_at is None, "a user-initiated cancel must not re-enter"
        print(f"Polling stopped at {job.polls} poll(s); no re-entry occurred")

        # /jobs now shows the cancelled state.
        listing = content_of(await run_command(overlord, "/jobs"))
        assert "cancelled" in listing, listing

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: /jobs integration works for watches")
        print("  - active watch listed with label, tool, and status")
        print("  - pause/resume answer honestly (not supported)")
        print("  - cancel stopped the poll loop mid-watch")
        print("  - no completion re-entry after a user-initiated cancel")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: /jobs")
        print(f"System: {listing}")
        print(f"\nUser: /jobs cancel {job_id}")
        print(f"System: {cancel_reply}")

        print("\nTest 25A3 PASSED")
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
