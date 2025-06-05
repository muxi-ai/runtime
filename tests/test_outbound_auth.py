#!/usr/bin/env python3
"""
Test script for A2A outbound authentication
Tests that our agents can authenticate to external agents with various auth types
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add runtime to path
runtime_path = Path(__file__).parent.parent / "runtime"
sys.path.insert(0, str(runtime_path))

from muxi.runtime.overlord import Overlord
from muxi.runtime.agent import Agent
from muxi.runtime.llm.llm import LLM
from muxi.runtime.a2a.auth import get_auth_manager, AuthType

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_outbound_auth():
    """Test outbound authentication to various external agents"""
    print("🔐 Testing A2A Outbound Authentication")
    print("=" * 50)

    # Create a mock overlord and agent
    overlord = Overlord()

    # Create a mock LLM (won't actually be used for communication testing)
    class MockLLM:
        def __init__(self):
            self.model = "mock-model"

        async def generate_response(self, message, **kwargs):
            return f"Mock response to: {message}"

    mock_llm = MockLLM()

    # Create an agent for testing
    agent = Agent(
        agent_id="test-sender",
        model=mock_llm,
        overlord=overlord,
        system_message="Test agent for outbound auth testing"
    )

    # Test authentication manager setup
    auth_manager = get_auth_manager()
    print(f"📋 Available credentials: {auth_manager.list_agents_with_credentials()}")

    # Test different target agents with different auth requirements
    test_cases = [
        {
            "name": "No Auth Agent",
            "target": "public-data-service",
            "expected_auth": AuthType.NONE,
            "should_succeed": True
        },
        {
            "name": "API Key Agent",
            "target": "external-billing-service",
            "expected_auth": AuthType.API_KEY,
            "should_succeed": True  # We have credentials
        },
        {
            "name": "Bearer Token Agent",
            "target": "analytics-engine",
            "expected_auth": AuthType.BEARER,
            "should_succeed": True  # We have credentials
        },
        {
            "name": "OAuth2 Agent",
            "target": "notification-hub",
            "expected_auth": AuthType.OAUTH2,
            "should_succeed": False  # OAuth endpoint won't work in test
        },
        {
            "name": "Unknown Agent",
            "target": "non-existent-agent",
            "expected_auth": None,
            "should_succeed": False  # Agent doesn't exist
        }
    ]

    results = []

    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")
        print(f"   Target: {test_case['target']}")
        print(f"   Expected auth: {test_case['expected_auth']}")

        try:
            # Send a test message - this will trigger authentication flow
            response = await agent.send_a2a_message(
                target_agent_id=test_case['target'],
                message="Hello, this is a test message for authentication verification",
                message_type="request",
                wait_for_response=True,
                timeout=10  # Short timeout for testing
            )

            success = response.get("status") != "error"

            if success and test_case['should_succeed']:
                print(f"   ✅ SUCCESS: Authentication worked as expected")
            elif not success and not test_case['should_succeed']:
                print(f"   ✅ SUCCESS: Failed as expected - {response.get('error', 'Unknown error')}")
            elif success and not test_case['should_succeed']:
                print(f"   ❌ UNEXPECTED: Should have failed but succeeded")
                print(f"      Response: {response}")
            else:
                print(f"   ❌ UNEXPECTED: Should have succeeded but failed")
                print(f"      Error: {response.get('error', 'Unknown error')}")

            results.append({
                "test": test_case['name'],
                "target": test_case['target'],
                "success": success,
                "expected": test_case['should_succeed'],
                "response": response
            })

        except Exception as e:
            print(f"   ❌ EXCEPTION: {str(e)}")
            results.append({
                "test": test_case['name'],
                "target": test_case['target'],
                "success": False,
                "expected": test_case['should_succeed'],
                "error": str(e)
            })

    # Summary
    print(f"\n{'='*50}")
    print("📊 TEST RESULTS SUMMARY")
    print(f"{'='*50}")

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['success'] == r['expected'])

    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")

    for result in results:
        status = "✅ PASS" if result['success'] == result['expected'] else "❌ FAIL"
        print(f"{status} {result['test']} ({result['target']})")

    return results

async def test_auth_manager_directly():
    """Test the authentication manager directly"""
    print("\n🔧 Testing Auth Manager Directly")
    print("=" * 40)

    auth_manager = get_auth_manager()

    # Test credential management
    print("Testing credential management...")

    # Test adding new credentials
    try:
        auth_manager.add_credentials(
            "test-agent",
            AuthType.API_KEY,
            {"api_key": "test-key-123"}
        )
        print("✅ Successfully added test credentials")
    except Exception as e:
        print(f"❌ Failed to add credentials: {e}")

    # Test getting credentials
    creds = auth_manager.get_credentials("test-agent")
    if creds:
        print(f"✅ Retrieved credentials: {creds.auth_type}")
    else:
        print("❌ Failed to retrieve credentials")

    # Test applying authentication
    headers = {"Content-Type": "application/json"}
    success, updated_headers = await auth_manager.apply_authentication(
        "test-agent", AuthType.API_KEY, headers, required=True
    )

    if success and "X-API-Key" in updated_headers:
        print(f"✅ Authentication applied successfully")
        print(f"   Headers: {updated_headers}")
    else:
        print(f"❌ Authentication failed")

    # Clean up
    auth_manager.remove_credentials("test-agent")

if __name__ == "__main__":
    async def main():
        await test_auth_manager_directly()
        await test_outbound_auth()

    asyncio.run(main())
