"""
Utility function to wait for the API server to be ready.

This is useful for tests that need to ensure the server is fully
started before making API calls, especially when using auto-reload
during development.
"""

import asyncio
import httpx
from typing import Optional, Dict, Any


async def wait_for_server(
    host: str = "0.0.0.0",
    port: int = 8271,
    timeout: float = 60.0,
    check_interval: float = 2.0,
    verbose: bool = True
) -> bool:
    """
    Wait for the API server to be ready by checking the health endpoint.

    Args:
        host: Server host (default: 0.0.0.0)
        port: Server port (default: 8271)
        timeout: Maximum time to wait in seconds (default: 60)
        check_interval: Time between checks in seconds (default: 2)
        verbose: Whether to print status messages (default: True)

    Returns:
        True if server is ready, False if timeout reached

    Example:
        # In your test file:
        from tests.unit.api.utils.wait_for_server import wait_for_server

        async def test_something():
            # Wait for server to be ready
            if not await wait_for_server():
                raise RuntimeError("Server failed to start")

            # Now run your tests...
    """
    start_time = asyncio.get_event_loop().time()
    health_url = f"http://{host}:{port}/v1/health"

    if verbose:
        print(f"⏳ Waiting for server at {health_url} to be ready...")

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_url)
                if response.status_code == 200:
                    if verbose:
                        print("✅ Server is ready!")
                    return True
                else:
                    if verbose:
                        print(f"   Server returned status {response.status_code}, waiting...")
        except (httpx.ConnectError, httpx.TimeoutException):
            if verbose:
                print("   Server not responding yet, waiting...")
        except Exception as e:
            if verbose:
                print(f"   Unexpected error: {e}, waiting...")

        await asyncio.sleep(check_interval)

    if verbose:
        print(f"❌ Server failed to start within {timeout} seconds")
    return False


async def wait_for_server_from_config(
    server_config: Optional[Dict[str, Any]] = None,
    **kwargs
) -> bool:
    """
    Wait for server using configuration dict.

    Args:
        server_config: Server configuration dict with 'host' and 'port' keys
        **kwargs: Additional arguments passed to wait_for_server()

    Returns:
        True if server is ready, False if timeout reached

    Example:
        server_config = {"host": "localhost", "port": 8271}
        await wait_for_server_from_config(server_config)
    """
    if server_config is None:
        server_config = {}

    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8271)

    return await wait_for_server(host=host, port=port, **kwargs)


# Convenience function for use in synchronous test setup
def wait_for_server_sync(**kwargs) -> bool:
    """
    Synchronous wrapper for wait_for_server.

    Useful for test fixtures or setup functions that aren't async.
    """
    return asyncio.run(wait_for_server(**kwargs))
