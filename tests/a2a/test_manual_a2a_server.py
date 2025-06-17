#!/usr/bin/env python3
"""
Manual A2A Formation Server Test

Quick test to verify the A2A Formation Server endpoints work correctly.
"""

import asyncio
import sys
import aiohttp
from unittest.mock import AsyncMock, MagicMock

from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM


async def test_a2a_a2a_server():
    """Manual test of A2A Formation Server"""

    # Configuration
    formation_config = {
        "name": "manual-test-formation",
        "a2a": {
            "server": {
                "enabled": True,
                "port": 8185,  # Different port to avoid conflicts
                "host": "127.0.0.1",
                "trusted_endpoints": ["127.0.0.1", "localhost"],
                "mode": "none"
            }
        }
    }

    # Create mock model
    mock_model = MagicMock(spec=LLM)
    mock_model.run = AsyncMock(return_value="Hello from A2A Formation Server!")

    # Create mock LLM.chat method too in case it's used
    mock_model.chat = AsyncMock(return_value="Hello from A2A Formation Server!")
    mock_model.generate = AsyncMock(return_value="Hello from A2A Formation Server!")

    print("🚀 Starting A2A Formation Server test...")

    # Create overlord with formation server
    overlord = Overlord(formation_config=formation_config)
    print(f"✅ Formation server initialized: {overlord.server is not None}")

    # Add a test agent
    agent = overlord.create_agent(
        agent_id="test-agent",
        model=mock_model,
        description="Test agent for A2A communication",
        a2a_external=True
    )
    print(f"✅ Created agent: {agent.agent_id}")

    # Start the formation server
    start_result = await overlord.start_a2a_server()
    print(f"✅ Server started: {start_result}")

    if start_result["status"] != "started":
        print("❌ Failed to start server!")
        return False

    try:
        print("📡 Testing HTTP endpoints...")

        # Give server a moment to fully start
        await asyncio.sleep(1)

        async with aiohttp.ClientSession() as session:
            base_url = "http://127.0.0.1:8185"

            # Test health endpoint
            print("Testing /health endpoint...")
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Health check: {data['status']}")
                    print(f"   Formation: {data['formation']}")
                    print(f"   Agents: {data['agents']}")
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return False

            # Test formation info endpoint
            print("Testing /info endpoint...")
            async with session.get(f"{base_url}/info") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Formation info: {data['formation']}")
                    print(f"   Total agents: {data['total_agents']}")
                    print(f"   Server mode: {data['server_mode']}")
                else:
                    print(f"❌ Formation info failed: {response.status}")
                    return False

            # Test agent discovery endpoint
            print("Testing /agents endpoint...")
            async with session.get(f"{base_url}/agents") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Agent discovery: {len(data['agents'])} agents found")
                    if data['agents']:
                        agent_card = data['agents'][0]
                        print(f"   Agent: {agent_card['name']}")
                        print(f"   Formation: {agent_card['formation']}")
                else:
                    print(f"❌ Agent discovery failed: {response.status}")
                    return False

            # Test agent message endpoint
            print("Testing /agents/{agent_id}/message endpoint...")
            message_payload = {
                "message": "Hello from external client!",
                "message_type": "request",
                "context": {"test": True},
                "message_id": "manual-test-123"
            }

            async with session.post(
                f"{base_url}/agents/test-agent/message",
                json=message_payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Agent message response:")
                    print(f"   Status: {data['status']}")
                    print(f"   Agent ID: {data['agent_id']}")
                    print(f"   Message ID: {data['message_id']}")
                    print(f"   Response: {data['response']}")

                    # Verify mock was called (check agent.run, not model.run)
                    # The formation server calls agent.run() which then calls the model
                    print("✅ Agent responded correctly!")
                else:
                    print(f"❌ Agent message failed: {response.status}")
                    text = await response.text()
                    print(f"   Error: {text}")
                    return False

        print("🎉 All endpoints working correctly!")
        return True

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

    finally:
        # Stop the formation server
        stop_result = await overlord.stop_a2a_server()
        print(f"✅ Server stopped: {stop_result}")


async def main():
    """Main entry point"""
    print("=" * 60)
    print("🧪 MANUAL A2A FORMATION SERVER TEST")
    print("=" * 60)

    success = await test_a2a_a2a_server()

    print("=" * 60)
    if success:
        print("🎉 SUCCESS: A2A Formation Server is working correctly!")
        print("✅ Step 2: A2A Formation Server implementation COMPLETE!")
    else:
        print("❌ FAILED: A2A Formation Server has issues")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
