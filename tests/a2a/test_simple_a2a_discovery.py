#!/usr/bin/env python3
"""
Test: Simple A2A Discovery with Single Source of Truth

This test demonstrates the cleaned up A2A discovery implementation
with a single, clear configuration approach.
"""

import sys
from pathlib import Path

# Add the runtime to the path for testing from tests directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.muxi.runtime.overlord import Overlord  # noqa: E402
from src.muxi.runtime.llm import LLM  # noqa: E402


def test_simple_a2a_discovery():
    """Test the simplified A2A discovery with single configuration source"""
    # Create overlord
    overlord = Overlord()

    # Create model (mock for testing)
    model = LLM(model="openai/gpt-4o-mini")

    # Create agents with different A2A configurations
    # Agent A: participates in internal A2A (default)
    agent_a = overlord.create_agent(
        agent_id="weather-agent",
        model=model,
        description="Provides weather information",
        # a2a_internal=True (default)
    )

    # Agent B: participates in internal A2A (explicit)
    overlord.create_agent(
        agent_id="calendar-agent",
        model=model,
        description="Manages calendar events",
        a2a_internal=True
    )

    # Agent C: does NOT participate in internal A2A
    overlord.create_agent(
        agent_id="private-agent",
        model=model,
        description="Private agent, no A2A",
        a2a_internal=False  # This agent won't be discoverable
    )

    print("\n=== A2A Discovery Test ===")
    print(f"Created {len(overlord.agents)} agents:")
    for agent_id in overlord.agents:
        agent = overlord.agents[agent_id]
        print(f"  - {agent_id}: a2a_internal={agent.a2a_internal}")

    # Test discovery from weather agent
    print("\n=== Weather Agent Discovery ===")
    available = agent_a.discover_agents()
    print(f"Weather agent discovered {len(available)} agents:")
    for agent_id, info in available.items():
        print(f"  - {agent_id}: {info['description']}")

    # Verify results
    assert "calendar-agent" in available, "Should find calendar agent"
    assert "private-agent" not in available, "Should NOT find private agent (a2a_internal=False)"
    assert "weather-agent" not in available, "Should NOT find itself"

    print("\n✅ Test passed! Single source of truth working correctly.")
    print("\n=== Key Benefits ===")
    print("1. Single source of truth: agent.a2a_internal")
    print("2. Simple check: getattr(agent, 'a2a_internal', True)")
    print("3. Clear configuration at agent creation time")
    print("4. Backwards compatible (defaults to True)")


if __name__ == "__main__":
    test_simple_a2a_discovery()
