#!/usr/bin/env python3
"""
Test that authentication errors return proper API envelope format.
"""

import asyncio
import httpx
import json


BASE_URL = "http://localhost:8271"
ADMIN_KEY = "sk_muxi_admin_some_api_key"
CLIENT_KEY = "sk_muxi_client_some_api_key"


async def test_auth_error_formats():
    """Test authentication error response formats."""
    print("🔒 TESTING AUTHENTICATION ERROR RESPONSE FORMATS")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        # Test cases for authentication errors
        test_cases = [
            {
                "name": "Admin endpoint - No API key",
                "endpoint": "/v1/agents",
                "headers": {},
                "expected_error_code": "FORBIDDEN",
                "expected_message": "A valid admin API key is required. Please provide the 'X-Muxi-Admin-Key' header."
            },
            {
                "name": "Admin endpoint - Wrong API key",
                "endpoint": "/v1/agents",
                "headers": {"X-Muxi-Admin-Key": "wrong_key"},
                "expected_error_code": "FORBIDDEN",
                "expected_message": "Invalid admin API key. Please check your 'X-Muxi-Admin-Key' header value."
            },
            {
                "name": "Client endpoint - No API key",
                "endpoint": "/v1/jobs/test_user",
                "headers": {},
                "expected_error_code": "FORBIDDEN",
                "expected_message": "A valid client API key is required. Please provide the 'X-Muxi-Client-Key' header."
            },
            {
                "name": "Client endpoint - Wrong API key",
                "endpoint": "/v1/jobs/test_user",
                "headers": {"X-Muxi-Client-Key": "wrong_key"},
                "expected_error_code": "FORBIDDEN",
                "expected_message": "Invalid client API key. Please check your 'X-Muxi-Client-Key' header value."
            },
        ]
        
        for test in test_cases:
            print(f"\n📍 Testing: {test['name']}")
            print("-" * 40)
            
            try:
                response = await client.get(
                    f"{BASE_URL}{test['endpoint']}",
                    headers=test['headers']
                )
                
                print(f"Status Code: {response.status_code}")
                
                # Parse response body
                try:
                    body = response.json()
                    print(f"Response Type: JSON")
                    
                    # Check envelope structure
                    has_envelope = all(key in body for key in ["object", "timestamp", "type", "request", "success", "error"])
                    
                    if has_envelope:
                        print("✅ Response uses API envelope format")
                        
                        # Check specific fields
                        print(f"  object: {body.get('object')}")
                        print(f"  type: {body.get('type')}")
                        print(f"  success: {body.get('success')}")
                        
                        if body.get('error'):
                            error = body['error']
                            print(f"  error.code: {error.get('code')}")
                            print(f"  error.message: {error.get('message')}")
                            
                            # Verify expected values
                            if error.get('code') == test['expected_error_code']:
                                print(f"  ✅ Error code matches expected: {test['expected_error_code']}")
                            else:
                                print(f"  ❌ Error code mismatch! Expected: {test['expected_error_code']}, Got: {error.get('code')}")
                            
                            if error.get('message') == test['expected_message']:
                                print(f"  ✅ Error message matches expected")
                            else:
                                print(f"  ❌ Error message mismatch!")
                                print(f"     Expected: {test['expected_message']}")
                                print(f"     Got: {error.get('message')}")
                    else:
                        print("❌ Response does NOT use API envelope format")
                        print(f"Response: {json.dumps(body, indent=2)}")
                        
                except Exception as e:
                    print(f"❌ Failed to parse JSON: {e}")
                    print(f"Response: {response.text}")
                    
            except Exception as e:
                print(f"❌ Request failed: {e}")


async def test_successful_request_format():
    """Test that successful requests also use envelope format."""
    print("\n\n✅ TESTING SUCCESSFUL REQUEST FORMAT")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        # Test a successful public endpoint
        print("\n📍 Testing successful public endpoint: /v1/health")
        print("-" * 40)
        
        try:
            response = await client.get(f"{BASE_URL}/v1/health")
            print(f"Status Code: {response.status_code}")
            
            body = response.json()
            
            # Check if it's envelope format or direct response
            if "object" in body and "success" in body:
                print("✅ Uses API envelope format")
                print(f"Response: {json.dumps(body, indent=2)}")
            else:
                print("⚠️  Direct response format (not envelope)")
                print(f"Response: {json.dumps(body, indent=2)}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")


async def main():
    """Run all error format tests."""
    print("🧪 TESTING API ERROR RESPONSE FORMATS")
    print("This test verifies that authentication errors use the proper API envelope format")
    print("instead of FastAPI's default error format.\n")
    
    # Check server connectivity
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/v1/health")
            print(f"✅ Server is reachable")
    except Exception as e:
        print(f"❌ Cannot reach server: {e}")
        print("Make sure the server is running on http://localhost:8271")
        return
    
    await test_auth_error_formats()
    await test_successful_request_format()
    
    print("\n\n" + "=" * 60)
    print("📋 SUMMARY:")
    print("- Authentication errors should use API envelope format")
    print("- Error responses should have: object, timestamp, type, request, success, error")
    print("- The 'error' field should contain: code, message")
    print("- Error codes should match the error type (FORBIDDEN for 403)")


if __name__ == "__main__":
    asyncio.run(main())