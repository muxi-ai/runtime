#!/usr/bin/env python3
"""
Test 28A4: The body on the own-auth path.

1. The auth script receives the exact body bytes: an HMAC over the raw body,
   computed here, verifies inside the script; a tampered signature fails.
2. A JSON body becomes ``data``: a template reading ``data.event.kind``
   renders and runs.
3. A form-encoded body becomes ``data.body``: a template reading
   ``data.body`` renders and runs, and the JSON-shaped template cannot
   render it (the body is not parsed into fields).
"""

import asyncio
import hashlib
import hmac
import os
import sys
import tempfile
from pathlib import Path

import httpx
from trigger_auth_common import (
    ALLOW,
    BASE_URL,
    HMAC_CHECK,
    SIGNING_SECRET_ENV,
    build_formation,
    print_result,
    start_formation,
    teardown,
    unique_formation_id,
    wait_for_completion,
)

SECRET = "whsec_e2e_28a4"
REPLY = "Reply with the single word: received."


async def main():
    print("MUXI Runtime - Test 28A4: Body handling on the own-auth path")
    print("=" * 60)

    # The runtime's environment is how a script gets its signing secret.
    os.environ[SIGNING_SECRET_ENV] = SECRET

    formation = server = None
    formation_id = unique_formation_id("body")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-trigger-auth-28a4-"))
    transcript = []
    try:
        formation_dir = build_formation(
            tmp,
            formation_id,
            triggers={
                "signed": f"---\nauth: ./auth/hmac_check.py\n---\nSigned: ${{{{ data.id }}}}. {REPLY}",
                "json-event": f"---\nauth: ./auth/allow.py\n---\nKind: ${{{{ data.event.kind }}}}. {REPLY}",
                "form-event": f"---\nauth: ./auth/allow.py\n---\nForm: ${{{{ data.body }}}}. {REPLY}",
            },
            scripts={"allow.py": (ALLOW, True), "hmac_check.py": (HMAC_CHECK, True)},
        )
        formation, server = await start_formation(formation_dir)
        print(f"Formation loaded with server: {formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Exact bytes: odd spacing and key order must survive untouched.
            body = b'{ "id":"evt_28a4",\n\t"amount" : 100 ,"currency":"usd" }'
            signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            response = await client.post(
                f"{BASE_URL}/triggers/signed",
                headers={"Content-Type": "application/json", "X-Test-Signature": signature},
                content=body,
            )
            assert response.status_code == 200, f"signed: {response.status_code} {response.text}"
            status = await wait_for_completion(client, response.json()["request"]["id"])
            assert status["status"] == "completed", f"signed run did not complete: {status}"
            transcript.append(("POST /triggers/signed (evt_28a4)", status.get("result")))
            response = await client.post(
                f"{BASE_URL}/triggers/signed",
                headers={"Content-Type": "application/json", "X-Test-Signature": "0" * 64},
                content=body,
            )
            assert response.status_code == 401, f"tampered: {response.status_code}"
            print("HMAC over the raw body verified in the script; tampered signature: 401")

            # 2. A JSON body becomes data.
            response = await client.post(
                f"{BASE_URL}/triggers/json-event", json={"event": {"kind": "ping"}}
            )
            assert response.status_code == 200, f"json: {response.status_code} {response.text}"
            status = await wait_for_completion(client, response.json()["request"]["id"])
            assert status["status"] == "completed", f"json run did not complete: {status}"
            transcript.append(("POST /triggers/json-event (ping)", status.get("result")))
            print("JSON body became data (data.event.kind rendered)")

            # 3. A form-encoded body becomes data.body.
            form = {"Content-Type": "application/x-www-form-urlencoded"}
            response = await client.post(
                f"{BASE_URL}/triggers/form-event", headers=form, content=b"kind=ping&n=1"
            )
            assert response.status_code == 200, f"form: {response.status_code} {response.text}"
            status = await wait_for_completion(client, response.json()["request"]["id"])
            assert status["status"] == "completed", f"form run did not complete: {status}"
            transcript.append(("POST /triggers/form-event (kind=ping&n=1)", status.get("result")))
            response = await client.post(
                f"{BASE_URL}/triggers/json-event", headers=form, content=b"kind=ping&n=1"
            )
            assert response.status_code == 400, f"form as json: {response.status_code}"
            print("Form body became data.body (and was not parsed into fields)")

        print_result(
            "the own-auth path checks the exact bytes and wraps the body as data",
            [
                "the script verified an HMAC over the exact body bytes; tampering gave 401",
                "a JSON body became data",
                "a form-encoded body became data.body",
            ],
            transcript,
        )
        print("\nTest 28A4 PASSED")
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
