#!/usr/bin/env python3
"""
Test 28A3: Client-key callers are unchanged.

In a formation where one trigger declares ``auth:``:
1. That trigger, called with the real client key and MUXI's ``{"data": ...}``
   body, runs exactly as today even though its auth check fails (the replay
   path).
2. A trigger without ``auth`` still requires the client key and behaves as
   before.
3. ``GET /v1/triggers/<mapped name>`` still requires the client key.
4. A trigger with malformed non-auth frontmatter does not stop the formation
   from booting; calling it is still today's 400.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import httpx
from trigger_auth_common import (
    BASE_URL,
    CLIENT_KEY,
    DENY,
    build_formation,
    print_result,
    start_formation,
    teardown,
    unique_formation_id,
)

TEMPLATE = "An event arrived: ${{ data.message }}. Reply with the single word: received."
KEY = {"X-Muxi-Client-Key": CLIENT_KEY}


async def main():
    print("MUXI Runtime - Test 28A3: Client-key callers are unchanged")
    print("=" * 60)

    formation = server = None
    formation_id = unique_formation_id("keyed")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-trigger-auth-28a3-"))
    transcript = []
    try:
        formation_dir = build_formation(
            tmp,
            formation_id,
            triggers={
                "stripe": f"---\nauth: ./auth/deny.py\n---\n{TEMPLATE}",
                "plain": TEMPLATE,
                "broken": f"---\nbogus: 1\n---\n{TEMPLATE}",
            },
            scripts={"deny.py": (DENY, True)},
        )
        # 4. Boots despite the malformed non-auth trigger.
        formation, server = await start_formation(formation_dir)
        print(f"Formation with a malformed non-auth trigger booted: {formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. The replay path: real key + {"data": ...} on a mapped trigger.
            request = "replayed event"
            response = await client.post(
                f"{BASE_URL}/triggers/stripe",
                headers=KEY,
                json={"data": {"message": request}, "use_async": False},
            )
            assert response.status_code == 200, f"replay: {response.status_code} {response.text}"
            reply = response.json()["data"]
            transcript.append((f"POST /triggers/stripe ({request})", reply))
            print("Mapped trigger with the client key ran as today")

            # 2. A trigger without auth: key required, behaviour unchanged.
            response = await client.post(
                f"{BASE_URL}/triggers/plain", json={"data": {"message": "no key"}}
            )
            assert response.status_code == 401, f"plain no key: {response.status_code}"
            response = await client.post(
                f"{BASE_URL}/triggers/plain",
                headers=KEY,
                json={"data": {"message": "with key"}, "use_async": False},
            )
            assert response.status_code == 200, f"plain key: {response.status_code} {response.text}"
            transcript.append(("POST /triggers/plain (with key)", response.json()["data"]))
            print("Trigger without auth: 401 without key, runs with key")

            # 3. GET on the mapped name still requires the key.
            response = await client.get(f"{BASE_URL}/triggers/stripe")
            assert response.status_code == 401, f"GET no key: {response.status_code}"
            response = await client.get(f"{BASE_URL}/triggers/stripe", headers=KEY)
            assert response.status_code == 200, f"GET key: {response.status_code}"
            print("GET /triggers/stripe: 401 without key, 200 with key")

            # 4. The malformed trigger fails at call time, as today.
            response = await client.post(
                f"{BASE_URL}/triggers/broken", headers=KEY, json={"data": {"message": "x"}}
            )
            assert response.status_code == 400, f"broken: {response.status_code} {response.text}"
            assert "Invalid frontmatter" in response.text, response.text
            print("Malformed non-auth trigger: still a call-time 400")

        print_result(
            "client-key callers behave exactly as before",
            [
                "a mapped trigger with the client key and a data body ran (replay path)",
                "a trigger without auth needs the client key, as before",
                "GET on a mapped trigger still needs the client key",
                "a malformed non-auth trigger did not stop the boot; calling it is a 400",
            ],
            transcript,
        )
        print("\nTest 28A3 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await teardown(formation, server, formation_id, tmp)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
