#!/usr/bin/env python3
"""Test 19y1: Idempotency-Key support on POST /v1/chat.

Verifies through a live formation server that:
  1. A request with an Idempotency-Key gets the key echoed in the envelope.
  2. A retry with the same key replays the identical cached response
     (same request id, no reprocessing).
  3. A different key is processed fresh (new request id).
  4. The same key under a different X-Muxi-User-Id is scoped independently.
  5. Requests without the header behave as before (no echo, no replay).
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


class TestIdempotency(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19y1_idempotency",
            test_description="Test Idempotency-Key replay on POST /v1/chat",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.client_key = self._load_key("client_key")

    def _load_key(self, key_name):
        formation_yaml = Path(__file__).parent / "formation-api" / "formation.yaml"
        with open(formation_yaml) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key_name}:"):
                    return stripped.split(f"{key_name}:", 1)[1].strip().strip('"').strip("'")
        return ""

    def _headers(self, idempotency_key=None, user_id=None):
        headers = {
            "X-Muxi-Client-Key": self.client_key,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Muxi-Idempotency-Key"] = idempotency_key
        if user_id:
            headers["X-Muxi-User-Id"] = user_id
        return headers

    async def test_19y1_idempotency(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19y1_idempotency",
            description="Test Idempotency-Key replay on POST /v1/chat",
        )
        checks = []
        payload = {"message": "Reply with exactly one word: pong", "stream": False}
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=120.0) as client:
                print("\n2. POST /chat with Idempotency-Key (first call)...")
                r1 = await client.post(
                    f"{self.base_url}/chat", json=payload, headers=self._headers("e2e-key-1")
                )
                assert r1.status_code == 200, f"status={r1.status_code}: {r1.text[:200]}"
                body1 = r1.json()
                assert body1["request"]["idempotency_key"] == "e2e-key-1", body1["request"]
                request_id_1 = body1["request"]["id"]
                print(f"✅ Key echoed in envelope (request id {request_id_1})")
                checks.append("Key echoed in envelope")

                print("\n3. Retry with the same key replays the cached response...")
                r2 = await client.post(
                    f"{self.base_url}/chat", json=payload, headers=self._headers("e2e-key-1")
                )
                assert r2.status_code == 200
                body2 = r2.json()
                assert body2 == body1, "replayed response differs from original"
                print("✅ Identical response replayed (same request id, no reprocessing)")
                checks.append("Same key replays cached response")

                print("\n4. A different key is processed fresh...")
                r3 = await client.post(
                    f"{self.base_url}/chat", json=payload, headers=self._headers("e2e-key-2")
                )
                assert r3.status_code == 200
                body3 = r3.json()
                assert body3["request"]["id"] != request_id_1, "expected a fresh request id"
                assert body3["request"]["idempotency_key"] == "e2e-key-2"
                print(f"✅ New request id {body3['request']['id']}")
                checks.append("Different key processed fresh")

                print("\n5. Same key under a different user is scoped independently...")
                r4 = await client.post(
                    f"{self.base_url}/chat",
                    json=payload,
                    headers=self._headers("e2e-key-1", user_id="other-user"),
                )
                assert r4.status_code == 200
                body4 = r4.json()
                assert body4["request"]["id"] != request_id_1, "keys must be scoped per user"
                print("✅ Per-user scoping enforced")
                checks.append("Per-user key scoping")

                print("\n6. Request without the header behaves as before...")
                r5 = await client.post(
                    f"{self.base_url}/chat", json=payload, headers=self._headers()
                )
                assert r5.status_code == 200
                body5 = r5.json()
                assert body5["request"].get("idempotency_key") in (None, ""), body5["request"]
                print("✅ No-header passthrough unchanged")
                checks.append("No-header passthrough")

            formatter.print_test_result(
                test_name="test_19y1_idempotency",
                success=True,
                checks=checks,
                transcript=[("User", payload["message"])],
                duration=time.time() - start_time,
            )
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19y1_idempotency",
                success=False,
                checks=checks + [f"Failed: {e}"],
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
    await TestIdempotency().test_19y1_idempotency()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
