#!/usr/bin/env python3
"""Test 20e1: MCP and REST API parity.

Calls the same operations via MCP and REST, then compares responses
to verify the MCP layer faithfully wraps the REST API.
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

from common import BaseE2ETest, TestOutputFormatter


class TestMCPRestParity(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_20e1_rest_parity",
            test_description="MCP tools return same data as REST endpoints",
            test_area="20_mcp_server",
        )
        self.base_url = "http://127.0.0.1:8271"
        self.client_key = "test-client-key"
        self.rest_headers = {
            "X-Muxi-Client-Key": self.client_key,
            "X-Muxi-User-ID": "parity-test-user",
            "Content-Type": "application/json",
        }

    async def test_20e1_rest_parity(self):
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_20e1_rest_parity",
            description="MCP tools return same data as REST endpoints",
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

            async with Client(f"{self.base_url}/mcp") as mcp_client:

                # Test 1: list_sessions parity
                print("\n2. Comparing list_sessions...")
                async with httpx.AsyncClient(timeout=30.0) as http:
                    rest_resp = await http.get(
                        f"{self.base_url}/v1/sessions",
                        headers=self.rest_headers,
                    )
                rest_data = rest_resp.json()

                mcp_result = await mcp_client.call_tool(
                    "list_sessions",
                    {
                        "X-Muxi-User-ID": "parity-test-user",
                    },
                )
                mcp_data = json.loads(mcp_result.content[0].text)

                assert rest_data.get("success") == mcp_data.get("success"), (
                    f"Parity mismatch: REST success={rest_data.get('success')}, "
                    f"MCP success={mcp_data.get('success')}"
                )
                print("  list_sessions: REST and MCP agree")

                # Test 2: list_requests parity
                print("\n3. Comparing list_requests...")
                async with httpx.AsyncClient(timeout=30.0) as http:
                    rest_resp = await http.get(
                        f"{self.base_url}/v1/requests",
                        headers=self.rest_headers,
                    )
                rest_data = rest_resp.json()

                mcp_result = await mcp_client.call_tool(
                    "list_requests",
                    {
                        "X-Muxi-User-ID": "parity-test-user",
                    },
                )
                mcp_data = json.loads(mcp_result.content[0].text)

                rest_count = len(rest_data.get("data", {}).get("requests", []))
                mcp_count = len(mcp_data.get("data", {}).get("requests", []))
                assert (
                    rest_count == mcp_count
                ), f"Request count mismatch: REST={rest_count}, MCP={mcp_count}"
                print(f"  list_requests: both return {rest_count} requests")

                # Test 3: list_sops parity
                print("\n4. Comparing list_sops...")
                async with httpx.AsyncClient(timeout=30.0) as http:
                    rest_resp = await http.get(
                        f"{self.base_url}/v1/sops",
                        headers=self.rest_headers,
                    )
                rest_data = rest_resp.json()

                mcp_result = await mcp_client.call_tool("list_sops", {})
                mcp_data = json.loads(mcp_result.content[0].text)

                assert rest_data.get("success") == mcp_data.get("success")
                rest_sops = rest_data.get("data", {}).get("sops", [])
                mcp_sops = mcp_data.get("data", {}).get("sops", [])
                assert len(rest_sops) == len(
                    mcp_sops
                ), f"SOP count mismatch: REST={len(rest_sops)}, MCP={len(mcp_sops)}"
                print(f"  list_sops: both return {len(rest_sops)} SOPs")

                # Test 4: get_request_status parity (for non-existent ID)
                # Note: REST returns error in response body, MCP raises ToolError for HTTP errors
                print("\n5. Comparing error handling...")
                bad_id = "nonexistent-id"
                async with httpx.AsyncClient(timeout=30.0) as http:
                    rest_resp = await http.get(
                        f"{self.base_url}/v1/requests/{bad_id}",
                        headers=self.rest_headers,
                    )
                rest_data = rest_resp.json()
                assert rest_data.get("success") is False, "REST should return success=False"

                from fastmcp.exceptions import ToolError

                try:
                    mcp_result = await mcp_client.call_tool(
                        "get_request_status",
                        {
                            "request_id": bad_id,
                            "X-Muxi-User-ID": "parity-test-user",
                        },
                    )
                    mcp_data = json.loads(mcp_result.content[0].text)
                    mcp_error = mcp_data.get("success") is False
                except ToolError:
                    mcp_error = True

                assert mcp_error, "MCP should also return error for bad request ID"
                print("  Error handling: both REST and MCP return error for bad request ID")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20e1_rest_parity",
                success=True,
                checks=[
                    "list_sessions: REST and MCP match",
                    "list_requests: REST and MCP match",
                    "list_sops: REST and MCP match",
                    "Error handling: REST and MCP match",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20e1_rest_parity",
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
    test = TestMCPRestParity()
    await test.test_20e1_rest_parity()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
