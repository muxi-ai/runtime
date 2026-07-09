#!/usr/bin/env python3
"""Test 19x2: RBAC group permissions via the request middleware.

Covers the request-middleware PRD end to end:
- a formation declaring a stdio ``middleware:`` (the shipped template
  example reading a static user -> groups map) + a ``groups/`` directory
  loads, connects the middleware, verifies the tool contract, and serves
  a chat request -- the middleware-attached groups drive resource
  filtering through the existing PermissionResolver
- resolver semantics survive the rewiring: inheritance, deny overrides,
  and memory.write resolve from middleware-attached group ids
- NO runtime-side caching: editing the map file takes effect on the very
  next request (fallback: false then rejects the un-mapped user with 403)
- a formation with circular group inheritance FAILS to load
- RBAC active + fallback false + no middleware (dead config) FAILS to load
- a formation still carrying the removed ``server.auth`` key FAILS to
  load with an actionable migration error
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter  # noqa: E402

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError  # noqa: E402
from muxi.runtime.formation import Formation  # noqa: E402

CHAT_USER = "0"  # SQLite backend: chat requests execute as user "0"
FORMATION_ID = "api-test-groups"
FORMATION_DIR = Path(__file__).parent / "formation-api-groups"
GROUPS_MAP = FORMATION_DIR / "groups.json"


class TestGroupPermissions(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x2_group_permissions",
            test_description="Test RBAC group permissions via the request middleware",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.headers = {
            "X-Muxi-Client-Key": "test-client-key-456",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _write_map(mapping: dict) -> None:
        """Point the fixture middleware's map at ``mapping``.

        The template middleware re-reads the file on every call, so the
        change is live immediately -- the runtime never caches answers.
        """
        GROUPS_MAP.write_text(json.dumps(mapping, indent=2) + "\n")

    async def test_19x2_group_permissions(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x2_group_permissions",
            description="Test RBAC group permissions via the request middleware",
        )
        checks = []
        try:
            # Baseline map: chat user "0" is an analyst
            self._write_map({CHAT_USER: ["analyst"], "alice@example.com": ["analyst"]})

            # Phase A: formation with groups/ + middleware loads and serves
            print("\n1. Starting formation with groups/ + stdio middleware...")
            await self.setup_formation(formation_path=FORMATION_DIR)
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation loaded; middleware connected and contract verified")
            checks.append("formation with groups/ + middleware loads (contract verified)")

            print("\n2. Verifying group auto-discovery + rbac wiring...")
            resolver = self.formation.permission_resolver
            assert resolver is not None, "permission_resolver not constructed"
            assert resolver.group_ids == ("admin", "analyst", "base"), resolver.group_ids
            assert resolver.fallback_group is None, "fallback: false expected"
            assert self.formation.request_middleware is not None, "middleware not constructed"
            print(f"✅ Auto-discovered groups: {', '.join(resolver.group_ids)}")
            checks.append("groups auto-discovered; rbac + middleware wired")

            print("\n3. Chat with middleware-attached groups (analyst)...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": CHAT_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            print("✅ Analyst chat served: middleware groups admitted the request")
            checks.append("middleware-attached groups drive access (chat 200)")

            print("\n4. Resolving analyst permissions (with inheritance)...")
            perms = resolver.resolve_groups(("analyst",))
            assert perms.group_ids == ("analyst",), perms.group_ids
            assert perms.is_allowed("agents", "assistant"), "inherited grant missing"
            assert perms.is_allowed("agents", "researcher"), "own grant missing"
            assert not perms.is_allowed("agents", "hr-assistant"), "ungranted agent allowed"
            effective = perms.effective_tools(
                "assistant", "database-mcp", ["get_records", "delete_records"]
            )
            assert effective == {"get_records"}, effective
            assert perms.memory_write_scopes == ("group:analyst",)
            print("✅ Inheritance, deny override, and memory.write resolved correctly")
            checks.append("analyst resolves with inherited grants and tool deny")

            print("\n5. Un-mapping the user: next request is rejected (no caching)...")
            self._write_map({"alice@example.com": ["analyst"]})
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": CHAT_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
            print("✅ fallback: false rejected the ungrouped user with 403, immediately")
            checks.append("no groups + fallback false rejects with 403 (no runtime caching)")

            await self.cleanup_formation()
            self.formation = None
            self.overlord = None
            await asyncio.sleep(2)  # let the port fully release

            # Phase B: circular inheritance fails formation load
            print("\n6. Loading formation with circular group inheritance...")
            failed = False
            try:
                bad_formation = Formation()
                await bad_formation.load(
                    str(Path(__file__).parent / "formation-api-groups-circular")
                )
            except ConfigurationValidationError as e:
                failed = True
                message = str(e)
                assert "Circular group inheritance" in message, message
                print("✅ Formation load failed with a clear circular-inheritance error")
                checks.append("circular inheritance fails formation load")
            assert failed, "circular-inheritance formation loaded but should have failed"

            # Phase C: dead config (rbac active + fallback false + no middleware)
            print("\n7. Loading dead-config formation (no middleware, fallback false)...")
            failed = False
            try:
                bad_formation = Formation()
                await bad_formation.load(
                    str(Path(__file__).parent / "formation-api-groups-deadconfig")
                )
            except ConfigurationValidationError as e:
                failed = True
                message = str(e)
                assert "Dead configuration" in message, message
                assert "middleware" in message, message
                print("✅ Formation load failed: dead configuration detected")
                checks.append("rbac active + fallback false + no middleware fails load")
            assert failed, "dead-config formation loaded but should have failed"

            # Phase D: the removed server.auth key fails the load loudly
            print("\n8. Loading formation still carrying server.auth...")
            failed = False
            try:
                bad_formation = Formation()
                await bad_formation.load(
                    str(Path(__file__).parent / "formation-api-server-auth-removed")
                )
            except ConfigurationValidationError as e:
                failed = True
                message = str(e)
                assert "server.auth" in message and "removed" in message, message
                print("✅ Formation load failed with the server.auth migration error")
                checks.append("removed server.auth key fails load with migration error")
            assert failed, "server.auth formation loaded but should have failed"

            formatter.print_test_result(
                test_name="test_19x2_group_permissions",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19x2_group_permissions",
                success=False,
                checks=[f"Failed: {e}"],
                transcript=[],
                duration=time.time() - start_time,
            )
            import traceback

            traceback.print_exc()
            raise
        finally:
            # Restore the baseline map for the next run
            self._write_map({CHAT_USER: ["analyst"], "alice@example.com": ["analyst"]})
            if self.formation:
                await self.cleanup_formation()


async def main():
    await TestGroupPermissions().test_19x2_group_permissions()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
