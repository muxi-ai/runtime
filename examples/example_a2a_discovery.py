#!/usr/bin/env python3
"""
Example: Simple A2A Discovery Usage

This example demonstrates the new simplified A2A discovery approach where
agents simply ask their overlord to discover other agents in the formation.
No HTTP servers, no complex discovery services - just simple method calls!
"""

import sys
from pathlib import Path

# Add the runtime to the path for testing from examples directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.muxi.runtime.overlord import Overlord  # noqa: E402
from runtime.muxi.runtime.llm import LLM  # noqa: E402


def example_basic_discovery():
    """Example of basic A2A discovery using the overlord"""
    print("=== Basic A2A Discovery Example ===\n")

    # Create overlord (formation manager)
    overlord = Overlord()
    print("✓ Created overlord (formation manager)")

    # Create a mock model for agents
    model = LLM(model="openai/gpt-4o-mini")

    # Create agents with different capabilities
    weather_agent = overlord.create_agent(
        agent_id="weather-agent",
        model=model,
        description="Provides weather information and forecasts",
        a2a_internal=True,  # Participates in A2A
        a2a_external=True
    )

    calendar_agent = overlord.create_agent(
        agent_id="calendar-agent",
        model=model,
        description="Manages calendar events and scheduling",
        a2a_internal=True,  # Participates in A2A
        a2a_external=True
    )

    email_agent = overlord.create_agent(
        agent_id="email-agent",
        model=model,
        description="Handles email communication",
        a2a_internal=False,  # Does NOT participate in A2A
        a2a_external=True
    )

    print("✓ Created 3 agents in the formation")
    print(f"  - {weather_agent.agent_id}: A2A enabled")
    print(f"  - {calendar_agent.agent_id}: A2A enabled")
    print(f"  - {email_agent.agent_id}: A2A disabled")

    # Weather agent discovers other agents
    print("\n--- Weather Agent Discovering Peers ---")
    discovered = weather_agent.discover_agents()

    print(f"Weather agent discovered {len(discovered)} other agents:")
    for agent_id, info in discovered.items():
        print(f"  - {agent_id}: {info['description']}")
        print(f"    Status: {info['status']}")
        print(f"    Capabilities: {info.get('capabilities', 'N/A')}")

    return overlord, weather_agent, calendar_agent, email_agent


def example_capability_filtering(overlord, weather_agent):
    """Example of discovering agents with specific capabilities"""
    print("\n=== Capability-Based Discovery Example ===\n")

    # Create agents with specific capabilities
    search_agent = overlord.create_agent(
        agent_id="search-agent",
        model=LLM(model="openai/gpt-4o-mini"),
        description="Provides web and document search capabilities",
        a2a_internal=True
    )

    # Mock adding capabilities (in real implementation, this would be more structured)
    search_agent.capabilities = ["web_search", "document_search"]

    analysis_agent = overlord.create_agent(
        agent_id="analysis-agent",
        model=LLM(model="openai/gpt-4o-mini"),
        description="Provides data analysis and visualization",
        a2a_internal=True
    )

    analysis_agent.capabilities = ["data_analysis", "visualization"]

    print("✓ Created agents with specific capabilities:")
    print(f"  - {search_agent.agent_id}: {search_agent.capabilities}")
    print(f"  - {analysis_agent.agent_id}: {analysis_agent.capabilities}")

    # Discover agents with search capabilities
    print("\n--- Discovering Agents with Search Capabilities ---")
    search_capable = weather_agent.discover_agents(capability_filter=["web_search"])

    for agent_id, info in search_capable.items():
        print(f"Found: {agent_id} with search capabilities")
        print(f"  Capabilities: {info.get('capabilities', [])}")


