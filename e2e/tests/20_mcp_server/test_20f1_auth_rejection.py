#!/usr/bin/env python3
"""Test 20f1: MCP auth rejection.

Verifies that MCP tool calls fail with appropriate errors when no auth
or wrong auth is provided. The MCP endpoint itself is reachable (you can
list tools), but calling any tool without valid credentials must fail.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestMCPAuthRejection(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_20f1_auth_rejection",
            test_description="MCP tool calls fail without valid auth",
            test_area="20_mcp_server",
        )
        self.base_url = "http://127.0.0.1:8271"

    async def test_20f1_auth_rejection(self):
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_20f1_auth_rejection",
            description="MCP tool calls fail without valid auth",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-mcp",
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("  Formation ready")

            from fastmcp import Client
            from fastmcp.client.transports.http import StreamableHttpTransport

            # Test 1: No auth -- tool call should fail with 401
            print("\n2. Calling tool with NO auth (expect failure)...")
            transport_no_auth = StreamableHttpTransport(f"{self.base_url}/mcp/")
            async with Client(transport_no_auth) as client:
                try:
                    result = await client.call_tool(
                        "list_sessions",
                        {"X-Muxi-User-ID": "test-user"},
                    )
                    result_text = result.content[0].text if result.content else ""
                    data = json.loads(result_text)
                    assert (
                        data.get("success") is not True
                    ), f"Tool call without auth should not succeed: {data}"
                    error_msg = str(data.get("error", ""))
                    assert (
                        "401" in error_msg
                        or "unauthorized" in error_msg.lower()
                        or "key" in error_msg.lower()
                    ), f"Expected auth error, got: {data}"
                    print(f"  No-auth call rejected: {error_msg[:100]}")
                except Exception as e:
                    error_str = str(e)
                    assert (
                        "401" in error_str or "unauthorized" in error_str.lower()
                    ), f"Expected 401 error, got: {error_str}"
                    print(f"  No-auth call raised error: {error_str[:100]}")

            # Test 2: Wrong auth -- tool call should fail with 401
            print("\n3. Calling tool with WRONG auth (expect failure)...")
            transport_bad_auth = StreamableHttpTransport(
                f"{self.base_url}/mcp/",
                headers={"X-Muxi-Client-Key": "invalid-test-value"},
            )
            async with Client(transport_bad_auth) as client:
                try:
                    result = await client.call_tool(
                        "list_sessions",
                        {"X-Muxi-User-ID": "test-user"},
                    )
                    result_text = result.content[0].text if result.content else ""
                    data = json.loads(result_text)
                    assert (
                        data.get("success") is not True
                    ), f"Tool call with wrong auth should not succeed: {data}"
                    error_msg = str(data.get("error", ""))
                    assert (
                        "401" in error_msg
                        or "unauthorized" in error_msg.lower()
                        or "key" in error_msg.lower()
                    ), f"Expected auth error, got: {data}"
                    print(f"  Wrong-auth call rejected: {error_msg[:100]}")
                except Exception as e:
                    error_str = str(e)
                    assert (
                        "401" in error_str or "unauthorized" in error_str.lower()
                    ), f"Expected 401 error, got: {error_str}"
                    print(f"  Wrong-auth call raised error: {error_str[:100]}")

            # Test 3: Correct auth -- tool call should succeed (sanity check)
            print("\n4. Calling tool with CORRECT auth (expect success)...")
            transport_good_auth = StreamableHttpTransport(
                f"{self.base_url}/mcp/",
                headers={"X-Muxi-Client-Key": "test-client-key"},
            )
            async with Client(transport_good_auth) as client:
                result = await client.call_tool(
                    "list_sessions",
                    {"X-Muxi-User-ID": "test-user"},
                )
                result_text = result.content[0].text if result.content else ""
                data = json.loads(result_text)
                assert data.get("success") is True, f"Expected success with correct auth: {data}"
                print("  Correct-auth call succeeded")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20f1_auth_rejection",
                success=True,
                checks=[
                    "Tool call with no auth rejected (401)",
                    "Tool call with wrong auth rejected (401)",
                    "Tool call with correct auth succeeds",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20f1_auth_rejection",
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
    test = TestMCPAuthRejection()
    await test.test_20f1_auth_rejection()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
