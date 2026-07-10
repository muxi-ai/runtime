#!/usr/bin/env python3
"""
Test 24A3: Coding delegation, claude-code adapter, existing-project task.

Hermetic: a LOCAL bare git repository (file:// remote) stands in for the
project host. The delegated agent clones it, makes a specific change,
commits, and pushes a branch; the test asserts the branch + commit
arrived in the bare remote. No GitHub, no network.
"""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

from coding_common import (
    delegate_via_chat,
    git,
    load_formation,
    make_bare_remote,
    teardown,
    wait_for_completion,
    wait_for_reentry,
)


async def main():
    print("MUXI Runtime - Test 24A3: claude-code existing-project delegation")
    print("=" * 60)

    formation = None
    fixture_dir = Path(tempfile.mkdtemp(prefix="muxi-coding-24a3-"))
    try:
        remote_url = make_bare_remote(fixture_dir)
        print(f"Local bare remote seeded: {remote_url}")

        task = (
            f"Clone the git repository at {remote_url} into a directory named "
            "repo. Inside that repo, create a branch named muxi-update, append "
            "the line: updated by muxi, to the end of notes.txt, commit with "
            "the message: muxi update, and push the muxi-update branch to origin."
        )

        formation, overlord = await load_formation("formation-claude")
        print(f"Formation loaded: {formation.formation_id}")

        reply, job, user = await delegate_via_chat(overlord, task)
        finished = await wait_for_completion(overlord, job["id"], user)
        assert finished.status == "completed", f"delegation failed: {finished.error}"

        # The branch + commit must have arrived in the bare remote.
        bare = str(fixture_dir / "remote.git")
        branch = git(["--git-dir", bare, "rev-parse", "muxi-update"], check=False)
        assert branch.returncode == 0, "branch muxi-update was not pushed to the remote"
        notes = git(["--git-dir", bare, "show", "muxi-update:notes.txt"]).stdout
        assert "updated by muxi" in notes, f"pushed notes.txt missing the change: {notes!r}"
        subject = git(["--git-dir", bare, "log", "-1", "--format=%s", "muxi-update"]).stdout.strip()
        print(f"Remote received branch muxi-update, HEAD commit: {subject!r}")
        print(f"notes.txt on the remote branch:\n{notes.strip()}")

        await wait_for_reentry(overlord, job["id"], user)

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: claude-code existing-project delegation works end-to-end")
        print("  - the real claude run cloned the local file:// remote")
        print("  - the change was committed and pushed as branch muxi-update")
        print("  - the bare remote received the branch + commit (git is the persistence layer)")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f'\nUser: Please delegate this coding task: "{task}"')
        print(f"System: {reply}")

        print("\nTest 24A3 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation)
        shutil.rmtree(fixture_dir, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
