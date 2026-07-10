#!/usr/bin/env python3
"""
Test 24A10: Coding delegation, pi adapter, fixture CLI.

The pi CLI is not installed (and needs provider credentials), so this
test provisions a fixture `pi` binary on PATH -- the PRD's fixture-CLI
approach -- emitting the REAL pi 0.73.1 JSONL shapes: the session header
line was verified against the actual tool (a credential-less run emits
it before failing), the agent_end event comes from that version's
bundled docs/json.md. The BUNDLED pi template is what resolves, so its
parse selectors ($.messages[-1].content[-1].text / $.id) and the
captured-session wiring are exercised end to end:

chat turn -> delegate_coding -> fixture `pi --print --mode json <prompt>`
-> session id captured from the header -> continuation replays it via
`--session <id>` -> the fixture proves it received the id.
"""

import asyncio
import os
import stat
import sys
import tempfile
from pathlib import Path

from coding_common import (
    assert_cross_user_isolation,
    delegate_via_chat,
    load_formation,
    teardown,
    wait_for_completion,
    wait_for_reentry,
)

TASK = "List the files in the current directory."

# The fixed id lets the test assert MUXI replayed the CAPTURED id on
# resume (vendor session ids never leak through the public surface).
FIXTURE_SESSION_ID = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001"

# Emits the pi 0.73.1 --mode json line shapes. Resume runs (--session)
# echo the received id in the final text so the test can prove the
# captured id round-tripped.
FIXTURE_PI = f"""#!{sys.executable}
import json, sys

args = sys.argv[1:]
assert args[:3] == ["--print", "--mode", "json"], f"unexpected base args: {{args}}"
session_id = None
if "--session" in args:
    session_id = args[args.index("--session") + 1]
prompt = args[-1]

sid = session_id or "{FIXTURE_SESSION_ID}"
reply = (
    "resumed:" + sid + ":follow-up handled"
    if session_id
    else "fixture-pi-done: " + prompt
)
final = {{
    "role": "assistant",
    "content": [
        {{"type": "thinking", "thinking": "planning"}},
        {{"type": "text", "text": reply}},
    ],
    "stopReason": "stop",
}}
print(json.dumps({{"type": "session", "version": 3, "id": sid, "cwd": "."}}))
print(json.dumps({{"type": "agent_start"}}))
print(json.dumps({{"type": "turn_start"}}))
print(json.dumps({{"type": "message_end", "message": final}}))
print(json.dumps({{"type": "turn_end", "message": final, "toolResults": []}}))
print(json.dumps({{
    "type": "agent_end",
    "messages": [
        {{"role": "user", "content": [{{"type": "text", "text": prompt}}]}},
        final,
    ],
}}))
"""


def provision_fixture_pi(bin_dir: Path) -> None:
    """A fake `pi` on PATH so formation load (binary check) succeeds."""
    script = bin_dir / "pi"
    script.write_text(FIXTURE_PI)
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


async def main():
    print("MUXI Runtime - Test 24A10: pi fixture-CLI delegation")
    print("=" * 60)

    formation = None
    bin_dir = Path(tempfile.mkdtemp(prefix="muxi-coding-24a10-"))
    try:
        provision_fixture_pi(bin_dir)
        print(f"Fixture pi provisioned at {bin_dir}/pi")

        formation, overlord = await load_formation("formation-pi")
        print(f"Formation loaded: {formation.formation_id}")

        # --- First delegation: captured-id path -------------------------
        reply, job, user = await delegate_via_chat(overlord, TASK)
        finished = await wait_for_completion(overlord, job["id"], user)

        assert finished.status == "completed", f"delegation failed: {finished.error}"
        # The template's result selector must have extracted the final
        # assistant text (not thinking, not raw JSONL). The prompt tail is
        # not asserted verbatim -- the delegating LLM owns that fidelity.
        assert (finished.result or "").startswith(
            "fixture-pi-done: "
        ), f"parse.result selector extracted the wrong value: {finished.result!r}"
        assert "files" in finished.result, f"prompt did not reach the CLI: {finished.result!r}"
        # The session header's id must have been captured.
        assert (
            finished.vendor_session_id == FIXTURE_SESSION_ID
        ), "session id was not captured from the pi session header"
        print(f"Result extracted via template selectors: {finished.result!r}")
        print("Session id captured from the session header event")

        await wait_for_reentry(overlord, job["id"], user)
        mine = await overlord.delegation_service.list_user_jobs(user)
        assert mine[0]["resumable"] is True, "captured-session job must read as resumable"

        # --- Continuation: MUXI replays the captured id via --session ---
        continued = await overlord.delegation_service.delegate(
            user_id=user,
            prompt="Now also count them.",
            continue_job_id=job["id"],
        )
        assert continued["success"], f"continuation rejected: {continued}"
        second = await wait_for_completion(overlord, continued["job_id"], user)
        assert second.status == "completed", f"continuation failed: {second.error}"
        assert (
            second.result == f"resumed:{FIXTURE_SESSION_ID}:follow-up handled"
        ), f"the captured session id did not round-trip on resume: {second.result!r}"
        print(f"Continuation replayed the captured id: {second.result!r}")

        assert_cross_user_isolation(overlord, job["id"])

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: pi delegation works end-to-end against the fixture CLI")
        print("  - the bundled pi template resolved and drove the subprocess")
        print("  - result extracted via $.messages[-1].content[-1].text")
        print("  - session id captured from the real-shape session header ($.id)")
        print("  - continuation replayed the captured id via --session")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print(f'\nUser: Please delegate this coding task: "{TASK}"')
        print(f"System: {reply}")

        print("\nTest 24A10 PASSED")
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

        shutil.rmtree(bin_dir, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
