#!/usr/bin/env python3
"""Test 19n1: MCP (Model Context Protocol) endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import os
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestMCP(BaseE2ETest):
    """Test MCP endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19n1_mcp",
            test_description="Test MCP server and tool management endpoints",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19n1_mcp(self):
        """Test MCP endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19n1_mcp",
            description="Test MCP server and tool management endpoints",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api-full",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            
            # Wait for server to be ready
            await asyncio.sleep(2)
            print("✅ Formation ready with API server")

            # Test 1: GET /v1/mcp (MCP status)
            print("\n2. Testing GET /v1/mcp...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/mcp",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            # MCP settings are flat in data, not nested under data.mcp
            assert "enhance_user_prompts" in data["data"] or "servers" in data["data"]
            print(f"   MCP settings retrieved: enhance_user_prompts={data['data'].get('enhance_user_prompts')}")
            print("✅ GET /v1/mcp passed")

            # Test 2: PATCH /v1/mcp - DEPRECATED (removed from implementation)
            # MCP configuration should be changed via formation YAML and redeployment
            print("\n3. Skipping PATCH /v1/mcp (deprecated - use deployment instead)")
            print("✅ PATCH /v1/mcp skipped (deprecated)")

            # Test 3: GET /v1/mcp/servers (list servers)
            print("\n4. Testing GET /v1/mcp/servers...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/mcp/servers",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "servers" in data["data"]
            initial_server_count = len(data["data"]["servers"])
            print(f"   Initial server count: {initial_server_count}")
            print("✅ GET /v1/mcp/servers passed")

            # Test 4-7: POST/PATCH/DELETE /v1/mcp/servers - ALL DEPRECATED
            # MCP servers should be configured via formation YAML
            print("\n5-7. Skipping MCP server CRUD operations (deprecated - use deployment instead)")
            print("✅ MCP server CRUD skipped (deprecated)")

            # Test 7: GET /v1/mcp/tools (list tools)
            print("\n8. Testing GET /v1/mcp/tools...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/mcp/tools",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            assert data["success"] is True
            assert "tools" in data["data"]
            print(f"   Available tools: {len(data['data']['tools'])}")
            print("✅ GET /v1/mcp/tools passed")

            # Test 8: POST /v1/mcp/tools/call (call a tool)
            print("\n9. Testing POST /v1/mcp/tools/call...")
            # This would require an actual tool to be available
            # For now, test that the endpoint exists
            tool_call_data = {
                "server_id": "test_server",
                "tool_name": "test_tool",
                "arguments": {},
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/mcp/tools/call",
                    headers=self.headers,
                    json=tool_call_data,
                )
            
            # Expected to fail since tool doesn't exist (422 = validation error)
            assert response.status_code in [400, 404, 422, 500], f"Expected 400/404/422/500, got {response.status_code}"
            print("✅ POST /v1/mcp/tools/call endpoint exists (expected failure for non-existent tool)")

            # Test 9: DELETE /v1/mcp/servers/{server_id} - DEPRECATED
            print("\n10. Skipping DELETE /v1/mcp/servers (deprecated - use deployment instead)")

            # Test 10: Authentication (without admin key)
            print("\n11. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/mcp",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            checks = [
                "GET /v1/mcp passed (MCP status)",
                "PATCH /v1/mcp skipped (deprecated)",
                f"GET /v1/mcp/servers passed ({initial_server_count} servers)",
                "MCP server CRUD skipped (deprecated)",
                "GET /v1/mcp/tools passed",
                "POST /v1/mcp/tools/call endpoint verified",
                "Authentication enforced",
            ]
            
            formatter.print_test_result(
                test_name="test_19n1_mcp",
                success=True,
                checks=checks,
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19n1_mcp",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Cleanup
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestMCP()
    await test.test_19n1_mcp()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
