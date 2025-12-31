#!/usr/bin/env python3
"""
Comprehensive tests for all GET endpoints in the Formation API.

This test suite validates that all GET endpoints return responses
that match the OpenAPI specification defined in schemas/api/formation-api-v1.yaml
"""

import asyncio
import httpx
import pytest
from typing import Dict, Any, Optional
from tests.unit.api.utils.wait_for_server import wait_for_server

# Test configuration
BASE_URL = "http://0.0.0.0:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"
TEST_USER_ID = "test_user_123"


class TestGetEndpoints:
    """Test all GET endpoints defined in the OpenAPI spec."""

    @classmethod
    def setup_class(cls):
        """Wait for server to be ready before running tests."""
        if not asyncio.run(wait_for_server(verbose=True)):
            raise RuntimeError("Server failed to start")
        print("\n✅ Server is ready, starting GET endpoint tests...\n")

    async def _make_get_request(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        expected_status: int = 200
    ) -> Dict[str, Any]:
        """Helper to make GET requests and validate response envelope."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}{path}",
                headers=headers or {}
            )

            print(f"GET {path} -> {response.status_code}")

            # Check status code
            assert response.status_code == expected_status, \
                f"Expected {expected_status}, got {response.status_code}: {response.text}"

            # Parse JSON response
            data = response.json()

            # Validate response envelope structure
            assert "object" in data, "Response missing 'object' field"
            assert "timestamp" in data, "Response missing 'timestamp' field"
            assert "success" in data, "Response missing 'success' field"
            assert "data" in data, "Response missing 'data' field"
            assert "error" in data, "Response missing 'error' field"

            # For successful responses
            if expected_status == 200:
                assert data["success"] is True, "Success should be True for 200 responses"
                assert data["error"] is None, "Error should be None for successful responses"

            return data

    # Health & Status Tests
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test GET /v1/health - No auth required."""
        data = await self._make_get_request("/v1/health")

        # Validate health response
        assert data["object"] == "health"
        assert data["data"]["status"] == "healthy"
        assert "version" in data["data"]
        assert "formation_id" in data["data"]
        print("  ✅ Health endpoint validated")

    @pytest.mark.asyncio
    async def test_status_endpoint(self):
        """Test GET /v1/status - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/status", headers)

        # Validate status response
        assert data["object"] == "formation_status"
        status_data = data["data"]
        assert "formation_id" in status_data
        assert "agents" in status_data
        assert "services" in status_data
        assert "uptime_seconds" in status_data
        print("  ✅ Status endpoint validated")

    @pytest.mark.asyncio
    async def test_config_endpoint(self):
        """Test GET /v1/config - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/config", headers)

        # Validate config response
        assert data["object"] == "formation_config"
        config_data = data["data"]
        assert "schema" in config_data
        assert "id" in config_data
        assert "description" in config_data
        assert "server" in config_data
        assert "llm" in config_data
        print("  ✅ Config endpoint validated")

    # Overlord Tests
    @pytest.mark.asyncio
    async def test_overlord_config(self):
        """Test GET /v1/overlord - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/overlord", headers)

        assert data["object"] == "overlord_config"
        overlord_data = data["data"]
        assert "persona" in overlord_data
        assert "llm" in overlord_data
        print("  ✅ Overlord config endpoint validated")

    @pytest.mark.asyncio
    async def test_overlord_persona(self):
        """Test GET /v1/overlord/persona - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/overlord/persona", headers)

        assert data["object"] == "overlord_persona"
        assert "persona" in data["data"]
        print("  ✅ Overlord persona endpoint validated")

    # Agent Tests
    @pytest.mark.asyncio
    async def test_list_agents(self):
        """Test GET /v1/agents - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/agents", headers)

        assert data["object"] == "list"
        assert data["type"] == "agent"
        assert isinstance(data["data"], list)
        if data["data"]:
            # Validate agent structure
            agent = data["data"][0]
            assert "id" in agent
            assert "name" in agent
            assert "description" in agent
            assert "status" in agent
        print("  ✅ List agents endpoint validated")

    # Secret Tests
    @pytest.mark.asyncio
    async def test_list_secrets(self):
        """Test GET /v1/secrets - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/secrets", headers)

        assert data["object"] == "list"
        assert data["type"] == "secret"
        assert isinstance(data["data"], list)
        if data["data"]:
            # Validate secret structure
            secret = data["data"][0]
            assert "key" in secret
            assert "value" in secret
            assert secret["value"] == "********"  # Should be masked
        print("  ✅ List secrets endpoint validated")

    # LLM Tests
    @pytest.mark.asyncio
    async def test_llm_settings(self):
        """Test GET /v1/llm/settings - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/llm/settings", headers)

        assert data["object"] == "llm_settings"
        settings = data["data"]
        assert "temperature" in settings
        assert "max_tokens" in settings
        assert "timeout_seconds" in settings
        print("  ✅ LLM settings endpoint validated")

    # Logging Tests
    @pytest.mark.asyncio
    async def test_logging_config(self):
        """Test GET /v1/logging - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/logging", headers)

        assert data["object"] == "logging_config"
        assert "system" in data["data"]
        assert "conversation" in data["data"]
        print("  ✅ Logging config endpoint validated")

    # Memory Tests
    @pytest.mark.asyncio
    async def test_memory_config(self):
        """Test GET /v1/memory - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/memory", headers)

        assert data["object"] == "memory_config"
        memory_data = data["data"]
        assert "working" in memory_data
        assert "buffer" in memory_data
        print("  ✅ Memory config endpoint validated")

    # Async Tests
    @pytest.mark.asyncio
    async def test_async_settings(self):
        """Test GET /v1/async - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/async", headers)

        assert data["object"] == "async_settings"
        async_data = data["data"]
        assert "threshold_seconds" in async_data
        assert "enable_estimation" in async_data
        print("  ✅ Async settings endpoint validated")

    # Scheduler Tests
    @pytest.mark.asyncio
    async def test_scheduler_settings(self):
        """Test GET /v1/scheduler - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/scheduler", headers)

        assert data["object"] == "scheduler_settings"
        scheduler_data = data["data"]
        assert "enabled" in scheduler_data
        assert "timezone" in scheduler_data
        print("  ✅ Scheduler settings endpoint validated")

    # A2A Tests
    @pytest.mark.asyncio
    async def test_a2a_settings(self):
        """Test GET /v1/a2a - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/a2a", headers)

        assert data["object"] == "a2a_settings"
        a2a_data = data["data"]
        assert "enabled" in a2a_data
        assert "outbound" in a2a_data
        assert "inbound" in a2a_data
        print("  ✅ A2A settings endpoint validated")

    # MCP Tests
    @pytest.mark.asyncio
    async def test_mcp_defaults(self):
        """Test GET /v1/mcp - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/mcp", headers)

        assert data["object"] == "mcp_defaults"
        mcp_data = data["data"]
        assert "default_retry_attempts" in mcp_data
        assert "default_timeout_seconds" in mcp_data
        print("  ✅ MCP defaults endpoint validated")

    @pytest.mark.asyncio
    async def test_list_mcp_servers(self):
        """Test GET /v1/mcp/servers - Admin auth required."""
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        data = await self._make_get_request("/v1/mcp/servers", headers)

        assert data["object"] == "list"
        assert data["type"] == "mcp_server"
        assert isinstance(data["data"], list)
        print("  ✅ List MCP servers endpoint validated")

    # Client Endpoints Tests
    @pytest.mark.asyncio
    async def test_list_jobs(self):
        """Test GET /v1/jobs/{user_id} - Client auth required."""
        headers = {
            "X-Muxi-Client-Key": CLIENT_KEY,
            "X-Muxi-User-Id": TEST_USER_ID
        }
        data = await self._make_get_request(f"/v1/jobs/{TEST_USER_ID}", headers)

        assert data["object"] == "list"
        assert data["type"] == "job"
        assert isinstance(data["data"], list)
        print("  ✅ List jobs endpoint validated")

    @pytest.mark.asyncio
    async def test_get_memories(self):
        """Test GET /v1/memories/{user_id} - Client auth required."""
        headers = {
            "X-Muxi-Client-Key": CLIENT_KEY,
            "X-Muxi-User-Id": TEST_USER_ID
        }
        data = await self._make_get_request(f"/v1/memories/{TEST_USER_ID}", headers)

        assert data["object"] == "list"
        assert data["type"] == "memory"
        assert isinstance(data["data"], list)
        print("  ✅ Get memories endpoint validated")

    # Error Cases
    @pytest.mark.asyncio
    async def test_unauthorized_admin_endpoint(self):
        """Test admin endpoint without auth returns 401."""
        await self._make_get_request("/v1/config", expected_status=401)
        print("  ✅ Unauthorized admin access properly rejected")

    @pytest.mark.asyncio
    async def test_unauthorized_client_endpoint(self):
        """Test client endpoint without auth returns 401."""
        await self._make_get_request(f"/v1/jobs/{TEST_USER_ID}", expected_status=401)
        print("  ✅ Unauthorized client access properly rejected")

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """Test invalid API key returns 401."""
        headers = {"X-Muxi-Admin-Key": "invalid_key"}
        await self._make_get_request("/v1/config", headers, expected_status=401)
        print("  ✅ Invalid API key properly rejected")


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "-s"])
