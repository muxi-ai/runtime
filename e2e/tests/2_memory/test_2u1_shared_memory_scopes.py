#!/usr/bin/env python3
"""Test 2U1: Memory Namespaces Phases 2+3 - Shared Scopes

Two users in different GBAC groups on a PostgreSQL formation:

1. Write grants: a member of team-a (grants: group:team-a + formation)
   shares a formation fact and a group fact; a member of team-b (grant:
   group:team-b only) gets 403 on formation- and foreign-group writes
   but can share into their own group.
2. Scoped rows: shared writes land with their true (scope_type,
   scope_id); memory events record the same scope.
3. Read fan-out: user A recalls the group-A fact and the formation fact
   but NOT group-B's (listing + retrieval probe + real chat recall);
   user B sees group-B + formation but NOT group-A.
4. Per-query narrowing: scopes=user restores the user-only view.
5. Replay: wipe-and-rebuild of the flat-facts projection reproduces the
   scoped rows from the event log.
6. User-scope recall unchanged: each user's own memories stay private.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import text as sql_text

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_memory_test import BaseMemoryTest  # noqa: E402

from muxi.runtime.services.memory.long_term import UserGroup  # noqa: E402
from muxi.runtime.utils.user_resolution import resolve_user_identifier  # noqa: E402

FORMATION_ID = "scoped-memory-test"
BASE_URL = "http://127.0.0.1:8272/v1"
CLIENT_HEADERS = {
    "X-Muxi-Client-Key": "test-client-key-2u1",
    "Content-Type": "application/json",
}

ALICE = "alice@scoped.test"  # team-a: may write group:team-a + formation
BOB = "bob@scoped.test"  # team-b: may write group:team-b only

FORMATION_FACT = "Our standard refund window is 30 days from the purchase date."
TEAM_A_FACT = "Team A ships releases every Friday afternoon."
TEAM_B_FACT = "Team B holds its standup on Monday mornings."
ALICE_USER_FACT = "Alice's favorite tea is sencha."


class TestSharedMemoryScopes(BaseMemoryTest):
    """Validate shared-scope writes, grants, fan-out, and replay."""

    def _headers(self, user_id: str) -> dict:
        return {**CLIENT_HEADERS, "X-Muxi-User-ID": user_id}

    async def _wipe_previous_run(self):
        """Idempotent re-runs on a persistent PostgreSQL database."""
        async with self.formation._db_manager.get_async_session() as session:
            await session.execute(
                sql_text("DELETE FROM memory_events WHERE formation_id = :f"),
                {"f": FORMATION_ID},
            )
            await session.execute(
                sql_text("DELETE FROM user_groups WHERE formation_id = :f"),
                {"f": FORMATION_ID},
            )
            try:
                await session.execute(
                    sql_text(
                        "DELETE FROM memories_1536 WHERE user_id IN "
                        "(SELECT id FROM users WHERE formation_id = :f)"
                    ),
                    {"f": FORMATION_ID},
                )
            except Exception:
                pass  # table may not exist on a fresh database yet
            await session.commit()

    async def _seed_membership(self, user_id: str, group_id: str):
        async with self.formation._db_manager.get_async_session() as session:
            await UserGroup.create(
                session,
                user_id=user_id,
                group_id=group_id,
                formation_id=FORMATION_ID,
            )
            await session.commit()

    async def _memory_rows(self):
        async with self.formation._db_manager.get_async_session() as session:
            result = await session.execute(
                sql_text(
                    "SELECT m.text, m.scope_type, m.scope_id FROM memories_1536 m "
                    "JOIN users u ON m.user_id = u.id WHERE u.formation_id = :f"
                ),
                {"f": FORMATION_ID},
            )
            return {row[0]: (row[1], row[2]) for row in result.all()}

    async def test_shared_scopes(self):
        test_name = "2u1_shared_memory_scopes"
        self.print_test_header(
            test_name, "Shared memory scopes: write grants, scoped rows, read fan-out, replay"
        )

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            print("\n📝 Phase 1: Formation with groups + PostgreSQL memory...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formations" / "formation-scoped-memory"
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)

            resolver = self.formation.permission_resolver
            assert resolver is not None, "permission_resolver not constructed"
            assert resolver.group_ids == ("team-a", "team-b"), resolver.group_ids
            print(f"  ✓ Groups loaded: {', '.join(resolver.group_ids)}")
            checks_passed.append("Groups loaded")

            await self._wipe_previous_run()

            # Register both users with the auth gate and seed memberships.
            for user in (ALICE, BOB):
                await resolve_user_identifier(
                    identifier=user,
                    formation_id=FORMATION_ID,
                    db_manager=self.formation._db_manager,
                    kv_cache=None,
                    create_if_missing=True,
                )
            await self._seed_membership(ALICE, "team-a")
            await self._seed_membership(BOB, "team-b")
            print(f"  ✓ Seeded {ALICE} -> team-a, {BOB} -> team-b")

            print("\n🔐 Phase 2: Write grants (403 without a memory.write grant)...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                # Alice: formation + own group writes succeed.
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(ALICE),
                    json={"content": FORMATION_FACT, "scope": "formation"},
                )
                assert r.status_code == 200, f"formation write: {r.status_code} {r.text}"
                assert r.json()["data"]["scope"] == "formation", r.json()

                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(ALICE),
                    json={"content": TEAM_A_FACT, "scope": "group", "scope_id": "team-a"},
                )
                assert r.status_code == 200, f"group write: {r.status_code} {r.text}"
                assert r.json()["data"]["scope_id"] == "team-a", r.json()
                print("  ✓ Alice (team-a) wrote a formation fact and a group fact")
                checks_passed.append("Granted shared writes succeed")

                # Bob: no formation grant, no foreign-group grant -> 403.
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(BOB),
                    json={"content": "Bob's formation takeover", "scope": "formation"},
                )
                assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(BOB),
                    json={
                        "content": "Bob writes into team-a",
                        "scope": "group",
                        "scope_id": "team-a",
                    },
                )
                assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
                print("  ✓ Bob's ungranted formation / foreign-group writes got 403")
                checks_passed.append("Ungranted shared writes rejected (403)")

                # Bob CAN share into his own group.
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(BOB),
                    json={"content": TEAM_B_FACT, "scope": "group", "scope_id": "team-b"},
                )
                assert r.status_code == 200, f"team-b write: {r.status_code} {r.text}"

                # Alice: plain user-scope write (unchanged Phase 1 path).
                r = await client.post(
                    f"{BASE_URL}/memories",
                    headers=self._headers(ALICE),
                    json={"content": ALICE_USER_FACT},
                )
                assert r.status_code == 200, f"user write: {r.status_code} {r.text}"
                assert r.json()["data"]["scope"] == "user", r.json()
                print("  ✓ Bob shared into team-b; Alice's user-scope write unchanged")
                checks_passed.append("Own-group and user-scope writes work")

            print("\n🗄️  Phase 3: Rows and events carry their true scope...")
            rows = await self._memory_rows()
            assert rows[FORMATION_FACT] == ("formation", FORMATION_ID), rows[FORMATION_FACT]
            assert rows[TEAM_A_FACT] == ("group", "team-a"), rows[TEAM_A_FACT]
            assert rows[TEAM_B_FACT] == ("group", "team-b"), rows[TEAM_B_FACT]
            assert rows[ALICE_USER_FACT][0] == "user", rows[ALICE_USER_FACT]
            print("  ✓ memories rows stamped with their true (scope_type, scope_id)")
            checks_passed.append("Rows carry true scope")

            alice_events = await self.overlord.memory_events.list_events(ALICE)
            shared_events = [e for e in alice_events if e["source"] == "user_edit"]
            event_scopes = {(e["scope_type"], e["scope_id"]) for e in shared_events}
            assert ("formation", FORMATION_ID) in event_scopes, event_scopes
            assert ("group", "team-a") in event_scopes, event_scopes
            print(f"  ✓ memory_events recorded the shared scopes: {sorted(event_scopes)}")
            checks_passed.append("Events record true scope")

            print("\n🔎 Phase 4: Read fan-out (listing + retrieval probe)...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.get(
                    f"{BASE_URL}/memories", headers=self._headers(ALICE), params={"limit": 50}
                )
                assert r.status_code == 200, r.text
                alice_view = {m["content"] for m in r.json()["data"]["memories"]}
                assert FORMATION_FACT in alice_view, alice_view
                assert TEAM_A_FACT in alice_view, alice_view
                assert ALICE_USER_FACT in alice_view, alice_view
                assert TEAM_B_FACT not in alice_view, alice_view
                print("  ✓ Alice lists user + team-a + formation; team-b invisible")

                r = await client.get(
                    f"{BASE_URL}/memories",
                    headers=self._headers(BOB),
                    params={"limit": 50},
                )
                assert r.status_code == 200, r.text
                bob_view = {m["content"] for m in r.json()["data"]["memories"]}
                assert TEAM_B_FACT in bob_view, bob_view
                assert FORMATION_FACT in bob_view, bob_view
                assert TEAM_A_FACT not in bob_view, bob_view
                assert ALICE_USER_FACT not in bob_view, bob_view
                print("  ✓ Bob lists team-b + formation; team-a and Alice's facts invisible")

                # Per-query narrowing restores the user-only view.
                r = await client.get(
                    f"{BASE_URL}/memories",
                    headers=self._headers(ALICE),
                    params={"limit": 50, "scopes": "user"},
                )
                assert r.status_code == 200, r.text
                narrowed = {m["content"] for m in r.json()["data"]["memories"]}
                assert ALICE_USER_FACT in narrowed, narrowed
                assert FORMATION_FACT not in narrowed and TEAM_A_FACT not in narrowed, narrowed
                print("  ✓ scopes=user narrows Alice's listing to her own memories")
            checks_passed.append("Listing fan-out with group isolation")
            checks_passed.append("Per-query narrowing")

            # Vector retrieval probe through the persistent memory manager
            # (no request permissions set -> exercises the registered
            # resolver fallback for membership lookup).
            probe = await self.overlord.persistent_memory_manager.search_long_term_memory(
                query="When does the team ship releases?", k=5, user_id=ALICE
            )
            probe_texts = [p.get("text", "") for p in probe]
            assert any(TEAM_A_FACT in t for t in probe_texts), probe_texts
            assert not any(TEAM_B_FACT in t for t in probe_texts), probe_texts
            probe = await self.overlord.persistent_memory_manager.search_long_term_memory(
                query="What is the refund policy?", k=5, user_id=BOB
            )
            probe_texts = [p.get("text", "") for p in probe]
            assert any(FORMATION_FACT in t for t in probe_texts), probe_texts
            assert not any(TEAM_A_FACT in t for t in probe_texts), probe_texts
            print("  ✓ Vector retrieval fans out per member (resolver-fallback membership)")
            checks_passed.append("Vector fan-out with group isolation")

            print("\n💬 Phase 5: Chat recall of shared facts...")
            # The agent is pinned (2T1 precedent): this test validates the
            # memory fan-out, not LLM routing.
            recall_msg = "How long is our refund window?"
            response = await self.overlord.chat(
                recall_msg,
                agent_name="assistant",
                user_id=ALICE,
                use_async=False,
                stream=False,
            )
            recall_text = response.content if hasattr(response, "content") else str(response)
            transcript.append((recall_msg, recall_text))
            print(f"  Alice: {recall_msg}")
            print(f"  Assistant: {recall_text[:200]}")
            if "30 day" in recall_text.lower():
                print("  ✓ Alice's chat recalled the formation-scope fact")
                checks_passed.append("Chat recall of shared fact")
            else:
                print("  ✗ Chat did not recall the formation fact")
                all_passed = False

            print("\n🔁 Phase 6: Replay reproduces scoped rows...")
            report = await self.overlord.memory_events.rebuild(ALICE, projection="flat_facts")
            print(f"  Rebuild report: {report}")
            rows = await self._memory_rows()
            assert rows[FORMATION_FACT] == ("formation", FORMATION_ID), rows.get(FORMATION_FACT)
            assert rows[TEAM_A_FACT] == ("group", "team-a"), rows.get(TEAM_A_FACT)
            assert rows[TEAM_B_FACT] == ("group", "team-b"), rows.get(TEAM_B_FACT)
            print("  ✓ Wipe-and-replay reproduced the shared rows with their scopes")
            checks_passed.append("Replay reproduces scoped rows")

        except Exception as e:
            import traceback

            print(f"  ✗ Test failed with error: {e}")
            traceback.print_exc()
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🧭 AREA 2U1: SHARED MEMORY SCOPES (NAMESPACES PHASES 2+3)")
        print("=" * 60)

        all_passed = await self.test_shared_scopes()

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Shared writes require a memory.write grant; denials are generic 403s")
        print("- Reads fan out user -> member groups -> formation, membership-gated")
        print("- Events record the write's true scope; replay reproduces scoped rows")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestSharedMemoryScopes()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
