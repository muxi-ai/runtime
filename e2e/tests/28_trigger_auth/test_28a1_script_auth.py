#!/usr/bin/env python3
"""
Test 28A1: Script auth on a trigger, with no client key.

A trigger whose frontmatter declares ``auth: ./auth/<script>``:
1. Script exits 0: the provider's own body runs the trigger with no client key.
2. Script exits 1: the caller gets the existing missing-key 401 (not a 422
   for the unwrapped body), byte-identical to an unmapped trigger's 401.
3. Script exceeds the fixed 2-second timeout: 401.
4. The fail log names the trigger and the failure kind, and carries no
   header or body content.
"""

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx
from trigger_auth_common import (
    ALLOW,
    BASE_URL,
    DENY,
    SLOW,
    auth_failures,
    build_formation,
    print_result,
    start_formation,
    teardown,
    unique_formation_id,
    wait_for_completion,
)

TEMPLATE = "A payment event arrived: ${{ data.type }}. Reply with the single word: received."
PROVIDER_BODY = {"type": "charge.succeeded", "note": "E2E_BODY_MARKER"}
SIGNATURE_HEADER = {"Stripe-Signature": "t=1,v1=E2E_SIGNATURE_MARKER"}


def _comparable(response) -> dict:
    """The 401 envelope without the per-request id and timestamp."""
    envelope = response.json()
    envelope.pop("timestamp", None)
    envelope["request"] = {**envelope["request"], "id": None}
    return envelope


async def main():
    print("MUXI Runtime - Test 28A1: Script auth on a trigger")
    print("=" * 60)

    formation = server = None
    formation_id = unique_formation_id("script")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-trigger-auth-28a1-"))
    transcript = []
    try:
        formation_dir = build_formation(
            tmp,
            formation_id,
            triggers={
                "stripe": f"---\nauth: ./auth/allow.py\n---\n{TEMPLATE}",
                "denied": f"---\nauth: ./auth/deny.py\n---\n{TEMPLATE}",
                "slow": f"---\nauth: ./auth/slow.py\n---\n{TEMPLATE}",
                "plain": TEMPLATE,
            },
            scripts={"allow.py": (ALLOW, True), "deny.py": (DENY, True), "slow.py": (SLOW, True)},
        )
        formation, server = await start_formation(formation_dir)
        print(f"Formation loaded with server: {formation_id}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Pass: the provider body runs the trigger with no client key.
            response = await client.post(
                f"{BASE_URL}/triggers/stripe",
                headers={**SIGNATURE_HEADER, "X-Muxi-User-Id": "spoofed-user"},
                json=PROVIDER_BODY,
            )
            assert response.status_code == 200, f"pass: {response.status_code} {response.text}"
            request_id = response.json()["request"]["id"]
            status = await wait_for_completion(client, request_id)
            assert status["status"] == "completed", f"trigger run did not complete: {status}"
            assert status["user_id"] == "0", f"caller user id was not dropped: {status}"
            transcript.append(("POST /triggers/stripe (charge.succeeded)", status.get("result")))
            print(f"Script exit 0: trigger ran with no client key ({request_id})")

            # 2. Fail: today's 401, not a 422 for the unwrapped body.
            denied = await client.post(
                f"{BASE_URL}/triggers/denied", headers=SIGNATURE_HEADER, json=PROVIDER_BODY
            )
            baseline = await client.post(f"{BASE_URL}/triggers/plain", json=PROVIDER_BODY)
            assert denied.status_code == 401, f"deny: {denied.status_code} {denied.text}"
            assert baseline.status_code == 401
            assert _comparable(denied) == _comparable(baseline), (
                f"401 envelope differs from today's:\n{denied.text}\n{baseline.text}"
            )
            print("Script exit 1: existing 401 envelope, unchanged")

            # 3. Timeout: the 2-second limit is fixed and fails closed.
            started = time.monotonic()
            slow = await client.post(
                f"{BASE_URL}/triggers/slow", headers=SIGNATURE_HEADER, json=PROVIDER_BODY
            )
            elapsed = time.monotonic() - started
            assert slow.status_code == 401, f"slow: {slow.status_code} {slow.text}"
            assert 1.9 <= elapsed < 5, f"timeout not enforced at 2s (took {elapsed:.1f}s)"
            print(f"Script over the timeout: 401 after {elapsed:.1f}s")

        # 4. The fail log: trigger name and failure kind only.
        system_log = tmp / "system.jsonl"
        denied_events = auth_failures(system_log, "denied")
        slow_events = auth_failures(system_log, "slow")
        assert denied_events, "no auth failure event logged for 'denied'"
        assert slow_events, "no auth failure event logged for 'slow'"
        assert denied_events[0]["data"]["failure"] == "exit_code"
        assert denied_events[0]["data"]["exit_code"] == 1
        assert slow_events[0]["data"]["failure"] == "timeout"
        log_text = system_log.read_text()
        for marker in ("E2E_SIGNATURE_MARKER", "E2E_BODY_MARKER", "stripe-signature"):
            assert marker not in log_text, f"{marker!r} leaked into the system log"
        print("Fail log carries trigger + failure kind, no header or body content")

        print_result(
            "script auth admits a verified provider and leaves every other caller unchanged",
            [
                "exit 0 ran the trigger with no client key (user id dropped to '0')",
                "exit 1 returned today's 401 envelope, not a 422",
                "a script over 2 seconds returned 401",
                "the fail log named the trigger and failure kind, no headers or body",
            ],
            transcript,
        )
        print("\nTest 28A1 PASSED")
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
