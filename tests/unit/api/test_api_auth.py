#!/usr/bin/env python3
"""
Test API authentication for admin and client endpoints.

Tests each endpoint with:
1. Correct API key
2. Wrong API key
3. No API key
"""

import asyncio
import httpx
from typing import Dict, Any
import json
from datetime import datetime


# Server configuration
BASE_URL = "http://localhost:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"
WRONG_KEY = "sk_muxi_wrong_key_12345"


async def test_endpoint(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: Dict[str, str],
    test_name: str
) -> Dict[str, Any]:
    """Test a single endpoint and return results."""
    try:
        response = await client.request(method, url, headers=headers)
        result = {
            "test": test_name,
            "url": url,
            "status": response.status_code,
            "success": 200 <= response.status_code < 300,
            "headers": dict(response.headers),
        }

        # Try to parse JSON response
        try:
            result["body"] = response.json()
        except Exception:
            result["body"] = response.text

        return result

    except Exception as e:
        return {
            "test": test_name,
            "url": url,
            "status": "ERROR",
            "success": False,
            "error": str(e)
        }


async def test_admin_endpoints():
    """Test admin endpoints with different auth scenarios."""
    print("\n" + "="*60)
    print("🔐 TESTING ADMIN ENDPOINTS")
    print("="*60)

    # Admin endpoints to test
    admin_endpoints = [
        ("GET", "/v1/agents", "List agents"),
        ("GET", "/v1/secrets", "List secrets"),
        ("GET", "/v1/config", "Get config"),
        ("GET", "/v1/overlord/status", "Overlord status"),
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for method, endpoint, description in admin_endpoints:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n📍 Testing: {description} ({endpoint})")
            print("-" * 50)

            # Test 1: Correct API key
            headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
            result = await test_endpoint(client, method, url, headers, "Correct admin key")
            print(f"✅ Correct key: {result['status']} - {'SUCCESS' if result['success'] else 'FAILED'}")
            if result['success'] and 'body' in result:
                print(f"   Response preview: {json.dumps(result['body'], indent=2)[:200]}...")

            # Test 2: Wrong API key
            headers = {"X-Muxi-Admin-Key": WRONG_KEY}
            result = await test_endpoint(client, method, url, headers, "Wrong admin key")
            print(f"❌ Wrong key: {result['status']} - {'FAILED as expected' if result['status'] == 401 else 'UNEXPECTED'}")

            # Test 3: No API key
            headers = {}
            result = await test_endpoint(client, method, url, headers, "No admin key")
            print(f"🚫 No key: {result['status']} - {'FAILED as expected' if result['status'] == 403 else 'UNEXPECTED'}")


async def test_client_endpoints():
    """Test client endpoints with different auth scenarios."""
    print("\n" + "="*60)
    print("👤 TESTING CLIENT ENDPOINTS")
    print("="*60)

    # Client endpoints to test (these need user_id in path)
    client_endpoints = [
        ("GET", "/v1/events/test_user", "Events stream"),
        ("GET", "/v1/jobs/test_user", "List user jobs"),
        ("GET", "/v1/memories/test_user", "User memories"),
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for method, endpoint, description in client_endpoints:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n📍 Testing: {description} ({endpoint})")
            print("-" * 50)

            # Test 1: Correct API key
            headers = {"X-Muxi-Client-Key": CLIENT_KEY}
            result = await test_endpoint(client, method, url, headers, "Correct client key")
            print(f"✅ Correct key: {result['status']} - {'SUCCESS' if result['success'] else 'FAILED'}")
            if result['success'] and 'body' in result:
                print(f"   Response preview: {json.dumps(result['body'], indent=2)[:200]}...")

            # Test 2: Wrong API key
            headers = {"X-Muxi-Client-Key": WRONG_KEY}
            result = await test_endpoint(client, method, url, headers, "Wrong client key")
            print(f"❌ Wrong key: {result['status']} - {'FAILED as expected' if result['status'] == 401 else 'UNEXPECTED'}")

            # Test 3: No API key
            headers = {}
            result = await test_endpoint(client, method, url, headers, "No client key")
            print(f"🚫 No key: {result['status']} - {'FAILED as expected' if result['status'] == 403 else 'UNEXPECTED'}")

            # Test 4: Using admin key on client endpoint (should fail)
            headers = {"X-Muxi-Client-Key": ADMIN_KEY}
            result = await test_endpoint(client, method, url, headers, "Admin key on client endpoint")
            print(f"🔑 Admin key: {result['status']} - {'FAILED as expected' if result['status'] == 401 else 'UNEXPECTED'}")


async def test_public_endpoints():
    """Test public endpoints that don't require authentication."""
    print("\n" + "="*60)
    print("🌐 TESTING PUBLIC ENDPOINTS")
    print("="*60)

    # Public endpoints (no auth required)
    public_endpoints = [
        ("GET", "/v1/health", "Health check"),
        ("GET", "/", "Root endpoint"),
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for method, endpoint, description in public_endpoints:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n📍 Testing: {description} ({endpoint})")
            print("-" * 50)

            # Test without any key (should work)
            headers = {}
            result = await test_endpoint(client, method, url, headers, "No key (public)")
            print(f"🆓 No key: {result['status']} - {'SUCCESS' if result['success'] else 'FAILED'}")
            if result['success'] and 'body' in result:
                print(f"   Response: {json.dumps(result['body'], indent=2)}")


async def main():
    """Run all authentication tests."""
    print("\n🚀 Starting API Authentication Tests")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Server: {BASE_URL}")
    print(f"🔑 Admin Key: {ADMIN_KEY[:20]}...")
    print(f"🔑 Client Key: {CLIENT_KEY[:20]}...")

    try:
        # Test server connectivity first
        print("\n🏥 Checking server health...")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            if response.status_code == 200:
                print("✅ Server is healthy!")
            else:
                print(f"⚠️  Server returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Make sure the server is running on http://localhost:8271")
        return

    # Run all tests
    await test_public_endpoints()
    await test_admin_endpoints()
    await test_client_endpoints()

    print("\n" + "="*60)
    print("✅ All authentication tests completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
