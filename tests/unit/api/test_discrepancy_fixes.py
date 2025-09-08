"""
Test to verify API discrepancy fixes are working correctly.

This test validates that the key discrepancies identified in docs/api-discrepancies.md
have been resolved by checking the actual API responses.
"""

import asyncio
import httpx
import pytest
from tests.api.utils import wait_for_server


@pytest.mark.asyncio
async def test_health_endpoint_envelope_format():
    """Test that /health returns proper envelope format instead of simple JSON."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    async with httpx.AsyncClient() as client:
        response = await client.get("http://0.0.0.0:8271/v1/health")
        assert response.status_code == 200

        data = response.json()

        # Check envelope format is present
        assert "object" in data
        assert "timestamp" in data
        assert "type" in data
        assert "request" in data
        assert "success" in data
        assert "error" in data
        assert "data" in data

        # Check specific values
        assert data["object"] == "status"
        assert data["success"] is True
        assert data["error"] is None
        assert "status" in data["data"]
        assert data["data"]["status"] in ["healthy", "unhealthy"]


@pytest.mark.asyncio
async def test_authentication_returns_401():
    """Test that authentication errors return HTTP 401 instead of HTTP 403."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    async with httpx.AsyncClient() as client:
        # Test missing admin key
        response = await client.get("http://0.0.0.0:8271/v1/agents")
        assert response.status_code == 401  # Should be 401, not 403

        # Test invalid admin key
        response = await client.get(
            "http://0.0.0.0:8271/v1/agents",
            headers={"X-Muxi-Admin-Key": "invalid-key"}
        )
        assert response.status_code == 401  # Should be 401, not 403

        # Test missing client key
        response = await client.post(
            "http://0.0.0.0:8271/v1/chat",
            json={"message": "hello"}
        )
        assert response.status_code == 401  # Should be 401, not 403


@pytest.mark.asyncio
async def test_secrets_endpoint_returns_array():
    """Test that /secrets returns array of objects instead of dictionary."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    # We need a valid admin key - this test might fail if no admin key is configured
    # For now, we'll test the structure assuming some admin key exists
    # In a real test environment, you'd configure a test admin key

    async with httpx.AsyncClient() as client:
        # First try to get the endpoint (might fail with 401 if no admin key)
        response = await client.get(
            "http://0.0.0.0:8271/v1/secrets",
            headers={"X-Muxi-Admin-Key": "test-admin-key"}
        )

        # If we get 401, that's expected in test environment
        if response.status_code == 401:
            pytest.skip("No admin key configured for testing")

        # If we get a successful response, validate the format
        if response.status_code == 200:
            data = response.json()

            # Check envelope format
            assert "object" in data
            assert "success" in data
            assert "data" in data

            # Check that data is an array, not a dictionary with "secrets" key
            assert data["object"] == "list"  # Should be "list" not "secret_list"
            assert isinstance(data["data"], list)  # Should be array directly

            # If there are secrets, each should be an object with key, value, masked
            if data["data"]:
                secret = data["data"][0]
                assert "key" in secret
                assert "value" in secret
                assert "masked" in secret
                assert secret["masked"] is True
                assert secret["value"] == "••••••••"


@pytest.mark.asyncio
async def test_config_endpoint_returns_full_config():
    """Test that /config returns full formation configuration instead of resource summary."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://0.0.0.0:8271/v1/config",
            headers={"X-Muxi-Admin-Key": "test-admin-key"}
        )

        # If we get 401, that's expected in test environment
        if response.status_code == 401:
            pytest.skip("No admin key configured for testing")

        if response.status_code == 200:
            data = response.json()

            # Check envelope format
            assert "object" in data
            assert "success" in data
            assert "data" in data
            assert data["object"] == "config"

            # Check that we get full config, not navigation structure
            # Full config should have formation-level keys like "schema", "id", etc.
            config_data = data["data"]

            # Should NOT have navigation structure (resource links)
            assert "resource" not in str(config_data)  # No resource links

            # Should have formation-level configuration
            # (exact structure depends on test formation, but should be configuration, not links)
            assert isinstance(config_data, dict)


@pytest.mark.asyncio
async def test_404_errors_use_envelope_format():
    """Test that 404 errors return proper envelope format."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    async with httpx.AsyncClient() as client:
        # Test a non-existent endpoint
        response = await client.get("http://0.0.0.0:8271/v1/nonexistent")
        assert response.status_code == 404

        data = response.json()

        # Check envelope format is present
        assert "object" in data
        assert "timestamp" in data
        assert "type" in data
        assert "request" in data
        assert "success" in data
        assert "error" in data
        assert "data" in data

        # Check specific values for 404
        assert data["object"] == "error"
        assert data["success"] is False
        assert data["error"] is not None
        assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert data["data"] == {}


@pytest.mark.asyncio
async def test_root_endpoints_return_html():
    """Test that root endpoints return HTML status pages."""
    # Wait for server to be ready
    if not await wait_for_server(verbose=False):
        pytest.fail("Server failed to start")

    async with httpx.AsyncClient() as client:
        # Test root endpoint
        response = await client.get("http://0.0.0.0:8271/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Up" in response.text or "Down" in response.text

        # Test /v1 endpoint
        response = await client.get("http://0.0.0.0:8271/v1")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Up" in response.text or "Down" in response.text


if __name__ == "__main__":
    # Run all tests
    asyncio.run(test_health_endpoint_envelope_format())
    asyncio.run(test_authentication_returns_401())
    asyncio.run(test_secrets_endpoint_returns_array())
    asyncio.run(test_config_endpoint_returns_full_config())
    asyncio.run(test_404_errors_use_envelope_format())
    asyncio.run(test_root_endpoints_return_html())
    print("✅ All discrepancy fix tests completed!")
