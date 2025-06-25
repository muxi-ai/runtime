#!/usr/bin/env python3
"""
Test script for External A2A Registry Integration

This script tests the external registry functionality with the mock server
running on localhost:9090. It demonstrates:
- Agent registration with external registry using formation config
- Agent discovery from external registry
- External agent communication
- Registry health checks
"""

import asyncio
import socket
import yaml


from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM


def load_formation_config(file_path: str):
    """Load formation configuration from YAML file."""
    try:
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Failed to load formation config: {e}")
        return None


async def test_external_registry():
    """Test external registry integration end-to-end."""

    print("🚀 Testing External A2A Registry Integration")
    print("=" * 50)

    # Load formation configuration
    print("\n1. Loading formation configuration...")
    formation_config = load_formation_config("test-formation.yaml")
    if not formation_config:
        print("❌ Failed to load formation config")
        return

    print(f"✅ Loaded formation: {formation_config['name']}")
    print(f"   Registries: {formation_config.get('a2a', {}).get('registries', [])}")

    # Create overlord with formation config
    overlord = Overlord(
        user_api_key="test_client_key",
        admin_api_key="test_admin_key",
        formation_config=formation_config
    )

    # Initialize external registry async
    await overlord.initialize_external_registry_async()

    # Create a simple model for testing
    model = LLM(model="openai/gpt-4o-mini", api_key="test_key")

    # Create test agents
    print("\n2. Creating test agents...")

    # Create agents as specified in formation
    for agent_config in formation_config.get('agents', []):
        agent_id = agent_config['id']
        description = agent_config.get('description', f"Agent: {agent_id}")
        a2a_external = agent_config.get('a2a_external', False)

        agent = overlord.create_agent(
            agent_id=agent_id,
            model=model,
            system_message=agent_config['system_message'],
            description=description
        )

        print(f"   ✅ Created agent: {agent_id} (external: {a2a_external})")

    print(f"\n✅ Created {len(overlord.agents)} agents")

    # Test external registry functionality
    if overlord.external_registry_client:
        print("\n3. Testing external registry operations...")

        # Test health check
        print("   Testing health check...")
        try:
            for registry_name in overlord.external_registry_client.registries:
                health = await overlord.external_registry_client.health_check(registry_name)
                if health:
                    print(f"   ✅ Registry {registry_name} is healthy")
                else:
                    print(f"   ❌ Registry {registry_name} is unhealthy")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")

        # Test agent registration
        print("\n   Testing agent registration...")
        for agent_id in overlord.agents:
            try:
                success = await overlord.register_agent_with_external_registry(agent_id)
                if success:
                    print(f"   ✅ Registered agent: {agent_id}")
                else:
                    print(f"   ❌ Failed to register agent: {agent_id}")
            except Exception as e:
                print(f"   ❌ Registration error for {agent_id}: {e}")

        # Test discovery
        print("\n   Testing agent discovery...")
        try:
            discovered = await overlord.discover_external_agents(capability="tools")
            print(f"   ✅ Discovered {len(discovered)} external agents")
            for agent in discovered[:3]:  # Show first 3
                name = getattr(agent, 'name', 'unknown')
                desc = getattr(agent, 'description', 'no description')
                print(f"      - {name}: {desc[:50]}...")
        except Exception as e:
            print(f"   ❌ Discovery failed: {e}")
    else:
        print("\n❌ No external registry client configured")

    print("\n🎉 Test completed!")


def check_server_connectivity(host: str = "localhost", port: int = 9090):
    """Check if the mock registry server is running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def main():
    """Main test function."""
    print("🔍 Checking mock registry server...")
    if check_server_connectivity():
        print("✅ Mock registry server is running on localhost:9090")
        await test_external_registry()
    else:
        print("❌ Mock registry server not found on localhost:9090")
        print("   Please start the mock server before running this test")


if __name__ == "__main__":
    asyncio.run(main())
