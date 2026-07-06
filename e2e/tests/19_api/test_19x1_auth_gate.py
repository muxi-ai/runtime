#!/usr/bin/env python3
"""Test 19x1: Formation user auth gate (server.auth: open | required).

Covers GBAC Phase 1 gate behavior end to end:
- auth open (default): unknown users can chat
- auth required: unknown users get 401 on chat and trigger webhooks
- auth required: users seeded in users/user_identifiers pass the gate
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter  # noqa: E402

from muxi.runtime.utils.user_resolution import resolve_user_identifier  # noqa: E402

KNOWN_USER = "alice@example.com"
UNKNOWN_USER = "stranger@example.com"


class TestAuthGate(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x1_auth_gate",
            test_description="Test formation user auth gate (server.auth)",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.headers = {
            "X-Muxi-Client-Key": "test-client-key-456",
            "Content-Type": "application/json",
        }

    async def _start(self, formation_dir: str):
        await self.setup_formation(formation_path=Path(__file__).parent / formation_dir)
        await self.formation.start_server(block=False)
        await asyncio.sleep(2)

    async def _stop(self):
        await self.cleanup_formation()
        self.formation = None
        self.overlord = None
        await asyncio.sleep(2)  # let the port fully release before the next server

    async def test_19x1_auth_gate(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x1_auth_gate",
            description="Test formation user auth gate (server.auth)",
        )
        checks = []
        try:
            # Phase A: auth open (default) - unknown users pass
            print("\n1. Starting formation with default (open) auth...")
            await self._start("formation-api-authgate-open")
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=90.0) as client:
                print("\n2. Testing chat as unknown user with auth open...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": UNKNOWN_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ auth open: unknown user can chat")
                checks.append("auth open: unknown user allowed")

            await self._stop()

            # Phase B: auth required - unknown users are rejected
            print("\n3. Starting formation with server.auth: required...")
            await self._start("formation-api-authgate-required")

            print("\n4. Seeding known user into users/user_identifiers...")
            await resolve_user_identifier(
                identifier=KNOWN_USER,
                formation_id="api-test-authgate-required",
                db_manager=self.formation._db_manager,
                kv_cache=None,
                create_if_missing=True,
            )
            print(f"✅ Seeded user {KNOWN_USER}")

            async with httpx.AsyncClient(timeout=90.0) as client:
                print("\n5. Testing chat as unknown user with auth required...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": UNKNOWN_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
                assert "Unknown user" in r.text
                print("✅ auth required: unknown user rejected with 401 on /chat")
                checks.append("auth required: unknown user 401 on chat")

                print("\n6. Testing trigger webhook as unknown user...")
                r = await client.post(
                    f"{self.base_url}/triggers/test-trigger",
                    headers={**self.headers, "X-Muxi-User-Id": UNKNOWN_USER},
                    json={"data": {"message": "hello"}},
                )
                assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
                print("✅ auth required: unknown user rejected with 401 on trigger")
                checks.append("auth required: unknown user 401 on trigger")

                print("\n7. Testing chat as known user with auth required...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": KNOWN_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ auth required: known user can chat")
                checks.append("auth required: known user allowed")

                print("\n8. Testing chat with known user in body (deprecated fallback)...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers=self.headers,
                    json={
                        "message": "Reply with the single word OK",
                        "user_id": KNOWN_USER,
                        "stream": False,
                    },
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ auth required: body user_id fallback works")
                checks.append("auth required: body user_id fallback allowed")

                print("\n9. Testing trigger webhook as known user...")
                r = await client.post(
                    f"{self.base_url}/triggers/test-trigger",
                    headers={**self.headers, "X-Muxi-User-Id": KNOWN_USER},
                    json={"data": {"message": "hello"}},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ auth required: known user can fire trigger")
                checks.append("auth required: known user trigger allowed")

            formatter.print_test_result(
                test_name="test_19x1_auth_gate",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19x1_auth_gate",
                success=False,
                checks=[f"Failed: {e}"],
                transcript=[],
                duration=time.time() - start_time,
            )
            import traceback

            traceback.print_exc()
            raise
        finally:
            if self.formation:
                await self.cleanup_formation()


async def main():
    await TestAuthGate().test_19x1_auth_gate()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
