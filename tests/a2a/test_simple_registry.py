#!/usr/bin/env python3
"""
Simple test to check mock registry server requirements
"""

import asyncio
import httpx
import json


async def test_registration_format():
    """Test what format the mock registry server expects."""

    print("🧪 Testing mock registry server format requirements")
    print("=" * 50)

    # Test basic registration payload
    test_payload = {
        "name": "test-agent",
        "description": "A test agent",
        "version": "1.0.0",
        "url": "http://localhost:8080/test-agent",
        "a2aVersion": "1.0",
        "capabilities": {
            "tools": {
                "name": "tools",
                "description": "Agent can use tools",
                "enabled": True
            }
        },
        "provider": {
            "name": "MUXI",
            "type": "formation",
            "organization": "MUXI Framework",
            "url": "https://github.com/muxi-framework"
        },
        "muxiExtensions": {
            "agentId": "test-agent"
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            # Test health endpoint
            health_response = await client.get("http://localhost:9090/health")
            print(f"Health check: {health_response.status_code}")

            # Test registration
            reg_response = await client.post(
                "http://localhost:9090/register",
                json=test_payload,
                headers={"Content-Type": "application/json"}
            )

            print(f"Registration status: {reg_response.status_code}")
            if reg_response.status_code != 200:
                print(f"Registration error: {reg_response.text}")
            else:
                print("✅ Registration successful!")

            # Test discovery
            disc_response = await client.get("http://localhost:9090/discover")
            print(f"Discovery status: {disc_response.status_code}")
            if disc_response.status_code == 200:
                agents = disc_response.json()
                print(f"Found {len(agents)} agents")
                if agents:
                    print("Sample agent structure:")
                    print(json.dumps(agents[0], indent=2))

        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_registration_format())
