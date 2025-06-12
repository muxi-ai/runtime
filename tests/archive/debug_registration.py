#!/usr/bin/env python3
"""
Debug script to isolate the registration issue
"""
import asyncio
import requests
from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM


async def test_registration():
    print("🔍 Debugging Agent Registration Issue")
    print("=" * 50)

    # Check registry status first
    try:
        response = requests.get("http://localhost:9090/health", timeout=5)
        print(f"✅ Registry health: {response.json()}")
    except Exception as e:
        print(f"❌ Registry not reachable: {e}")
        return

    # Create a simple formation config
    formation_config = {
        'name': 'debug-formation',
        'a2a': {
            'registries': ['http://localhost:9090'],
            'server': {
                'enabled': True,
                'port': 8082,
                'host': '0.0.0.0'
            }
        }
    }

    # Create overlord
    print("\n🏗️  Creating overlord...")
    overlord = Overlord(formation_config=formation_config)
    await overlord.initialize_external_registry_async()

    # Create model
    model = LLM(model="openai/gpt-4o-mini")

    # Create agent
    print("\n👤 Creating test agent...")
    agent = overlord.create_agent(
        agent_id="debug-agent",
        model=model,
        description="Test agent for debugging registration",
        a2a_external=True
    )

    # Start formation server
    print("\n🚀 Starting formation server...")
    result = await overlord.start_formation_server()
    print(f"Formation server result: {result}")

    # Check registry again
    try:
        response = requests.get("http://localhost:9090/discover", timeout=5)
        agents = response.json().get('agents', [])
        debug_agents = [a for a in agents if a.get('name') == 'debug-agent']
        print(f"\n📋 Debug agents in registry: {len(debug_agents)}")
        for agent in debug_agents:
            print(f"   - {agent.get('name')}: {agent.get('url')}")
    except Exception as e:
        print(f"❌ Failed to check registry: {e}")

    # Cleanup
    print("\n🧹 Cleaning up...")
    await overlord.stop_formation_server()
    print("✅ Cleanup complete")


if __name__ == "__main__":
    asyncio.run(test_registration())