def example_a2a_configuration():
    """Example showing different A2A configuration scenarios"""
    print("\n=== A2A Configuration Examples ===\n")

    overlord = Overlord()
    model = LLM(model="openai/gpt-4o-mini")

    # Different A2A configurations
    agents = {
        "public-agent": overlord.create_agent(
            agent_id="public-agent",
            model=model,
            description="Public-facing agent",
            a2a_internal=True,   # Can talk to other agents in formation
            a2a_external=True    # Can talk to agents in other formations
        ),

        "internal-only": overlord.create_agent(
            agent_id="internal-only",
            model=model,
            description="Internal operations agent",
            a2a_internal=True,   # Can talk to agents in formation
            a2a_external=False   # Cannot talk to external agents
        ),

        "isolated-agent": overlord.create_agent(
            agent_id="isolated-agent",
            model=model,
            description="Isolated processing agent",
            a2a_internal=False,  # Cannot talk to any agents
            a2a_external=False
        )
    }

    print("✓ Created agents with different A2A configurations:")
    for agent_id, agent in agents.items():
        print(f"  - {agent_id}:")
        print(f"    Internal A2A: {agent.a2a_internal}")
        print(f"    External A2A: {agent.a2a_external}")

    # Test discovery from different perspectives
    print("\n--- Discovery Results ---")

    print("Public agent discovers:")
    public_discovered = agents["public-agent"].discover_agents()
    for agent_id, info in public_discovered.items():
        print(f"  - {agent_id}: {info['description']}")

    print("\nIsolated agent discovers:")
    isolated_discovered = agents["isolated-agent"].discover_agents()
    print(f"  - Found {len(isolated_discovered)} agents (should be same as above)")
    print("  - Note: Isolated agent can discover others, but others cannot discover it")

    # Show overlord perspective
    print("\n--- Overlord's Full View ---")
    all_agents = overlord.list_agents()
    print(f"Overlord manages {len(all_agents)} total agents:")
    for agent_id, info in all_agents.items():
        print(f"  - {agent_id}: {info['description']}")


def example_formation_management():
    """Example of managing agents in a formation"""
    print("\n=== Formation Management Example ===\n")

    overlord = Overlord()
    model = LLM(model="openai/gpt-4o-mini")

    print("Building a customer service formation...")

    # Create a formation for customer service
    agents = []
    agent_configs = [
        ("ticket-router", "Routes customer tickets to appropriate agents", True),
        ("billing-agent", "Handles billing inquiries and payments", True),
        ("tech-support", "Provides technical support and troubleshooting", True),
        ("escalation-agent", "Handles escalated issues", True),
        ("audit-agent", "Monitors interactions for quality", False)  # Internal only
    ]

    for agent_id, description, a2a_enabled in agent_configs:
        agent = overlord.create_agent(
            agent_id=agent_id,
            model=model,
            description=description,
            a2a_internal=a2a_enabled
        )
        agents.append(agent)

    print(f"✓ Created {len(agents)} agents in customer service formation")

    # Simulate ticket router discovering available agents
    router = next(a for a in agents if a.agent_id == "ticket-router")
    available_agents = router.discover_agents()

    print(f"\nTicket router can route to {len(available_agents)} agents:")
    for agent_id, info in available_agents.items():
        print(f"  - {agent_id}: {info['description']}")

    # Show formation status
    print(f"\nFormation status:")
    print(f"  Total agents: {len(overlord.list_agents())}")
    print(f"  A2A enabled: {len(available_agents) + 1}")  # +1 for router itself
    print(f"  A2A disabled: {len(overlord.list_agents()) - len(available_agents) - 1}")


def main():
    """Run all A2A discovery examples"""
    print("SIMPLE A2A DISCOVERY EXAMPLES")
    print("=" * 50)
    print("No HTTP servers, no complex discovery services!")
    print("Just agents asking their overlord: 'Who else is here?'\n")

    # Run examples
    overlord, weather_agent, calendar_agent, email_agent = example_basic_discovery()
    example_capability_filtering(overlord, weather_agent)
    example_a2a_configuration()
    example_formation_management()

    print("\n" + "=" * 50)
    print("🎉 All examples completed!")
    print("\nKey Takeaways:")
    print("- A2A discovery is now trivially simple")
    print("- Agents just call discover_agents() on themselves")
    print("- Overlord already knows everything")
    print("- No HTTP, no ports, no complex setup needed")
    print("- Single source of truth: agent.a2a_internal")


if __name__ == "__main__":
    main()
