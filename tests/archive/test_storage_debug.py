#!/usr/bin/env python3
"""
Debug storage issues with the registry
"""

import sys
import json
from pathlib import Path

# Add the registry module to the path
sys.path.insert(0, '../src/muxi/runtime/utils')

# Import the storage classes
from a2a_registry import RegistryStorage, AgentCard  # noqa: E402


def test_storage():
    """Test the storage functionality directly"""

    print("🔧 Testing Registry Storage Directly")
    print("=" * 50)

    # Create storage instance
    storage = RegistryStorage(".test_registry_data")

    # Check if directory was created
    data_dir = Path(".test_registry_data")
    print(f"Data directory exists: {data_dir.exists()}")

    agents_file = data_dir / "agents.json"
    print(f"Agents file exists: {agents_file.exists()}")

    if agents_file.exists():
        with open(agents_file, 'r') as f:
            content = f.read()
        print(f"Initial file content: '{content}'")

    # Create a test agent card
    print("\n📝 Creating test agent card...")
    agent_card = AgentCard(
        name="test-storage-agent",
        description="Test agent for storage testing",
        version="1.0.0",
        url="http://localhost:8080/test-storage-agent"
    )

    print(f"Agent card created: {agent_card.name}")
    print(f"Agent URL: {agent_card.url}")

    # Test registration
    print("\n📦 Testing registration...")
    success = storage.register_agent(agent_card)
    print(f"Registration success: {success}")

    # Check file content after registration
    if agents_file.exists():
        with open(agents_file, 'r') as f:
            content = f.read()
        print(f"File content after registration: '{content}'")

        try:
            data = json.loads(content)
            print(f"Parsed JSON keys: {list(data.keys())}")
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")

    # Test retrieval
    print("\n📖 Testing retrieval...")
    registered_agents = storage.get_registered_agents()
    print(f"Retrieved {len(registered_agents)} agents")

    for agent in registered_agents:
        print(f"  - {agent.name}: {agent.url}")

    # Test deregistration
    print("\n🗑️ Testing deregistration...")
    deregister_success = storage.deregister_agent(agent_card.url)
    print(f"Deregistration success: {deregister_success}")

    # Check file content after deregistration
    if agents_file.exists():
        with open(agents_file, 'r') as f:
            content = f.read()
        print(f"File content after deregistration: '{content}'")

    # Final retrieval test
    print("\n📖 Final retrieval test...")
    final_agents = storage.get_registered_agents()
    print(f"Final agent count: {len(final_agents)}")

    # Cleanup
    import shutil
    if data_dir.exists():
        shutil.rmtree(data_dir)
        print("\n🧹 Cleaned up test directory")


if __name__ == "__main__":
    test_storage()
