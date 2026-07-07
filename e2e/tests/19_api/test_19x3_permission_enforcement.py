#!/usr/bin/env python3
"""Test 19x3: GBAC resource filtering enforcement (Phase 3).

Reproduces the PRD's Slack example with two groups and two agents:
- a user in group ``hr`` reaches ``hr-assistant``
- the same request from a user in group ``engineering`` never selects
  ``hr-assistant`` -- a directly-addressed denied agent produces the exact
  same error as a nonexistent agent (no information leak), and routed
  requests select a permitted agent instead
- a denied trigger returns 403 with a generic message; a permitted one runs
- a registered user with no group memberships gets a graceful response

Note on identity: this local e2e runs on the SQLite backend, which is
single-user by MUXI convention -- every chat request executes as user "0".
The test therefore moves user "0" between groups across phases (with an
explicit membership-cache invalidation, mirroring the 60s TTL expiry a
multi-user Postgres deployment would see). The trigger channel resolves
the caller's header identity directly (same pattern as the Phase 1 auth
gate), so it exercises two distinct users in a single phase.

The formation runs with server.auth: required (groups/ demands it as of
the 2026-07-07 ruling), so every HTTP identity is seeded into
users/user_identifiers before the requests fire.
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

from muxi.runtime.services.memory.long_term import UserGroup  # noqa: E402
from muxi.runtime.utils.user_resolution import resolve_user_identifier  # noqa: E402

CHAT_USER = "0"  # SQLite backend: all chat requests execute as user "0"
HR_USER = "alice@example.com"
ENG_USER = "carol@example.com"
NO_GROUPS_USER = "stranger@example.com"
FORMATION_ID = "api-test-enforcement"


class TestPermissionEnforcement(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x3_permission_enforcement",
            test_description="Test GBAC Phase 3 resource filtering enforcement",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.headers = {
            "X-Muxi-Client-Key": "test-client-key-456",
            "Content-Type": "application/json",
        }

    def _user_headers(self, user_id: str) -> dict:
        return {**self.headers, "X-Muxi-User-Id": user_id}

    async def _set_memberships(self, user_id: str, *group_ids: str):
        """Replace a user's memberships and invalidate the resolver cache."""
        from sqlalchemy import delete

        async with self.formation._db_manager.get_async_session() as session:
            # Idempotent across runs: the formation SQLite DB persists
            await session.execute(
                delete(UserGroup).where(
                    UserGroup.user_id == user_id,
                    UserGroup.formation_id == FORMATION_ID,
                )
            )
            for group_id in group_ids:
                await UserGroup.create(
                    session,
                    user_id=user_id,
                    group_id=group_id,
                    formation_id=FORMATION_ID,
                )
            await session.commit()
        # Equivalent to waiting out the 60s membership TTL
        self.formation.permission_resolver.invalidate_memberships(user_id)

    async def test_19x3_permission_enforcement(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x3_permission_enforcement",
            description="Test GBAC Phase 3 resource filtering enforcement",
        )
        checks = []
        try:
            print("\n1. Starting formation with groups/, two agents, and a trigger...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api-enforcement"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            resolver = self.formation.permission_resolver
            assert resolver is not None, "permission_resolver not constructed"
            assert resolver.group_ids == ("engineering", "hr"), resolver.group_ids
            print("✅ Formation loaded with groups: engineering, hr")
            checks.append("formation with enforcement groups loads")

            print("\n2. Registering HTTP identities with the auth gate...")
            # groups/ requires server.auth: required, so every header
            # identity must exist in users/user_identifiers to chat at all
            for identity in (HR_USER, ENG_USER, NO_GROUPS_USER):
                await resolve_user_identifier(
                    identifier=identity,
                    formation_id=FORMATION_ID,
                    db_manager=self.formation._db_manager,
                    kv_cache=None,
                    create_if_missing=True,
                )
            print("✅ Identities registered (auth gate)")

            print("\n3. Seeding memberships (chat user→hr, alice→hr, carol→engineering)...")
            await self._set_memberships(CHAT_USER, "hr")
            await self._set_memberships(HR_USER, "hr")
            await self._set_memberships(ENG_USER, "engineering")
            print("✅ Memberships seeded")

            async with httpx.AsyncClient(timeout=120.0) as client:
                print("\n4. HR-group user directly addresses hr-assistant (permitted)...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers=self._user_headers(HR_USER),
                    json={
                        "message": "Reply with the single word OK",
                        "agent_id": "hr-assistant",
                        "stream": False,
                    },
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ Permitted direct address returns 200")
                checks.append("group-A user reaches agent-A (direct address)")

                print("\n5. Trigger channel: alice (hr) permitted, carol (engineering) denied...")
                r = await client.post(
                    f"{self.base_url}/triggers/hr-report",
                    headers=self._user_headers(HR_USER),
                    json={"data": {"event": "quarterly-review"}, "use_async": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                print("✅ Permitted trigger executed (200)")
                checks.append("permitted trigger fires")

                r = await client.post(
                    f"{self.base_url}/triggers/hr-report",
                    headers=self._user_headers(ENG_USER),
                    json={"data": {"event": "quarterly-review"}, "use_async": False},
                )
                assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
                assert "hr-report" not in r.text, "403 detail must not echo the trigger name"
                print("✅ Denied trigger returns 403 with a generic message")
                checks.append("denied trigger returns 403")

                print("\n6. Switching chat user to group engineering...")
                await self._set_memberships(CHAT_USER, "engineering")

                print("\n7. Engineering user directly addresses hr-assistant (denied)...")
                r_denied = await client.post(
                    f"{self.base_url}/chat",
                    headers=self._user_headers(ENG_USER),
                    json={
                        "message": "Reply with the single word OK",
                        "agent_id": "hr-assistant",
                        "stream": False,
                    },
                )
                r_unknown = await client.post(
                    f"{self.base_url}/chat",
                    headers=self._user_headers(ENG_USER),
                    json={
                        "message": "Reply with the single word OK",
                        "agent_id": "ghost-agent",
                        "stream": False,
                    },
                )
                assert r_denied.status_code == r_unknown.status_code, (
                    f"Denied ({r_denied.status_code}) and unknown "
                    f"({r_unknown.status_code}) status codes differ"
                )
                denied_msg = (r_denied.json().get("error") or {}).get("message", "")
                unknown_msg = (r_unknown.json().get("error") or {}).get("message", "")
                assert denied_msg and unknown_msg, (denied_msg, unknown_msg)
                assert (
                    denied_msg.replace("hr-assistant", "ghost-agent") == unknown_msg
                ), f"Denied agent error leaks information: {denied_msg!r} vs {unknown_msg!r}"
                print("✅ Denied agent is indistinguishable from a nonexistent one")
                checks.append("denied direct address == unknown agent (no leak)")

                print("\n8. Engineering user asks an HR question (routed)...")
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers=self._user_headers(ENG_USER),
                    json={
                        "message": (
                            "What is Dave's salary? " "If you can't access that, say so briefly."
                        ),
                        "session_id": "sess-19x3-eng",
                        "stream": False,
                    },
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                selected = self.formation._overlord.agent_router._session_last_agent.get(
                    "sess-19x3-eng"
                )
                assert selected != "hr-assistant", (
                    f"Denied agent hr-assistant was selected for engineering user "
                    f"(selected={selected!r})"
                )
                print(f"✅ hr-assistant never selected (selected: {selected or 'overlord-direct'})")
                checks.append("denied agent never selected for group-B user")

                print("\n9. User with no group memberships chats (graceful response)...")
                await self._set_memberships(CHAT_USER)  # clear all memberships
                r = await client.post(
                    f"{self.base_url}/chat",
                    headers=self._user_headers(NO_GROUPS_USER),
                    json={"message": "What is Dave's salary?", "stream": False},
                )
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
                assert (
                    "no_capabilities" in r.text
                ), f"Expected graceful no-capabilities response, got: {r.text[:300]}"
                print("✅ No-groups user gets a graceful response (no crash)")
                checks.append("no-groups user gets graceful response")

            formatter.print_test_result(
                test_name="test_19x3_permission_enforcement",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )
            print("\nSUCCESS")
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19x3_permission_enforcement",
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
    await TestPermissionEnforcement().test_19x3_permission_enforcement()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
