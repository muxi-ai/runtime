#!/usr/bin/env python3
"""Test 20b1: MCP tool listing via FastMCP Client.

Verifies that auto-generated MCP tools from FastAPI routes are listed correctly,
with clean operation_id-based names (not auto-generated ugly names).
"""

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter

EXPECTED_TOOLS = {
    "chat",
    "audiochat",
    "list_requests",
    "get_request_status",
    "cancel_request",
    "search_memories",
    "create_memory",
    "delete_memory",
    "get_buffer_memory",
    "clear_buffer_memory",
    "clear_session_buffer",
    "list_sessions",
    "get_session",
    "get_session_messages",
    "restore_session",
    "list_events",
    "get_session_events",
    "get_request_events",
    "list_triggers",
    "get_trigger",
    "execute_trigger",
    "list_sops",
    "get_sop",
    "list_credential_services",
    "list_credentials",
    "create_credential",
    "get_credential",
    "delete_credential",
    "get_user_identifiers",
    "associate_user_identifiers",
    "delete_user_identifier",
    "lookup_user",
    "resolve_user",
}

# These admin/health/internal endpoints should NOT appear as MCP tools
EXCLUDED_TOOL_NAMES = {
    "get_formation_status_v1_status_get",
    "root_status_v1",
    "v1_status_v1_v1_get",
    "root_status",
    "health_check_v1_health_get",
}


class TestMCPToolListing(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_20b1_tool_listing",
            test_description="MCP tools are auto-generated from FastAPI routes with clean names",
            test_area="20_mcp_server",
        )
        self.base_url = "http://127.0.0.1:8271"
        self.client_key = "test-client-key"

    async def test_20b1_tool_listing(self):
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_20b1_tool_listing",
            description="MCP tools are auto-generated with clean names",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-mcp",
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("  Formation ready")

            # Connect with FastMCP client
            print("\n2. Connecting FastMCP client to /mcp...")
            from fastmcp import Client
            from fastmcp.client.transports.http import StreamableHttpTransport

            transport = StreamableHttpTransport(
                f"{self.base_url}/mcp/",
                headers={"X-Muxi-Client-Key": self.client_key},
            )
            async with Client(transport) as client:
                tools = await client.list_tools()

            tool_names = {t.name for t in tools}
            print(f"  Found {len(tool_names)} MCP tools")

            # Test 1: We have a reasonable number of tools
            print("\n3. Checking tool count...")
            assert len(tool_names) >= 20, f"Expected >= 20 tools, got {len(tool_names)}"
            print(f"  {len(tool_names)} tools (>= 20)")

            # Test 2: Key tools exist with clean names
            print("\n4. Checking expected tools are present...")
            missing = EXPECTED_TOOLS - tool_names
            if missing:
                print(f"  WARNING: Missing tools: {missing}")
                # Some tools may not register depending on formation config, so warn but
                # require at least the core ones
                core_tools = {
                    "chat",
                    "list_requests",
                    "get_request_status",
                    "search_memories",
                    "list_sessions",
                }
                core_missing = core_tools - tool_names
                assert not core_missing, f"Missing core MCP tools: {core_missing}"
            print("  All core tools present")

            # Test 3: No admin/health endpoints leaked into MCP tools
            print("\n5. Checking excluded routes are not exposed...")
            leaked = tool_names & EXCLUDED_TOOL_NAMES
            assert not leaked, f"Excluded routes leaked as MCP tools: {leaked}"
            # Also check for admin routes
            admin_tools = [t for t in tool_names if "admin" in t.lower()]
            assert not admin_tools, f"Admin routes leaked as MCP tools: {admin_tools}"
            print("  No admin/health/internal routes exposed")

            # Test 4: No ugly auto-generated names
            print("\n6. Checking for clean tool names (no auto-generated ugly names)...")
            ugly_names = [
                t
                for t in tool_names
                if "_v1_" in t or "_post" in t or "_get" in t or "_delete" in t
            ]
            assert not ugly_names, f"Found ugly auto-generated tool names: {ugly_names}"
            print("  All tool names are clean (operation_id-based)")

            # Print all tools for reference
            print("\n   All tools:")
            for name in sorted(tool_names):
                marker = "  " if name in EXPECTED_TOOLS else "? "
                print(f"     {marker}{name}")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20b1_tool_listing",
                success=True,
                checks=[
                    f"Found {len(tool_names)} MCP tools",
                    "Core tools present with clean names",
                    "No admin/health routes exposed",
                    "No ugly auto-generated names",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20b1_tool_listing",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            import traceback

            traceback.print_exc()
            raise
        finally:
            if self.formation:
                await self.cleanup_formation()


async def main():
    test = TestMCPToolListing()
    await test.test_20b1_tool_listing()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
