#!/usr/bin/env python3
"""Test 20a1: MCP server endpoint reachability.

Verifies the MCP server is mounted at /mcp and responds to HTTP requests.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter


class TestMCPEndpointReachability(BaseE2ETest):

    def __init__(self):
        super().__init__(
            test_name="test_20a1_endpoint_reachability",
            test_description="MCP server endpoint is reachable at /mcp",
            test_area="20_mcp_server",
        )
        self.base_url = "http://127.0.0.1:8271"

    async def test_20a1_endpoint_reachability(self):
        formatter = TestOutputFormatter()
        start_time = time.time()

        formatter.print_test_header(
            test_name="test_20a1_endpoint_reachability",
            description="MCP server endpoint is reachable at /mcp",
        )

        try:
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-mcp",
            )
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("  Formation ready with API server")

            # Test 1: /mcp endpoint responds (GET returns 406 since MCP requires SSE accept)
            print("\n2. Testing GET /mcp/ (expect MCP response)...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/mcp/")
            # MCP server responds -- 406 means it's alive but requires SSE headers
            assert response.status_code in [
                200,
                405,
                406,
            ], f"Expected 200, 405 or 406, got {response.status_code}: {response.text[:200]}"
            print(f"  GET /mcp/ returned {response.status_code} (MCP endpoint is alive)")

            # Test 2: POST /mcp/ with MCP initialize request (JSON-RPC)
            print("\n3. Testing POST /mcp/ with MCP initialize...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "e2e-test", "version": "1.0.0"},
                        },
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                )
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}: {response.text[:300]}"
            # Response may be SSE or JSON depending on server config
            body = response.text
            assert (
                "serverInfo" in body or "result" in body or "event" in body
            ), f"Expected MCP initialize response, got: {body[:300]}"
            print("  POST /mcp initialize returned 200")
            print("  Response contains MCP server info")

            # Test 3: REST API still works alongside MCP
            print("\n4. Verifying REST API at /v1/health still works...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["healthy", "unhealthy"]
            print(f"  REST API healthy: {data['status']}")

            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20a1_endpoint_reachability",
                success=True,
                checks=[
                    "MCP endpoint responds at /mcp",
                    "MCP initialize handshake works",
                    "REST API coexists at /v1/*",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_20a1_endpoint_reachability",
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
    test = TestMCPEndpointReachability()
    await test.test_20a1_endpoint_reachability()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
