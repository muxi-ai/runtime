"""
Example test showing how to use wait_for_server utility.
"""

import asyncio
import httpx
from tests.api.utils import wait_for_server, wait_for_server_from_config


async def test_health_endpoint():
    """Test the health endpoint after ensuring server is ready."""
    # Method 1: Using default parameters
    if not await wait_for_server():
        raise RuntimeError("Server failed to start")

    # Now run your test
    async with httpx.AsyncClient() as client:
        response = await client.get("http://0.0.0.0:8271/v1/health")
        assert response.status_code == 200
        print("✅ Health endpoint test passed!")


async def test_with_custom_config():
    """Test using server config dict."""
    server_config = {
        "host": "localhost",
        "port": 8271
    }

    # Method 2: Using server config
    if not await wait_for_server_from_config(server_config):
        raise RuntimeError("Server failed to start")

    # Run your test...
    print("✅ Server is ready with custom config!")


async def test_with_custom_timeout():
    """Test with custom timeout and less verbose output."""
    # Method 3: Custom parameters
    if not await wait_for_server(
        host="localhost",
        port=8271,
        timeout=30.0,  # 30 second timeout
        check_interval=1.0,  # Check every second
        verbose=False  # Quiet mode
    ):
        raise RuntimeError("Server failed to start")

    print("✅ Server ready (quiet mode)")


if __name__ == "__main__":
    # Run all tests
    asyncio.run(test_health_endpoint())
    asyncio.run(test_with_custom_config())
    asyncio.run(test_with_custom_timeout())
