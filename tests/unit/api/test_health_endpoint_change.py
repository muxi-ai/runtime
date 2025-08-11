#!/usr/bin/env python3
"""
Test that health endpoint has been moved from /health to /v1/health.
"""

import asyncio
import httpx


BASE_URL = "http://localhost:8271"


async def test_health_endpoints():
    """Test both old and new health endpoints."""
    print("🏥 TESTING HEALTH ENDPOINT CHANGE")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        print("\n📍 Testing old endpoint: /health")
        print("-" * 40)
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"Status: {response.status_code}")
            if response.status_code == 404:
                print("✅ EXPECTED: Old endpoint returns 404 (not found)")
            elif response.status_code == 200:
                print("⚠️  OLD ENDPOINT STILL WORKS - server needs restart")
            else:
                print(f"❓ Unexpected status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n📍 Testing new endpoint: /v1/health")
        print("-" * 40)
        try:
            response = await client.get(f"{BASE_URL}/v1/health")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                body = response.json()
                print("✅ SUCCESS: New endpoint works!")
                print(f"Response: {body}")
            elif response.status_code == 404:
                print("❌ NEW ENDPOINT NOT FOUND - server needs restart")
            else:
                print(f"❓ Unexpected status: {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n📍 Testing admin status endpoint: /v1/status (requires admin key)")
        print("-" * 40)
        try:
            # This is an admin endpoint, test without key first
            response = await client.get(f"{BASE_URL}/v1/status")
            print(f"Status without auth: {response.status_code}")
            if response.status_code == 403:
                print("✅ EXPECTED: Admin endpoint requires authentication")
            else:
                print(f"❓ Unexpected status without auth: {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")


async def main():
    """Run health endpoint tests."""
    print("🧪 TESTING HEALTH ENDPOINT STRUCTURE")
    print("Public: /v1/health (no auth required)")
    print("Admin: /v1/status (requires admin key)\n")
    
    await test_health_endpoints()
    
    print("\n" + "=" * 60)
    print("📋 SUMMARY:")
    print("- /health should return 404 (moved to /v1/health)")
    print("- /v1/health should return 200 (public endpoint)")
    print("- /v1/status should return 403 without auth (admin endpoint)")
    print("- If old /health still works, restart the server")


if __name__ == "__main__":
    asyncio.run(main())