#!/usr/bin/env python3
"""Quick test to debug server startup issue."""

import asyncio
import sys
from pathlib import Path
import httpx
import time

sys.path.insert(0, str(Path(__file__).parent / "src"))

from muxi.formation import Formation


async def test_server():
    """Test basic server startup and endpoint."""
    print("=" * 60)
    print("TESTING SERVER STARTUP")
    print("=" * 60)
    
    # Create formation
    print("\n1. Loading formation...")
    formation_path = Path(__file__).parent / "e2e/tests/19_api/formation-api"
    formation = Formation()
    await formation.load(str(formation_path / "formation.yaml"))
    
    print("✅ Formation loaded")
    
    # Check if server is configured
    print("\n2. Checking server configuration...")
    print(f"   Server config: {formation._server_config}")
    
    # Start overlord first
    print("\n3. Starting overlord...")
    await formation.start_overlord()
    print("✅ Overlord started")
    
    # Start server in non-blocking mode
    print("\n4. Starting API server...")
    server = await formation.start_server(block=False)
    print("✅ Server start() completed")
    
    # Wait a moment
    print("\n5. Waiting for server to settle...")
    await asyncio.sleep(2)
    
    # Check if server task is still running
    print(f"\n6. Server task status: done={server._server_task.done()}")
    if server._server_task.done():
        try:
            await server._server_task
            print("   Server task completed without error")
        except Exception as e:
            print(f"   Server task failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Test endpoint with async HTTP client
    print("\n7. Testing /v1/health endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8271/v1/health", timeout=5.0)
            print(f"   Status code: {response.status_code}")
            print(f"   Response: {response.json()}")
            print("✅ /v1/health endpoint responded")
    except httpx.TimeoutException:
        print("❌ Request timed out!")
        # Check server task status again
        print(f"   Server task done: {server._server_task.done()}")
        return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test /v1/status endpoint
    print("\n8. Testing /v1/status endpoint...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8271/v1/status", timeout=5.0)
            print(f"   Status code: {response.status_code}")
            print(f"   Response: {response.json()}")
            print("✅ /v1/status endpoint responded")
    except httpx.TimeoutException:
        print("❌ Request timed out!")
        return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Cleanup
    print("\n9. Cleaning up...")
    await formation.shutdown()
    print("✅ Cleanup complete")
    
    return True


if __name__ == "__main__":
    result = asyncio.run(test_server())
    sys.exit(0 if result else 1)
