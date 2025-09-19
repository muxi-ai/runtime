#!/usr/bin/env python3
"""
Test A2A agent discovery functionality.
Tests how agents discover each other through the registry.
"""

import asyncio
import sys
from pathlib import Path
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from muxi.formation import Formation  # noqa: E402


async def test_discovery():
    """Test agent discovery through A2A registry."""
    print("\nA2A Discovery Test")
    print("=" * 60)

    formation = Formation()

    try:
        await formation.load(str(Path(__file__).parent / "formations" / "formation-a2a/formation1/formation.yaml"))
        overlord = await formation.start_overlord()

        print("\nTesting agent discovery...")

        # Test 1: Discover all available agents
        if hasattr(overlord, 'a2a_coordinator'):
            agents = overlord.a2a_coordinator.get_available_agents_for_a2a(
                requesting_agent_id="test-agent",
                capability_filter=None
            )

            print(f"\nDiscovered {len(agents)} agents:")
            for agent_id, agent_info in agents.items():
                print(f"  - {agent_id}: {agent_info.get('description', 'No description')}")
                print(f"    Capabilities: {agent_info.get('capabilities', [])}")
                print(f"    Type: {agent_info.get('type', 'unknown')}")

        # Test 2: Discover by capability
        print("\n\nDiscovering agents with 'project_management' capability...")
        pm_agents = overlord.a2a_coordinator.get_available_agents_for_a2a(
            requesting_agent_id="test-agent",
            capability_filter=["project_management"]
        )

        print(f"Found {len(pm_agents)} project management agents")

        print("\n✅ Discovery test completed!")

    finally:
        await formation.stop_overlord()


if __name__ == "__main__":
    asyncio.run(test_discovery())
