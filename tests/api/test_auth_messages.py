#!/usr/bin/env python3
"""
Test improved authentication error messages and fixed secrets endpoint.
"""

import asyncio
import httpx
import json


BASE_URL = "http://localhost:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"
WRONG_KEY = "sk_muxi_wrong_key_12345"


async def test_auth_messages():
    """Test the improved authentication error messages."""
    print("🔐 TESTING IMPROVED AUTHENTICATION MESSAGES")
    print("=" * 60)
    
    test_cases = [
        # Admin endpoint tests
        {
            "endpoint": "/v1/agents",
            "headers": {},
            "description": "Admin endpoint with no auth header",
            "expected_message": "A valid admin API key is required. Please provide the 'X-Muxi-Admin-Key' header."
        },
        {
            "endpoint": "/v1/agents", 
            "headers": {"X-Muxi-Admin-Key": WRONG_KEY},
            "description": "Admin endpoint with wrong key",
            "expected_message": "Invalid admin API key. Please check your 'X-Muxi-Admin-Key' header value."
        },
        # Client endpoint tests
        {
            "endpoint": "/v1/jobs/test_user",
            "headers": {},
            "description": "Client endpoint with no auth header", 
            "expected_message": "A valid client API key is required. Please provide the 'X-Muxi-Client-Key' header."
        },
        {
            "endpoint": "/v1/jobs/test_user",
            "headers": {"X-Muxi-Client-Key": WRONG_KEY},
            "description": "Client endpoint with wrong key",
            "expected_message": "Invalid client API key. Please check your 'X-Muxi-Client-Key' header value."
        }
    ]
    
    async with httpx.AsyncClient() as client:
        for test_case in test_cases:
            url = f"{BASE_URL}{test_case['endpoint']}"
            print(f"\n📍 {test_case['description']}")
            print("-" * 50)
            
            try:
                response = await client.get(url, headers=test_case["headers"])
                
                if response.status_code == 403:
                    body = response.json()
                    actual_message = body.get("detail", "No detail found")
                    
                    if actual_message == test_case["expected_message"]:
                        print(f"✅ PASS: Correct error message")
                        print(f"   Message: {actual_message}")
                    else:
                        print(f"❌ FAIL: Wrong error message")
                        print(f"   Expected: {test_case['expected_message']}")
                        print(f"   Actual:   {actual_message}")
                else:
                    print(f"❌ FAIL: Expected 403, got {response.status_code}")
                    
            except Exception as e:
                print(f"❌ ERROR: {e}")


async def test_secrets_endpoint():
    """Test the fixed secrets endpoint."""
    print("\n\n🔐 TESTING FIXED SECRETS ENDPOINT")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        # Test with correct admin key
        headers = {"X-Muxi-Admin-Key": ADMIN_KEY}
        url = f"{BASE_URL}/v1/secrets"
        
        print("📍 Testing GET /v1/secrets with correct admin key")
        print("-" * 50)
        
        try:
            response = await client.get(url, headers=headers)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                body = response.json()
                print("✅ SUCCESS: Secrets endpoint is working!")
                print(f"Response structure: {json.dumps(body, indent=2)}")
                
                # Check if it has the expected structure
                if "data" in body and "secrets" in body.get("data", {}):
                    secrets = body["data"]["secrets"]
                    print(f"🔑 Found {len(secrets)} secrets (values masked)")
                    for key in secrets:
                        print(f"   - {key}: {secrets[key]}")
                else:
                    print("⚠️  Response structure different than expected")
                    
            elif response.status_code == 500:
                body = response.json()
                print("❌ STILL FAILING: Internal server error")
                print(f"Error details: {json.dumps(body, indent=2)}")
            else:
                print(f"❌ Unexpected status: {response.status_code}")
                try:
                    body = response.json()
                    print(f"Response: {json.dumps(body, indent=2)}")
                except:
                    print(f"Response text: {response.text}")
                    
        except Exception as e:
            print(f"❌ ERROR: {e}")


async def main():
    """Run all tests."""
    print("🧪 TESTING AUTHENTICATION IMPROVEMENTS & SECRETS FIX")
    print("📅 Starting tests...\n")
    
    # Check server health
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            if response.status_code == 200:
                print("✅ Server is healthy and reachable")
            else:
                print(f"⚠️  Server health check returned {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return
    
    # Run tests
    await test_auth_messages()
    await test_secrets_endpoint()
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())