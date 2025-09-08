#!/usr/bin/env python3
"""
Test GET endpoints against a running Formation API Server.

This script assumes the server is already running (e.g., via utils/start_test_server.py).
You can specify the server URL and admin key via environment variables:
    API_SERVER_URL=http://localhost:3000
    ADMIN_API_KEY=your_admin_key

Usage:
    python tests/api/test_running_server.py
"""

import os
import httpx
import json
import asyncio
from typing import Dict


# Configuration from environment or defaults
SERVER_URL = os.environ.get("API_SERVER_URL", "http://127.0.0.1:8271")
ADMIN_KEY = os.environ.get("ADMIN_API_KEY", None)


async def test_endpoint(client: httpx.AsyncClient, endpoint: str, headers: Dict[str, str]) -> None:
    """Test a single GET endpoint."""
    url = f"{SERVER_URL}/v1{endpoint}"
    print(f"\n{'='*60}")
    print(f"Testing GET {endpoint}")
    print(f"{'='*60}")

    try:
        response = await client.get(url, headers=headers)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Verify response structure
            assert "success" in data, "Missing 'success' field"
            assert data["success"] is True, "Request was not successful"
            assert "data" in data, "Missing 'data' field"
            assert "error" in data, "Missing 'error' field"
            assert data["error"] is None, "Unexpected error in response"
            assert "timestamp" in data, "Missing 'timestamp' field"
            assert "type" in data, "Missing 'type' field"
            assert "object" in data, "Missing 'object' field"

            print("✓ Response structure valid")
            print(f"✓ Type: {data['type']}")
            print(f"✓ Object: {data['object']}")

            # Print the actual data returned
            print("\nData returned:")
            data_str = json.dumps(data['data'], indent=2)
            # Truncate if too long
            if len(data_str) > 500:
                print(data_str[:500] + "\n... (truncated)")
            else:
                print(data_str)

            # Specific checks for certain endpoints
            if endpoint == "/overlord/persona":
                assert "persona" in data['data'], "Missing persona in response"
                persona = data['data']['persona']
                print(f"✓ Persona: {persona[:50]}..." if len(persona) > 50 else f"✓ Persona: {persona}")

            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


async def main():
    """Run all endpoint tests."""
    print(f"Testing Formation API Server at: {SERVER_URL}")

    # If no admin key provided, try to get it from the server's health endpoint
    if not ADMIN_KEY:
        print("\nNo ADMIN_API_KEY provided. Please set it as an environment variable.")
        print("You can find it in the server startup logs.")
        return

    headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

    # First test if server is reachable
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        try:
            response = await client.get(f"{SERVER_URL}/v1/health")
            if response.status_code != 200:
                print(f"✗ Server health check failed: {response.status_code}")
                return
            print("✓ Server is healthy")
        except Exception as e:
            print(f"✗ Cannot connect to server at {SERVER_URL}: {e}")
            return

        # Test all GET endpoints
        endpoints = [
            "/overlord",
            "/overlord/persona",
            "/mcp",
            "/llm/settings",
            "/logging",
            "/memory",
            "/async",
            "/scheduler",
            "/a2a",
            "/agents",
            "/mcp/servers",
            "/config",
            "/status",
        ]

        success_count = 0
        for endpoint in endpoints:
            result = await test_endpoint(client, endpoint, headers)
            if result:
                success_count += 1

        print(f"\n{'='*60}")
        print(f"Test Summary: {success_count}/{len(endpoints)} endpoints passed")
        print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
