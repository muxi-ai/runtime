#!/usr/bin/env python3
"""
Test 25A4: cross-user isolation + GBAC context on polls (PRD D5).

Against a formation with real group files loaded by the GBAC resolver:

1. A user whose groups deny check_status cannot watch it -- rejected at
   creation with a friendly error (a user who cannot call the tool
   cannot watch it).
2. A permitted user's watch stores the request's resolved permissions;
   polls run under THAT stored context even when the ambient request
   context changes afterwards -- the watch completes.
3. Another user can neither see nor cancel the first user's watch
   (ownership-scoped tracked surface).
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from watch_common import (
    DONE_WHEN,
    build_formation,
    load_formation,
    teardown,
    wait_for_terminal,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.services.gbac import enforcement as gbac_enforcement  # noqa: E402

WATCHERS_GROUP = """\
name: Watchers
description: Full access to the job server
agents: "*"
"""

RESTRICTED_GROUP = """\
name: Restricted
description: May submit but never poll
agents: "*"
mcp_servers:
  job-server:
    tools:
      deny:
        - check_status
"""


async def main():
    print("MUXI Runtime - Test 25A4: cross-user isolation + GBAC on polls")
    print("=" * 60)

    formation = None
    tmp = Path(tempfile.mkdtemp(prefix="muxi-watch-25a4-"))
    try:
        formation_dir = build_formation(
            tmp,
            interval=1,
            timeout=60,
            polls_to_done=2,
            groups={"watchers": WATCHERS_GROUP, "restricted": RESTRICTED_GROUP},
            rbac_fallback="watchers",
        )
        formation, overlord = await load_formation(formation_dir)
        resolver = formation._permission_resolver
        assert resolver is not None, "GBAC resolver was not built from groups/"
        print(f"Formation loaded with GBAC: groups {list(resolver.group_ids)}")

        alice_permissions = resolver.resolve_groups(["watchers"])
        bob_permissions = resolver.resolve_groups(["restricted"])

        # Submit one fixture job to poll.
        submit = await overlord.mcp_service.invoke_tool("job-server", "submit", {"prompt": "fox"})
        job_ref = submit["result"]["structured_content"]["job_id"]

        # --- 1. The restricted user cannot watch a tool he cannot call --
        token = gbac_enforcement.set_current_permissions(bob_permissions)
        groups_token = gbac_enforcement.set_request_groups(("restricted",))
        try:
            rejected = await overlord.watch_service.watch(
                agent_id="assistant",
                user_id="bob",
                tool="job-server.check_status",
                args={"job_id": job_ref},
                done_when=dict(DONE_WHEN),
            )
        finally:
            gbac_enforcement.reset_request_groups(groups_token)
            gbac_enforcement.reset_current_permissions(token)
        assert rejected["success"] is False, rejected
        assert "not available" in rejected["error"], rejected
        print(f"Restricted user rejected at creation: {rejected['error'][:80]}")

        # --- 2. The permitted user's watch polls under HER stored context
        token = gbac_enforcement.set_current_permissions(alice_permissions)
        groups_token = gbac_enforcement.set_request_groups(("watchers",))
        try:
            created = await overlord.watch_service.watch(
                agent_id="assistant",
                user_id="alice",
                tool="job-server.check_status",
                args={"job_id": job_ref},
                done_when=dict(DONE_WHEN),
                result="$.output",
                label="alice's render",
            )
        finally:
            gbac_enforcement.reset_request_groups(groups_token)
            gbac_enforcement.reset_current_permissions(token)
        assert created["success"] is True, created
        watch_id = created["job_id"]

        # Ambient context now belongs to the RESTRICTED user; the poll
        # loop must keep using alice's stored permissions regardless.
        ambient_token = gbac_enforcement.set_current_permissions(bob_permissions)
        try:
            job = await wait_for_terminal(overlord, watch_id, "alice", timeout=60)
        finally:
            gbac_enforcement.reset_current_permissions(ambient_token)
        assert job.status == "completed", f"watch failed under stored context: {job.error}"
        assert "img.fixture" in (job.result or ""), job.result
        print("Polls ran under alice's STORED permissions (ambient context ignored)")

        # --- 3. Cross-user isolation on the tracked surface -------------
        assert overlord.watch_service.get_job(watch_id, "bob") is None
        assert await overlord.watch_service.cancel_job(watch_id, "bob") is False
        bobs_view = await overlord.watch_service.list_user_jobs("bob")
        assert all(entry["id"] != watch_id for entry in bobs_view), bobs_view
        print("Cross-user lookup/cancel correctly reads as not found")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: GBAC + isolation semantics hold for watches")
        print("  - denied tool cannot be watched (creation-time, friendly error)")
        print("  - polls executed under the watcher's stored GBAC context")
        print("  - other users cannot see or cancel the watch")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser (bob/restricted): watch check_status")
        print(f"System: {rejected['error']}")
        print("\nUser (alice/watchers): watch check_status")
        print(f"System: watch {watch_id} completed with {job.result!r}")

        print("\nTest 25A4 PASSED")
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
