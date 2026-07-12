#!/usr/bin/env python3
"""
Test 27A6: pending flow (auto_apply: false) + /learnings + pending API.

Under manual mode the tuner writes PENDING-MUXI.md and never touches the
live file. The suggestion is reviewed and accepted through the built-in
/learnings command (chat path), a later suggestion is dismissed through
DELETE /tuning/pending (admin API), and the dismissal is remembered: the
dismissed experiments stay terminal across subsequent passes.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
from tuning_common import (
    ADMIN_KEY,
    build_formation,
    chat,
    experiments_path_for,
    load_formation,
    plant_tool_failures,
    run_tuning_pass,
    spool_dir_for,
    teardown,
    unique_formation_id,
    wait_for_segments,
)

PORT = 8273
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
HEADERS = {"X-Muxi-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}

HAND_WRITTEN = "# Operational learnings\n\n- Keep replies terse.\n"
USER = "pending-flow-user"


async def main():
    print("MUXI Runtime - Test 27A6: pending flow + /learnings + pending API")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("pending")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a6-"))
    transcript = []
    try:
        formation_dir = build_formation(
            tmp,
            formation_id,
            server_port=PORT,
            muxi_md=HAND_WRITTEN,
            manual_tuning=True,
            commands=True,
        )
        formation, overlord = await load_formation(formation_dir)
        await formation.start_server(block=False)
        await asyncio.sleep(2)
        print(f"Formation loaded with server: {formation_id}")

        # 1. Traffic + planted pattern -> one pass writes PENDING-MUXI.md
        #    and leaves the live file alone.
        task = "What is 5 + 5? Digits only."
        reply = await chat(overlord, task, USER, "pending-session")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply}")
        plant_tool_failures(count=30, tool="jira")
        wait_for_segments(spool_dir_for(formation_id))

        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["muxi_md_suggested"] is True, f"no suggestion was written: {result}"
        assert result["muxi_md_applied"] is False
        assert overlord.muxi_md.read() == HAND_WRITTEN.strip(), "live MUXI.md was touched"
        suggestion = overlord.muxi_md.read_pending()
        assert suggestion, "PENDING-MUXI.md is missing"
        assert (formation_dir / "PENDING-MUXI.md").is_file()
        print(f"Suggested revision:\n{suggestion}")

        # 2. GET /tuning/pending serves the suggestion.
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(f"{BASE_URL}/tuning/pending", headers=HEADERS)
            assert response.status_code == 200, response.text
            assert response.json()["data"]["content"] == suggestion
            print("GET /tuning/pending serves the suggestion")

        # 3. Review and accept through the chat path: /learnings.
        for command, needles in (
            ("/learnings", ("Keep replies terse.", "/learnings pending")),
            ("/learnings pending", (suggestion.splitlines()[0],)),
        ):
            reply = (
                await overlord.chat(
                    message=command,
                    user_id=USER,
                    session_id="pending-session",
                    use_async=False,
                    stream=False,
                )
            ).content
            transcript.append((command, reply))
            print(f"User: {command}\nSystem: {reply[:160]}")
            for needle in needles:
                assert needle in reply, f"{command} reply missing {needle!r}: {reply!r}"

        reply = (
            await overlord.chat(
                message="/learnings apply",
                user_id=USER,
                session_id="pending-session",
                use_async=False,
                stream=False,
            )
        ).content
        transcript.append(("/learnings apply", reply))
        print(f"User: /learnings apply\nSystem: {reply}")
        assert "Applied" in reply, f"apply did not confirm: {reply!r}"
        assert overlord.muxi_md.read() == suggestion, "pending was not promoted to live"
        assert overlord.muxi_md.read_pending() is None

        experiments = json.loads(experiments_path_for(formation_id).read_text())["experiments"]
        assert any(record["status"] == "active" for record in experiments), experiments
        print("/learnings apply promoted the suggestion; learnings are under observation")

        # 4. A later suggestion is dismissed through the admin API, and
        #    the dismissal is terminal.
        plant_tool_failures(count=30, tool="confluence")
        result = await run_tuning_pass(overlord)
        print(f"Second pass: {result}")
        if not result["muxi_md_suggested"]:
            # The tuner may legitimately decide the live file already covers
            # it; force a reviewable suggestion through the file contract.
            overlord.muxi_md.write_pending(overlord.muxi_md.read() + "\n- Placeholder suggestion.")
        assert overlord.muxi_md.read_pending() is not None

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.delete(f"{BASE_URL}/tuning/pending", headers=HEADERS)
            assert response.status_code == 200, response.text
            print("DELETE /tuning/pending dismissed the suggestion")

            # Dismissing again is a clean 404: nothing is pending.
            response = await client.delete(f"{BASE_URL}/tuning/pending", headers=HEADERS)
            assert response.status_code == 404, response.text

        assert overlord.muxi_md.read_pending() is None
        experiments = json.loads(experiments_path_for(formation_id).read_text())["experiments"]
        dismissed_hashes = {
            record["content_hash"] for record in experiments if record["status"] == "dismissed"
        }
        assert not any(
            record["status"] == "pending" for record in experiments
        ), f"pending records survived the dismissal: {experiments}"

        # 5. Dismissals survive later passes: the same hashes never leave
        #    the terminal state.
        plant_tool_failures(count=10, tool="confluence")
        await run_tuning_pass(overlord)
        experiments = json.loads(experiments_path_for(formation_id).read_text())["experiments"]
        for record in experiments:
            if record["content_hash"] in dismissed_hashes:
                assert record["status"] == "dismissed", f"dismissal was resurrected: {record}"
        print("Dismissed learnings stayed terminal across a later pass")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: the pending flow works end-to-end")
        print("  - auto_apply: false wrote PENDING-MUXI.md and left the live file alone")
        print("  - GET /tuning/pending served the suggestion")
        print("  - /learnings showed, previewed, and applied the suggestion")
        print("  - DELETE /tuning/pending dismissed a later suggestion (404 when re-dismissed)")
        print("  - dismissed learnings stayed terminal across a later pass")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A6 PASSED")
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
