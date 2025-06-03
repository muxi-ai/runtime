#!/usr/bin/env python3
"""
Test script for A2A Agent Server

This script tests the functionality of the A2A agent server implementation
with Google's a2a-sdk integration.
"""

import sys
import asyncio
from pathlib import Path

# Add the runtime to the path for testing from tests directory
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path setup  # noqa: E402
from runtime.muxi.runtime.a2a.server import (  # noqa: E402
    A2AAgentServer, A2AServerManager, MUXIAgentExecutor
)
from a2a.server.agent_execution import RequestContext  # noqa: E402
from a2a.server.events import EventQueue  # noqa: E402


class MockAgent:
    """Mock agent for testing A2A integration"""

    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name

    async def process_a2a_message(self, message: str, sender: str) -> str:
        """Mock method to handle A2A messages"""
        return f"Hello from {self.name}! You said: {message}"


async def test_basic_server_startup():
    """Test basic A2A server startup and shutdown"""

    print("🚀 Testing A2A Server Startup/Shutdown")
    print("-" * 40)

    try:
        # Create mock agent
        mock_agent = MockAgent(agent_id="assistant", name="Assistant")

        # Create and start A2A server
        server = A2AAgentServer(
            agent_instance=mock_agent
        )

        print(f"✅ Created A2A server for agent: {mock_agent.name}")

        # Start the server
        server_info = await server.start()
        print(f"✅ Server started: {server_info}")

        # Test server status
        status = await server.get_status()
        print(f"✅ Server status: {status}")

        # Test health check
        health = await server.health_check()
        print(f"✅ Health check: {health}")

        # Stop the server
        await server.stop()
        print("✅ Server stopped successfully")

        return True

    except Exception as e:
        print(f"❌ Error in server test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_server_manager():
    """Test the A2A Server Manager functionality"""

    print("\n🎯 Testing A2A Server Manager")
    print("-" * 40)

    try:
        # Create server manager
        manager = A2AServerManager()

        # Create multiple mock agents
        agents = [
            MockAgent(agent_id="assistant", name="Assistant"),
            MockAgent(agent_id="travel_assistant", name="Travel Assistant"),
            MockAgent(agent_id="weather_assistant", name="Weather Assistant")
        ]

        print(f"✅ Created {len(agents)} mock agents")

        # Start servers for all agents
        started_servers = {}
        for agent in agents:
            server_info = await manager.start_server(
                agent_instance=agent
            )

            started_servers[agent.agent_id] = server_info
            print(f"✅ Started server for {agent.agent_id}: {server_info['endpoint']}")

        # Test getting all servers
        all_servers = await manager.get_all_servers_info()
        print(f"✅ All servers: {len(all_servers)} running")

        # Test health check all
        health_results = await manager.health_check_all()
        print(f"✅ Health check results: {len(health_results)} servers checked")

        # Stop all servers
        await manager.stop_all_servers()
        print("✅ All servers stopped")

        return True

    except Exception as e:
        print(f"❌ Error in server manager test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_executor():
    """Test the MUXI agent executor functionality"""

    print("\n💬 Testing MUXI Agent Executor")
    print("-" * 40)

    try:
        # Create mock agent
        mock_agent = MockAgent(agent_id="test_agent", name="Test Agent")

        # Create executor
        executor = MUXIAgentExecutor(agent_instance=mock_agent)

        # Create test request context
        request_context = RequestContext(
            request=None,
            task_id="test_task_123",
            context_id="test_context_456",
            task=None
        )

        # Create event queue
        queue = EventQueue()

        # Execute the request
        await executor.execute(request_context, queue)

        # Check if we got a response
        try:
            event = await queue.dequeue_event()
            print("✅ Executor handled request successfully")
            # Extract text from the message parts
            if event.parts and len(event.parts) > 0:
                part = event.parts[0]
                # The part is a generic Part object with root containing the actual TextPart
                if hasattr(part, 'root') and hasattr(part.root, 'text'):
                    response_text = part.root.text
                    print(f"   Response: {response_text}")
                else:
                    print(f"   Raw part: {part}")
            else:
                print(f"   Response: {event}")
        except Exception as e:
            print(f"❌ No response received from executor: {e}")
            return False

        return True

    except Exception as e:
        print(f"❌ Error in executor test: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all A2A server tests"""

    print("🔧 Testing A2A Agent Server Implementation")
    print("=" * 50)

    # Run tests
    tests = [
        ("Basic Server Startup/Shutdown", test_basic_server_startup),
        ("Server Manager", test_server_manager),
        ("MUXI Agent Executor", test_agent_executor)
    ]

    results = {}

    for test_name, test_func in tests:
        results[test_name] = await test_func()

    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! A2A Agent Server is working correctly.")
        return 0
    else:
        print("🚨 Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(result)
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        sys.exit(1)
