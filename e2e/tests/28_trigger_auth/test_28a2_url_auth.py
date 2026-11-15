#!/usr/bin/env python3
"""
Test 28A2: URL auth on a trigger.

A trigger whose frontmatter declares ``auth: <http(s) URL>``:
1. The URL answers 2xx: the trigger runs with no client key.
2. The URL answers 403 or 500: the caller gets the existing 401.
3. The URL receives the documented input: trigger, method, url, headers
   and the base64 of the exact body bytes.
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
from trigger_auth_common import (
    BASE_URL,
    AuthService,
    build_formation,
    print_result,
    start_formation,
    teardown,
    unique_formation_id,
    wait_for_completion,
)

TEMPLATE = "A CRM event arrived: ${{ data.event }}. Reply with the single word: received."


async def main():
    print("MUXI Runtime - Test 28A2: URL auth on a trigger")
    print("=" * 60)

    formation = server = None
    formation_id = unique_formation_id("url")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-trigger-auth-28a2-"))
    auth_service = AuthService()
    transcript = []
    try:
        # The load checks the URL answers, so the service starts first.
        await auth_service.start()
        formation_dir = build_formation(
            tmp,
            formation_id,
            triggers={"hubspot": f"---\nauth: {auth_service.url}\n---\n{TEMPLATE}"},
        )
        formation, server = await start_formation(formation_dir)
        print(f"Formation loaded with server: {formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. 2xx passes.
            body = json.dumps({"event": "contact.created", "id": 42}).encode()
            response = await client.post(
                f"{BASE_URL}/triggers/hubspot",
                headers={"Content-Type": "application/json", "X-Test-Status": "204"},
                content=body,
            )
            assert response.status_code == 200, f"2xx: {response.status_code} {response.text}"
            status = await wait_for_completion(client, response.json()["request"]["id"])
            assert status["status"] == "completed", f"trigger run did not complete: {status}"
            transcript.append(("POST /triggers/hubspot (contact.created)", status.get("result")))
            print("URL answered 204: trigger ran with no client key")

            # 3. The documented input reached the URL.
            received = auth_service.requests[0]
            assert received["trigger"] == "hubspot"
            assert received["method"] == "POST"
            assert received["url"].endswith("/v1/triggers/hubspot"), received["url"]
            assert received["headers"]["x-test-status"] == "204"
            assert base64.b64decode(received["body"]) == body
            print("URL received trigger, method, url, headers and the exact body")

            # 2. Anything else fails with today's 401.
            for status_code in ("403", "500"):
                response = await client.post(
                    f"{BASE_URL}/triggers/hubspot",
                    headers={"X-Test-Status": status_code},
                    json={"event": "contact.deleted"},
                )
                assert (
                    response.status_code == 401
                ), f"{status_code}: {response.status_code} {response.text}"
                assert response.json()["type"] == "error.authentication"
                print(f"URL answered {status_code}: 401")

        print_result(
            "URL auth admits on 2xx and returns today's 401 otherwise",
            [
                "a 204 from the auth URL ran the trigger with no client key",
                "403 and 500 from the auth URL returned 401",
                "the auth URL received the documented JSON with the exact body bytes",
            ],
            transcript,
        )
        print("\nTest 28A2 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        await teardown(formation, server, formation_id, tmp)
        await auth_service.stop()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
