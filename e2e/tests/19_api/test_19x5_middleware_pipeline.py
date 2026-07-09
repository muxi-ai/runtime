#!/usr/bin/env python3
"""Test 19x5: request middleware pipeline semantics.

Covers the request-middleware PRD's pipeline states:
- ``rbac.fallback: <group>``: a request whose middleware answer is
  cleanly "no groups" proceeds with the fallback group's permissions
- middleware error: the request is REJECTED fail-closed (403) even
  though a fallback group is configured -- rbac.fallback never applies
  to middleware errors
- contract check: a middleware whose server does not expose a
  contract-compliant ``middleware`` tool FAILS the formation load
- ``rbac.active: false``: the kill switch loads the formation with
  groups present but filtering disabled (permission_resolver is None,
  ungrouped requests are served)
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

from muxi.runtime.formation import Formation  # noqa: E402

BASE_URL = "http://127.0.0.1:8271/v1"
HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-456",
    "Content-Type": "application/json",
}


class TestMiddlewarePipeline(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x5_middleware_pipeline",
            test_description="Test middleware fallback, fail-closed, contract, kill switch",
            test_area="19_api",
        )

    async def _chat(self, message="Reply with the single word OK"):
        async with httpx.AsyncClient(timeout=90.0) as client:
            return await client.post(
                f"{BASE_URL}/chat",
                headers={**HEADERS, "X-Muxi-User-Id": "0"},
                json={"message": message, "stream": False},
            )

    async def _restart_on(self, formation_dir: str):
        if self.formation:
            await self.cleanup_formation()
            self.formation = None
            self.overlord = None
            await asyncio.sleep(2)
        await self.setup_formation(formation_path=Path(__file__).parent / formation_dir)
        await self.formation.start_server(block=False)
        await asyncio.sleep(2)

    async def test_19x5_middleware_pipeline(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x5_middleware_pipeline",
            description="Test middleware fallback, fail-closed, contract, kill switch",
        )
        checks = []
        try:
            # Phase A: fallback group path
            print("\n1. Formation with rbac.fallback: public...")
            await self._restart_on("formation-api-middleware-fallback")
            resolver = self.formation.permission_resolver
            assert resolver is not None and resolver.fallback_group == "public"
            perms = resolver.resolve_request(())
            assert perms is not None and perms.group_ids == ("public",), perms
            assert perms.is_allowed("agents", "assistant")
            assert not perms.is_allowed("agents", "researcher")
            r = await self._chat()
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            print("✅ Ungrouped request proceeded with the public fallback tier")
            checks.append("fallback:<group> admits ungrouped requests with that tier")

            # Phase B: middleware error -> fail-closed rejection
            print("\n2. Formation whose middleware errors on every call...")
            await self._restart_on("formation-api-middleware-broken")
            assert self.formation.permission_resolver.fallback_group == "analyst"
            r = await self._chat()
            assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
            print("✅ Middleware error rejected the request (fallback did NOT apply)")
            checks.append("middleware error rejects fail-closed; fallback never applies")

            await self.cleanup_formation()
            self.formation = None
            self.overlord = None
            await asyncio.sleep(2)

            # Phase C: contract violation fails the load
            print("\n3. Formation whose middleware exposes the wrong tool...")
            failed = False
            try:
                bad_formation = Formation()
                await bad_formation.load(
                    str(Path(__file__).parent / "formation-api-middleware-badcontract")
                )
                await bad_formation.start_overlord()
            except Exception as e:
                failed = True
                message = str(e)
                assert "middleware" in message, message
                print(f"✅ Formation failed fast: {message[:100]}")
                checks.append("missing 'middleware' tool fails the formation startup")
            assert failed, "bad-contract formation started but should have failed"

            # Phase D: rbac.active false kill switch
            print("\n4. Formation with rbac.active: false (kill switch)...")
            await self._restart_on("formation-api-rbac-off")
            assert self.formation.permission_resolver is None, "resolver should be OFF"
            assert self.formation.request_middleware is None
            r = await self._chat()
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            print("✅ Kill switch: groups present, filtering disabled, request served")
            checks.append("rbac.active false disables filtering (kill switch)")

            formatter.print_test_result(
                test_name="test_19x5_middleware_pipeline",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19x5_middleware_pipeline",
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
    await TestMiddlewarePipeline().test_19x5_middleware_pipeline()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
