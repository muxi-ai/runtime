"""
Tests for GET endpoints that validate actual implementation behavior.
This test file documents the ACTUAL response format of each endpoint.
"""

import asyncio
import httpx
import pytest
from tests.api.utils import wait_for_server

# Test configuration
BASE_URL = "http://0.0.0.0:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"
TEST_USER_ID = "test_user_123"


class TestActualGetEndpoints:
    """Test GET endpoints with their actual response formats."""

    @classmethod
    def setup_class(cls):
        """Wait for server to be ready before running tests."""
        if not asyncio.run(wait_for_server(verbose=False)):
            raise RuntimeError("Server failed to start")

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test /v1/health - Returns simple JSON without envelope."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            assert response.status_code == 200

            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
            print("✓ Health endpoint: Simple format {'status': 'healthy'}")

    @pytest.mark.asyncio
    async def test_envelope_endpoints(self):
        """Test endpoints that use the standard envelope format."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        test_cases = [
            # Admin endpoints
            ("/v1/status", "status", ["formation_id", "agents", "uptime_seconds"]),
            ("/v1/config", "config", ["schema", "id", "description", "server", "llm"]),
            ("/v1/overlord", "overlord", ["persona", "llm"]),
            ("/v1/overlord/persona", "persona", ["persona"]),
            ("/v1/llm/settings", "llm_settings", ["temperature", "max_tokens", "timeout_seconds"]),
            ("/v1/logging", "logging", ["system", "conversation"]),
            ("/v1/memory", "memory", ["working", "buffer"]),
            ("/v1/async", "async", ["threshold_seconds", "enable_estimation"]),
            ("/v1/scheduler", "scheduler", ["enabled", "timezone"]),
            ("/v1/a2a", "a2a", ["enabled", "outbound", "inbound"]),
            ("/v1/mcp", "mcp", ["default_retry_attempts", "default_timeout_seconds"]),
        ]

        for path, expected_object, check_fields in test_cases:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BASE_URL}{path}", headers=headers)
                assert response.status_code == 200

                data = response.json()

                # Validate envelope
                assert "object" in data
                assert "timestamp" in data
                assert "success" in data
                assert "error" in data
                assert "data" in data
                assert data["object"] == expected_object
                assert data["success"] is True
                assert data["error"] is None

                # Check specific fields
                for field in check_fields:
                    assert field in data["data"], f"{path}: Missing field {field}"

                print(f"✓ {path}: Standard envelope with object='{expected_object}'")

    @pytest.mark.asyncio
    async def test_list_endpoints(self):
        """Test list endpoints that have custom response structures."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        # Test agent list - returns {agents: [...], count: N}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/agents", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "agent_list"
            assert "agents" in data["data"]
            assert "count" in data["data"]
            assert isinstance(data["data"]["agents"], list)
            print(f"✓ /v1/agents: Returns {{agents: [...], count: {data['data']['count']}}}")

        # Test secrets list - returns {secrets: [...], count: N}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/secrets", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "secret_list"
            assert "secrets" in data["data"]
            assert isinstance(data["data"]["secrets"], list)

            # Check masking
            if data["data"]["secrets"]:
                secret = data["data"]["secrets"][0]
                assert secret["value"] == "********"
            print(f"✓ /v1/secrets: Returns {{secrets: [...], count: {data['data']['count']}}}, values masked")

        # Test MCP servers list - returns {servers: [...], count: N}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/mcp/servers", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "mcp_server_list"
            assert "servers" in data["data"]
            assert isinstance(data["data"]["servers"], list)
            print(f"✓ /v1/mcp/servers: Returns {{servers: [...], count: {data['data']['count']}}}")

    @pytest.mark.asyncio
    async def test_client_endpoints(self):
        """Test client endpoints with user context."""
        headers = {
            "X-Muxi-Client-Key": CLIENT_KEY,
            "X-Muxi-User-Id": TEST_USER_ID
        }

        # Test jobs list - returns {jobs: [...], count: N}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/jobs/{TEST_USER_ID}", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "job_list"
            assert "jobs" in data["data"]
            assert "count" in data["data"]
            assert isinstance(data["data"]["jobs"], list)
            print(f"✓ /v1/jobs/{{user_id}}: Returns {{jobs: [...], count: {data['data']['count']}}}")

        # Test memories list - returns {memories: [...], count: N}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/memories/{TEST_USER_ID}", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "memory_list"
            assert "memories" in data["data"]
            assert isinstance(data["data"]["memories"], list)
            print(f"✓ /v1/memories/{{user_id}}: Returns {{memories: [...], count: {len(data['data']['memories'])}}}")

    @pytest.mark.asyncio
    async def test_error_responses(self):
        """Test error response formats."""
        # No auth - returns 403 with error envelope
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/config")
            assert response.status_code == 403

            data = response.json()
            assert data["object"] == "error"
            assert data["success"] is False
            assert data["error"]["code"] == "FORBIDDEN"
            print("✓ Auth errors: Return 403 with standard error envelope")

    @pytest.mark.asyncio
    async def test_response_summary(self):
        """Print summary of response patterns."""
        print("\n" + "="*60)
        print("RESPONSE FORMAT SUMMARY:")
        print("="*60)
        print("\n1. SPECIAL ENDPOINTS:")
        print("   - /v1/health: Simple JSON {'status': 'healthy'} (no envelope)")
        print("\n2. STANDARD ENVELOPE ENDPOINTS:")
        print("   - All config endpoints return: {object, timestamp, success, error, data}")
        print("   - data contains the actual response fields")
        print("\n3. LIST ENDPOINTS:")
        print("   - Return envelope with data: {<type>s: [...], count: N}")
        print("   - Examples: {agents: [...], count: 4}, {secrets: [...], count: 10}")
        print("\n4. ERROR RESPONSES:")
        print("   - Use standard envelope with success=false")
        print("   - Return 403 (not 401) for auth failures")
        print("   - error field contains: {code, message, trace}")
        print("\n" + "="*60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-k", "test_"])
