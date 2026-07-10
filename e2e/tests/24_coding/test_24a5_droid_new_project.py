#!/usr/bin/env python3
"""
Test 24A5: Coding delegation, droid adapter, new-project task.

The delegated droid run git-inits a fresh project inside its disposable
delegation directory. The fixture formation uses cleanup: keep, so the
test asserts the repository + commit exist in the workdir afterwards.
"""

import asyncio
import os
import sys

from coding_common import (
    delegate_via_chat,
    ensure_local_bin_on_path,
    git,
    load_formation,
    teardown,
    wait_for_completion,
    wait_for_reentry,
)

TASK = (
    "Initialize a new git repository in the current directory. Create a "
    "file named hello.txt containing exactly the text: hello muxi. Commit "
    "it with the commit message: init muxi project."
)


async def main():
    print("MUXI Runtime - Test 24A5: droid new-project delegation")
    print("=" * 60)

    ensure_local_bin_on_path()
    formation = None
    try:
        formation, overlord = await load_formation("formation-droid")
        print(f"Formation loaded: {formation.formation_id}")

        reply, job, user = await delegate_via_chat(overlord, TASK)
        finished = await wait_for_completion(overlord, job["id"], user)
        assert finished.status == "completed", f"delegation failed: {finished.error}"

        workdir = finished.delegation_dir
        assert workdir and os.path.isdir(workdir), f"delegation dir missing: {workdir}"
        assert os.path.isdir(os.path.join(workdir, ".git")), "no git repository was created"

        hello = os.path.join(workdir, "hello.txt")
        assert os.path.isfile(hello), "hello.txt was not created"
        assert "hello muxi" in open(hello).read(), "hello.txt content wrong"

        log = git(["log", "--oneline", "-5"], cwd=workdir).stdout
        assert "init muxi project" in log, f"expected commit missing from log: {log!r}"
        print(f"Repository created at {workdir}")
        print(f"Git log: {log.strip()}")

        await wait_for_reentry(overlord, job["id"], user)

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: droid new-project delegation works end-to-end")
        print("  - the real droid run git-inited a project in its delegation dir")
        print("  - hello.txt + the 'init muxi project' commit exist pre-cleanup")
        print("  - completion re-entered the conversation")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f'\nUser: Please delegate this coding task: "{TASK}"')
        print(f"System: {reply}")

        print("\nTest 24A5 PASSED")
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
