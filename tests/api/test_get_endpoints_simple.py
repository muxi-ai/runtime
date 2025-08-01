"""
Simplified tests for GET endpoints that match actual implementation.
"""

import asyncio
import httpx
import pytest
from typing import Dict, Optional
from tests.api.utils import wait_for_server

# Test configuration - matches test-formations/formation-api/formation.yaml
BASE_URL = "http://0.0.0.0:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"
TEST_USER_ID = "test_user_123"


class TestGetEndpointsSimple:
    """Test GET endpoints with actual response validation."""

    @classmethod
    def setup_class(cls):
        """Wait for server to be ready before running tests."""
        if not asyncio.run(wait_for_server(verbose=True)):
            raise RuntimeError("Server failed to start")
        print("\n✅ Server is ready, starting GET endpoint tests...\n")

    async def _test_endpoint(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        expected_status: int = 200,
        expected_object: Optional[str] = None,
        check_fields: Optional[list] = None,
    ):
        """Helper to test an endpoint."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}{path}", headers=headers or {})

            print(f"\nTesting GET {path}")
            print(f"  Status: {response.status_code}")

            assert (
                response.status_code == expected_status
            ), f"Expected {expected_status}, got {response.status_code}"

            if expected_status == 200:
                data = response.json()

                # Check standard envelope fields
                assert "object" in data
                assert "timestamp" in data
                assert "success" in data
                assert "data" in data
                assert "error" in data
                assert data["success"] is True
                assert data["error"] is None

                print(f"  Object: {data['object']}")

                if expected_object:
                    assert data["object"] == expected_object

                if check_fields:
                    for field in check_fields:
                        assert field in data["data"], f"Missing field: {field}"
                        print(f"  ✓ Has {field}")

                print("  ✅ Validated")
                return data

            return None

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health endpoint."""
        await self._test_endpoint(
            "/v1/health",
            expected_object="health",
            check_fields=["status", "version", "formation_id"],
        )

    @pytest.mark.asyncio
    async def test_admin_endpoints(self):
        """Test all admin GET endpoints."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        admin_endpoints = [
            # (path, expected_object, check_fields)
            ("/v1/status", "status", ["formation_id", "agents", "services"]),
            ("/v1/config", "config", ["schema", "id", "description"]),
            ("/v1/overlord", "overlord", ["persona", "llm"]),
            ("/v1/overlord/persona", "persona", ["persona"]),
            ("/v1/agents", "agent_list", None),  # List endpoint
            ("/v1/secrets", "secret_list", None),  # List endpoint
            ("/v1/llm/settings", "llm_settings", ["temperature", "max_tokens"]),
            ("/v1/logging", "logging", ["enabled", "streams"]),
            ("/v1/memory", "memory", ["working", "buffer"]),
            ("/v1/async", "async", ["threshold_seconds", "enable_estimation"]),
            ("/v1/scheduler", "scheduler", ["enabled", "timezone"]),
            ("/v1/a2a", "a2a", ["enabled", "outbound", "inbound"]),
            ("/v1/mcp", "mcp", ["default_retry_attempts", "default_timeout_seconds"]),
            ("/v1/mcp/servers", "mcp_server_list", None),  # List endpoint
        ]

        for path, expected_object, check_fields in admin_endpoints:
            await self._test_endpoint(path, headers, 200, expected_object, check_fields)

    @pytest.mark.asyncio
    async def test_client_endpoints(self):
        """Test client GET endpoints."""
        headers = {"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-Id": TEST_USER_ID}

        client_endpoints = [
            (f"/v1/jobs/{TEST_USER_ID}", "job_list"),
            (f"/v1/memories/{TEST_USER_ID}", "memory_list"),
        ]

        for path, expected_object in client_endpoints:
            data = await self._test_endpoint(path, headers, 200, expected_object)
            # Verify it's a list response
            assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_auth_errors(self):
        """Test authentication error responses."""
        print("\n\nTesting Authentication Errors:")

        # No auth header - expect 403
        await self._test_endpoint("/v1/config", expected_status=403)

        # Wrong key - expect 403
        await self._test_endpoint(
            "/v1/config", headers={"X-Muxi-Admin-Key": "wrong_key"}, expected_status=403
        )

        # Client key on admin endpoint - expect 403
        await self._test_endpoint(
            "/v1/config", headers={"X-Muxi-Client-Key": CLIENT_KEY}, expected_status=403
        )

        print("  ✅ All auth errors return 403 as expected")

    @pytest.mark.asyncio
    async def test_list_endpoints_structure(self):
        """Test that list endpoints return proper list structure."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        list_endpoints = ["/v1/agents", "/v1/secrets", "/v1/mcp/servers"]

        print("\n\nTesting List Endpoints Structure:")
        for path in list_endpoints:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BASE_URL}{path}", headers=headers)
                data = response.json()

                # Check list structure
                assert isinstance(data["data"], list), f"{path} should return a list"
                assert "type" in data, f"{path} should have 'type' field"

                print(f"  ✓ {path} returns list with type: {data['type']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
