#!/usr/bin/env python3
"""Test 19x4: allow/deny tools vocabulary across the override cascade.

Covers the registry/agent-level unification with the group-level GBAC
semantics (tools vocabulary unification):

- formation ``mcp.servers[].tools`` accepts canonical ``allow`` + ``deny``
  together (relaxed mutex): the registered catalog is allow minus deny,
  with deny winning on overlap
- an agent attaches a formation-declared server with the new
  ``{id, tools}`` reference form; the override (alias spelling
  ``blacklist``) chains after the registry bound and narrows the agent's
  tool registry without touching the shared catalog
- a group per-agent ``allow`` supersedes the attachment override
  (``create_record`` comes back) but cannot resurrect registry-pruned
  tools (``drop_database`` / ``delete_records`` stay out) -- both via the
  resolver and via the enforcement helper the chat path uses
- a ``tools`` block declaring a canonical key and its alias fails
  formation load fail-fast

The MCP stub (``records_server.py``) runs over stdio with a six-tool
catalog; the formation launches it with a path relative to the e2e
directory, so the test pins its working directory there first.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

E2E_DIR = Path(__file__).parent.parent.parent
os.chdir(E2E_DIR)  # the formation launches the MCP stub via an e2e-relative path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter  # noqa: E402

from muxi.runtime.services.gbac import enforcement as gbac_enforcement  # noqa: E402
from muxi.runtime.services.memory.long_term import UserGroup  # noqa: E402

ANALYST_USER = "alice@example.com"
FORMATION_ID = "api-test-tools-vocab"

# What each cascade level should leave visible (see formation.yaml/groups/)
REGISTRY_CATALOG = {"get_records", "list_records", "search_records", "create_record"}
ATTACHMENT_VIEW = {"get_records", "list_records", "search_records"}
GROUP_EFFECTIVE = {"get_records", "create_record"}


class TestToolsVocabulary(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_19x4_tools_vocabulary",
            test_description="Test allow/deny tools vocabulary across the override cascade",
            test_area="19_api",
        )

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
        self.formation.permission_resolver.invalidate_memberships(user_id)

    async def test_19x4_tools_vocabulary(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(
            test_name="test_19x4_tools_vocabulary",
            description="Test allow/deny tools vocabulary across the override cascade",
        )
        checks = []
        try:
            print("\n1. Starting formation with allow+deny registry filter and")
            print("   an {id, tools} agent attachment override...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api-tools-vocab"
            )
            await asyncio.sleep(2)
            mcp_service = self.overlord.mcp_service
            print("✅ Formation loaded, MCP stub registered")
            checks.append("formation with allow/deny vocabulary loads")

            print("\n2. Registry level: allow+deny together prune the shared catalog...")
            shared = mcp_service.agent_tool_registry["_shared"]["records-mcp"]
            assert set(shared) == REGISTRY_CATALOG, f"shared catalog: {sorted(shared)}"
            print(f"✅ Shared catalog: {sorted(shared)}")
            print("   (delete_records denied despite matching allow; drop_database never allowed)")
            checks.append("registry allow+deny prunes catalog (deny wins on overlap)")

            print("\n3. Attachment level: {id, tools} reference narrows the agent view...")
            agent_view = mcp_service.get_tool_registry("assistant")["records-mcp"]
            assert set(agent_view) == ATTACHMENT_VIEW, f"agent view: {sorted(agent_view)}"
            print(f"✅ Agent view: {sorted(agent_view)} (blacklist alias removed create_record)")
            checks.append("{id, tools} attachment override narrows agent registry")

            print("\n4. Seeding analyst membership and resolving the cascade...")
            await self._seed_membership(ANALYST_USER, "analyst")
            resolver = self.formation.permission_resolver
            assert resolver is not None, "permission_resolver not constructed"
            perms = await resolver.resolve(ANALYST_USER)
            effective = perms.effective_tools(
                "assistant",
                "records-mcp",
                inherited_tools=sorted(agent_view),
                catalog=sorted(shared),
            )
            assert effective == GROUP_EFFECTIVE, f"effective: {sorted(effective)}"
            print(f"✅ Group allow supersedes the attachment ({sorted(effective)})")
            print("   create_record restored; drop_database/delete_records stay registry-pruned")
            checks.append("group allow supersedes attachment, not the registry bound")

            print("\n5. Enforcement helper (chat path) applies the same cascade...")
            token = gbac_enforcement.set_current_permissions(perms)
            try:
                narrowed = gbac_enforcement.effective_tool_registry(
                    "assistant",
                    {"records-mcp": dict(agent_view)},
                    catalogs={"records-mcp": dict(shared)},
                )
            finally:
                gbac_enforcement.reset_current_permissions(token)
            assert set(narrowed.get("records-mcp", {})) == GROUP_EFFECTIVE, narrowed
            print("✅ effective_tool_registry matches the resolver cascade")
            checks.append("enforcement helper feeds the cascade the same way")

            await self.cleanup_formation()
            self.formation = None
            self.overlord = None
            await asyncio.sleep(2)

            print("\n6. Alias conflict (allow + whitelist) fails formation load...")
            from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
            from muxi.runtime.formation import Formation

            failed = False
            try:
                bad = Formation()
                await bad.load(str(Path(__file__).parent / "formation-api-tools-vocab-conflict"))
            except ConfigurationValidationError as e:
                failed = True
                message = str(e)
                assert "alias" in message, message
                assert "allow" in message and "whitelist" in message, message
                print("✅ Load failed with a clear alias-conflict error")
                checks.append("canonical+alias conflict fails formation load")
            assert failed, "alias-conflict formation loaded but should have failed"

            formatter.print_test_result(
                test_name="test_19x4_tools_vocabulary",
                success=True,
                checks=checks,
                transcript=[],
                duration=time.time() - start_time,
            )
            print("\nSUCCESS")
        except Exception as e:
            formatter.print_test_result(
                test_name="test_19x4_tools_vocabulary",
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
    await TestToolsVocabulary().test_19x4_tools_vocabulary()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
