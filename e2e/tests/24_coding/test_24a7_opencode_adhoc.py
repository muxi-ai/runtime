#!/usr/bin/env python3
"""
Test 24A7: Coding delegation, opencode adapter, ad-hoc task.

Chat turn -> delegate_coding tool -> REAL `opencode run` subprocess ->
tracked job completes -> result re-enters the conversation
(route_class: delegation) and stays retrievable by the calling user.
opencode is a captured-session adapter: the first run carries no session
flag and the tool-assigned id is parsed from output, so the finished job
must read as resumable.
"""

import asyncio
import os
import sys

from coding_common import (
    assert_cross_user_isolation,
    delegate_via_chat,
    load_formation,
    teardown,
    wait_for_completion,
    wait_for_reentry,
)

TASK = "Compute 17*23 and reply with only the resulting number."


async def main():
    print("MUXI Runtime - Test 24A7: opencode ad-hoc delegation")
    print("=" * 60)

    formation = None
    try:
        formation, overlord = await load_formation("formation-opencode")
        print(f"Formation loaded: {formation.formation_id}")

        reply, job, user = await delegate_via_chat(overlord, TASK)
        finished = await wait_for_completion(overlord, job["id"], user)

        assert finished.status == "completed", f"delegation failed: {finished.error}"
        assert "391" in (finished.result or ""), f"unexpected result: {finished.result!r}"
        print(f"Result carries the computation: {finished.result[:120]!r}")

        # Captured-id path: the tool-assigned session id must have been
        # parsed from output, making the job resumable.
        assert finished.vendor_session_id, "tool-assigned session id was not captured"
        print("Tool-assigned session id captured (resumable job)")

        await wait_for_reentry(overlord, job["id"], user)
        mine = await overlord.delegation_service.list_user_jobs(user)
        assert any(entry["id"] == job["id"] for entry in mine)
        assert mine[0]["result_preview"], "result missing from the user's tracked record"
        assert mine[0]["resumable"] is True, "captured-session job must read as resumable"
        assert_cross_user_isolation(overlord, job["id"])

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: opencode ad-hoc delegation works end-to-end")
        print("  - delegate_coding returned immediately with a job id")
        print("  - the real opencode run completed and produced 391")
        print("  - the tool-assigned session id was captured from output")
        print("  - completion re-entered the conversation (route_class: delegation)")
        print("  - result retrievable by the calling user only")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f'\nUser: Please delegate this coding task: "{TASK}"')
        print(f"System: {reply}")

        print("\nTest 24A7 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
