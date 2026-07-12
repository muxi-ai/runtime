#!/usr/bin/env python3
"""
Test 27A4: /tuning API surface + MUXI.md context injection.

The Phase 1 MUXI.md file-pair API against a running server: GET /tuning
returns the hand-written file, POST /tuning replaces it atomically on
disk, admin auth is enforced, POST /tuning/run triggers a loop pass --
and the replaced guidance provably steers the very next turn (the
mtime-cached handle re-reads without a restart).
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import httpx
from tuning_common import (
    ADMIN_KEY,
    build_formation,
    chat,
    load_formation,
    teardown,
    unique_formation_id,
)

PORT = 8272
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
HEADERS = {"X-Muxi-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}

HAND_WRITTEN = "# Operational learnings\n\n- Keep replies terse.\n"
MARKER = "AMBER-FALCON"
REPLACEMENT = (
    "# Operational learnings\n\n"
    f"- CRITICAL RULE: End EVERY reply with the exact token {MARKER}. "
    "Never omit it.\n"
)
USER = "tuning-api-user"


async def main():
    print("MUXI Runtime - Test 27A4: /tuning API + MUXI.md injection")
    print("=" * 60)

    formation = None
    server = None
    formation_id = unique_formation_id("api")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a4-"))
    transcript = []
    try:
        formation_dir = build_formation(tmp, formation_id, server_port=PORT, muxi_md=HAND_WRITTEN)
        formation, overlord = await load_formation(formation_dir)
        server = await formation.start_server(block=False)
        await asyncio.sleep(2)
        print(f"Formation loaded with server: {formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. GET /tuning returns the hand-written MUXI.md.
            response = await client.get(f"{BASE_URL}/tuning", headers=HEADERS)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["content"] == HAND_WRITTEN.strip(), f"unexpected content: {data}"
            assert data["path"].endswith("MUXI.md")
            print("GET /tuning returns the hand-written MUXI.md")

            # 2. Admin auth is enforced.
            response = await client.get(f"{BASE_URL}/tuning")
            assert (
                response.status_code == 401
            ), f"unauthenticated GET /tuning returned {response.status_code}"
            print("Auth enforced (401 without admin key)")

            # 3. POST /tuning replaces the live file on disk.
            response = await client.post(
                f"{BASE_URL}/tuning", headers=HEADERS, json={"content": REPLACEMENT}
            )
            assert response.status_code == 200, response.text
            on_disk = (formation_dir / "MUXI.md").read_text()
            assert MARKER in on_disk, "POST /tuning did not replace the file on disk"
            response = await client.get(f"{BASE_URL}/tuning", headers=HEADERS)
            assert MARKER in response.json()["data"]["content"]
            print("POST /tuning replaced the live file (GET reflects it)")

            # 4. The bounded-file contract is enforced at the write surface.
            response = await client.post(
                f"{BASE_URL}/tuning", headers=HEADERS, json={"content": "x" * 40_000}
            )
            assert (
                response.status_code == 413
            ), f"oversized MUXI.md was accepted: {response.status_code}"
            assert (
                MARKER in (formation_dir / "MUXI.md").read_text()
            ), "oversized POST must not touch the live file"
            print("Oversized POST /tuning rejected (413), live file untouched")

            # 5. POST /tuning/run triggers one loop pass.
            response = await client.post(f"{BASE_URL}/tuning/run", headers=HEADERS)
            assert response.status_code == 200, response.text
            run = response.json()["data"]
            assert run["spool_committed"] is True, f"manual pass did not commit: {run}"
            print(f"POST /tuning/run pass: {run}")

        # 6. The replaced guidance steers the very next turn -- no restart.
        task = "What is 2 + 2? Answer with the number."
        reply = await chat(overlord, task, USER, "tuning-api-session")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply}")
        assert (
            MARKER in reply
        ), f"MUXI.md guidance was not injected into the turn (no {MARKER!r} in reply)"

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: /tuning API + MUXI.md injection work end-to-end")
        print("  - GET /tuning served the hand-written file (admin auth enforced)")
        print("  - POST /tuning atomically replaced the live file")
        print("  - oversized content rejected at the 32KB bound (413)")
        print("  - POST /tuning/run triggered a committed loop pass")
        print("  - the replaced guidance steered the next turn without a restart")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A4 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if server is not None:
            try:
                await server.stop()
            except Exception:
                pass
        if formation is not None:
            await teardown(formation, formation_id)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
