#!/usr/bin/env python3
"""Test 19x2: GBAC group permission loading (groups/ auto-discovery).

Covers GBAC Phase 2 end to end:
- a formation with a groups/ directory (including inheritance) loads and
  serves a chat request -- zero behavior regression while groups are loaded
- the PermissionResolver resolves seeded user_groups memberships with
  inheritance, deny-overrides, and empty-membership semantics
- a formation with circular group inheritance FAILS to load with a clear error
- a formation combining groups/ with open (default) auth FAILS to load
  (2026-07-07 ruling: group files require server.auth: required)

Formations with group files run with server.auth: required, so HTTP users
are seeded into users/user_identifiers before chatting (same pattern as
the 19x1 auth gate test).
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

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError  # noqa: E402
from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.services.memory.long_term import UserGroup  # noqa: E402
from muxi.runtime.utils.user_resolution import resolve_user_identifier  # noqa: E402

ANALYST_USER = "alice@example.com"
UNGROUPED_USER = "stranger@example.com"
FORMATION_ID = "api-test-groups"


class TestGroupPermissions(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x2_group_permissions",
            test_description="Test GBAC group permission loading and resolution",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.headers = {
            "X-Muxi-Client-Key": "test-client-key-456",
            "Content-Type": "application/json",
        }

    async def _seed_membership(self, user_id: str, group_id: str):
        from sqlalchemy import delete

        async with self.formation._db_manager.get_async_session() as session:
            # Idempotent across runs: the formation SQLite DB persists
            await session.execute(
                delete(UserGroup).where(
                    UserGroup.user_id == user_id,
                    UserGroup.formation_id == FORMATION_ID,
                )
            )
            await UserGroup.create(
                session,
                user_id=user_id,
                group_id=group_id,
                formation_id=FORMATION_ID,
            )
            await session.commit()

    async def test_19x2_group_permissions(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x2_group_permissions",
            description="Test GBAC group permission loading and resolution",
        )
        checks = []
        try:
            # Phase A: formation with groups/ loads and serves requests
            print("\n1. Starting formation with a groups/ directory...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api-groups"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation with groups/ loaded and server started")
            checks.append("formation with groups/ loads")

            print("\n2. Verifying group auto-discovery...")
            resolver = self.formation.permission_resolver
            assert resolver is not None, "permission_resolver not constructed"
            assert resolver.group_ids == ("admin", "analyst", "base"), resolver.group_ids
            print(f"✅ Auto-discovered groups: {', '.join(resolver.group_ids)}")
            checks.append("groups auto-discovered from groups/ directory")

            print("\n3. Testing chat with groups loaded (zero behavior regression)...")
            # groups/ requires server.auth: required, so register the user
            # with the auth gate first (identity only -- no group membership)
            await resolve_user_identifier(
                identifier=UNGROUPED_USER,
                formation_id=FORMATION_ID,
                db_manager=self.formation._db_manager,
                kv_cache=None,
                create_if_missing=True,
            )
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers={**self.headers, "X-Muxi-User-Id": UNGROUPED_USER},
                    json={"message": "Reply with the single word OK", "stream": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            print("✅ Chat request served with groups loaded")
            checks.append("chat works while groups are loaded (no regression)")

            print("\n4. Seeding analyst group membership...")
            await self._seed_membership(ANALYST_USER, "analyst")
            print(f"✅ Seeded {ANALYST_USER} into group 'analyst'")

            print("\n5. Resolving analyst permissions (with inheritance)...")
            perms = await resolver.resolve(ANALYST_USER)
            assert perms.group_ids == ("analyst",), perms.group_ids
            assert perms.is_allowed("agents", "assistant"), "inherited grant missing"
            assert perms.is_allowed("agents", "researcher"), "own grant missing"
            assert not perms.is_allowed("agents", "hr-assistant"), "ungrated agent allowed"
            effective = perms.effective_tools(
                "assistant", "database-mcp", ["get_records", "delete_records"]
            )
            assert effective == {"get_records"}, effective
            assert perms.memory_write_scopes == ("group:analyst",)
            print("✅ Inheritance, deny override, and memory.write resolved correctly")
            checks.append("analyst resolves with inherited grants and tool deny")

            print("\n6. Resolving user with no memberships...")
            perms = await resolver.resolve(UNGROUPED_USER)
            assert perms.group_ids == ()
            assert not perms.is_allowed("agents", "assistant")
            print("✅ Empty membership resolves to empty permissions")
            checks.append("empty membership resolves to empty permissions")

            await self.cleanup_formation()
            self.formation = None
            self.overlord = None
            await asyncio.sleep(2)  # let the port fully release

            # Phase B: circular inheritance fails formation load
            print("\n7. Loading formation with circular group inheritance...")
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

            # Phase C: groups/ with open (default) auth fails formation load
            print("\n8. Loading formation combining groups/ with open auth...")
            failed = False
            try:
                bad_formation = Formation()
                await bad_formation.load(str(Path(__file__).parent / "formation-api-groups-open"))
            except ConfigurationValidationError as e:
                failed = True
                message = str(e)
                assert "server.auth" in message, message
                assert "required" in message, message
                assert "groups" in message, message
                print("✅ Formation load failed: groups/ requires server.auth: required")
                checks.append("groups/ with open auth fails formation load")
            assert failed, "open-auth groups formation loaded but should have failed"

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
            if self.formation:
                await self.cleanup_formation()


async def main():
    await TestGroupPermissions().test_19x2_group_permissions()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
