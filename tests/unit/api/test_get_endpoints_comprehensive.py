"""
Comprehensive tests for all GET endpoints documenting actual behavior.

This test suite validates the actual response format of each endpoint
and serves as living documentation of the API.
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


def print_test_header(title: str):
    """Print a formatted test section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


class TestFormationAPIGetEndpoints:
    """Comprehensive tests for Formation API GET endpoints."""

    @classmethod
    def setup_class(cls):
        """Wait for server to be ready before running tests."""
        if not asyncio.run(wait_for_server(verbose=False)):
            raise RuntimeError("Server failed to start")
        print_test_header("FORMATION API GET ENDPOINT TESTS")

    # =================================================================
    # HEALTH & STATUS ENDPOINTS
    # =================================================================

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """
        GET /v1/health - Health check endpoint

        Response format: Simple JSON (no envelope)
        {
            "status": "healthy"
        }
        """
        print_test_header("Health Endpoint")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            assert response.status_code == 200

            data = response.json()
            assert data == {"status": "healthy"}

            print("✓ GET /v1/health")
            print("  Response: {'status': 'healthy'}")
            print("  Note: No envelope format, just simple JSON")

    @pytest.mark.asyncio
    async def test_status_endpoint(self):
        """
        GET /v1/status - Formation status

        Requires: Admin auth
        Response: Standard envelope with formation runtime info
        """
        print_test_header("Status Endpoint")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/status", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "status"
            assert data["success"] is True

            status = data["data"]
            assert "formation_id" in status
            assert "agents" in status
            assert "uptime_seconds" in status

            print("✓ GET /v1/status")
            print(f"  Formation ID: {status['formation_id']}")
            print(
                f"  Agents: {status['agents']['total']} total, {status['agents']['active']} active"
            )
            print(f"  Uptime: {status['uptime_seconds']} seconds")

    # =================================================================
    # CONFIGURATION ENDPOINTS
    # =================================================================

    @pytest.mark.asyncio
    async def test_config_endpoint(self):
        """
        GET /v1/config - Formation configuration summary

        Requires: Admin auth
        Response: Resource links, not full config
        """
        print_test_header("Configuration Endpoint")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/config", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "config"

            config = data["data"]
            # Returns resource summary, not actual config
            assert "agents" in config
            assert "resource" in config["agents"]
            assert config["agents"]["resource"] == "/v1/agents"

            print("✓ GET /v1/config")
            print("  Note: Returns resource summary with links, not full config")
            print("  Resources:")
            for key, value in config.items():
                if isinstance(value, dict) and "resource" in value:
                    print(f"    - {key}: {value['resource']} (total: {value.get('total', 'N/A')})")

    @pytest.mark.asyncio
    async def test_overlord_endpoints(self):
        """Test Overlord configuration endpoints."""
        print_test_header("Overlord Endpoints")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        # Test /v1/overlord
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/overlord", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "overlord"
            assert "persona" in data["data"]
            assert "llm" in data["data"]

            print("✓ GET /v1/overlord")
            print(f"  Persona: {data['data']['persona'][:50]}...")
            print(f"  LLM Model: {data['data']['llm'].get('model', 'default')}")

        # Test /v1/overlord/persona
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/overlord/persona", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "persona"
            assert "persona" in data["data"]

            print("✓ GET /v1/overlord/persona")
            print("  Returns just the persona text")

    # =================================================================
    # LIST ENDPOINTS
    # =================================================================

    @pytest.mark.asyncio
    async def test_agent_list_endpoint(self):
        """
        GET /v1/agents - List all agents

        Response format: {agents: [...], count: N}
        """
        print_test_header("Agent List Endpoint")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/agents", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "agent_list"
            assert "agents" in data["data"]
            assert "count" in data["data"]

            agents = data["data"]["agents"]
            print("✓ GET /v1/agents")
            print(f"  Total agents: {data['data']['count']}")
            for agent in agents:
                print(f"    - {agent['id']}: {agent['name']} ({agent['status']})")

    @pytest.mark.asyncio
    async def test_secret_list_endpoint(self):
        """
        GET /v1/secrets - List all secrets (masked)

        Response format: {secrets: {key: "••••••••", ...}, count: N}
        """
        print_test_header("Secret List Endpoint")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/secrets", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "secret_list"
            assert "secrets" in data["data"]
            assert "count" in data["data"]

            secrets = data["data"]["secrets"]
            print("✓ GET /v1/secrets")
            print(f"  Total secrets: {data['data']['count']}")
            print("  Note: Returns dict of key->masked_value, not array")
            print("  Sample keys:")
            for i, key in enumerate(list(secrets.keys())[:5]):
                print(f"    - {key}: {secrets[key]}")

    @pytest.mark.asyncio
    async def test_mcp_endpoints(self):
        """Test MCP-related endpoints."""
        print_test_header("MCP Endpoints")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        # Test /v1/mcp - defaults
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/mcp", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "mcp"
            mcp_config = data["data"]

            print("✓ GET /v1/mcp")
            print(f"  Default retry attempts: {mcp_config['default_retry_attempts']}")
            print(f"  Default timeout: {mcp_config['default_timeout_seconds']}s")
            print(f"  Max tool iterations: {mcp_config['max_tool_iterations']}")

        # Test /v1/mcp/servers - list
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/mcp/servers", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "mcp_server_list"
            assert "servers" in data["data"]

            print("✓ GET /v1/mcp/servers")
            print(f"  Total servers: {data['data']['count']}")

    # =================================================================
    # SERVICE CONFIGURATION ENDPOINTS
    # =================================================================

    @pytest.mark.asyncio
    async def test_service_config_endpoints(self):
        """Test various service configuration endpoints."""
        print_test_header("Service Configuration Endpoints")

        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}

        endpoints = [
            ("/v1/llm/settings", "llm_settings", ["temperature", "max_tokens"]),
            ("/v1/logging", "logging", ["system", "conversation"]),
            ("/v1/memory", "memory", ["working", "buffer"]),
            ("/v1/async", "async", ["threshold_seconds", "enable_estimation"]),
            ("/v1/scheduler", "scheduler", ["enabled", "timezone"]),
            ("/v1/a2a", "a2a", ["enabled", "outbound", "inbound"]),
        ]

        for path, expected_object, check_fields in endpoints:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BASE_URL}{path}", headers=headers)
                assert response.status_code == 200

                data = response.json()
                assert data["object"] == expected_object

                print(f"✓ GET {path}")
                for field in check_fields:
                    if field in data["data"]:
                        value = data["data"][field]
                        print(f"    {field}: {value}")

    # =================================================================
    # CLIENT ENDPOINTS
    # =================================================================

    @pytest.mark.asyncio
    async def test_client_endpoints(self):
        """Test client endpoints requiring user context."""
        print_test_header("Client Endpoints")

        headers = {"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-Id": TEST_USER_ID}

        # Test jobs endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/jobs/{TEST_USER_ID}", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "job_list"
            assert "jobs" in data["data"]

            print(f"✓ GET /v1/jobs/{TEST_USER_ID}")
            print(f"  Jobs for user: {data['data']['count']}")

        # Test memories endpoint
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/memories/{TEST_USER_ID}", headers=headers)
            assert response.status_code == 200

            data = response.json()
            assert data["object"] == "memory_list"
            assert "memories" in data["data"]

            print(f"✓ GET /v1/memories/{TEST_USER_ID}")
            print(f"  Memories for user: {len(data['data']['memories'])}")

    # =================================================================
    # ERROR HANDLING
    # =================================================================

    @pytest.mark.asyncio
    async def test_error_responses(self):
        """Test error response formats."""
        print_test_header("Error Response Formats")

        # No auth
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/config")
            assert response.status_code == 403

            data = response.json()
            assert data["object"] == "error"
            assert data["success"] is False
            assert data["error"]["code"] == "FORBIDDEN"

            print("✓ Missing auth returns 403 (not 401)")
            print(f"  Error code: {data['error']['code']}")
            print(f"  Message: {data['error']['message']}")

        # Invalid key
        headers = {"X-Muxi-Admin-Key": "invalid"}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/config", headers=headers)
            assert response.status_code == 403

            print("✓ Invalid auth also returns 403")

        # Wrong key type
        headers = {"X-Muxi-Client-Key": CLIENT_KEY}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/config", headers=headers)
            assert response.status_code == 403

            print("✓ Wrong key type returns 403")

    @pytest.mark.asyncio
    async def test_api_summary(self):
        """Print API summary."""
        print_test_header("API RESPONSE PATTERNS SUMMARY")

        print("\n1. ENVELOPE FORMATS:")
        print("   - Health: Simple JSON, no envelope")
        print("   - All others: Standard envelope {object, timestamp, success, error, data}")

        print("\n2. LIST RESPONSES:")
        print("   - Agents: {agents: [...], count: N}")
        print("   - Secrets: {secrets: {key: 'masked'}, count: N} (dict, not array!)")
        print("   - MCP Servers: {servers: [...], count: N}")
        print("   - Jobs: {jobs: [...], count: N}")
        print("   - Memories: {memories: [...], count: N}")

        print("\n3. AUTHENTICATION:")
        print("   - Admin endpoints: X-Muxi-Admin-Key header")
        print("   - Client endpoints: X-Muxi-Client-Key + X-Muxi-User-Id headers")
        print("   - All auth errors return 403 (Forbidden), not 401")

        print("\n4. SPECIAL BEHAVIORS:")
        print("   - /v1/config returns resource links, not actual config")
        print("   - Secrets are always masked as '••••••••'")
        print("   - List endpoints include count field")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
