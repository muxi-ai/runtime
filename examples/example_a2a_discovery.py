#!/usr/bin/env python3
"""
Example: A2A Local Discovery Service Usage

This example demonstrates how to use the Local Discovery Service for
Agent-to-Agent (A2A) communication within MUXI formations.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the runtime to the path for testing from examples directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.muxi.runtime.a2a.discovery import (  # noqa: E402
    LocalDiscoveryService,
    DiscoveryConfig,
    DiscoveryServiceManager
)
from runtime.muxi.runtime.a2a.models import AgentCard, A2ACapability  # noqa: E402


async def example_basic_discovery():
    """Example of basic discovery service usage"""
    print("=== Basic Discovery Service Example ===\n")

    # Create discovery service configuration
    config = DiscoveryConfig(
        health_check_interval=30,  # Check health every 30 seconds
        agent_timeout=120,         # Mark agents as unreachable after 2 minutes
        enable_persistence=True,   # Save registry to disk
        registry_file="./discovery_registry.json"
    )

    # Create and start discovery service
    discovery = LocalDiscoveryService(config)
    await discovery.start("example_formation", 8080)

    print("✓ Discovery service started for formation 'example_formation'")

    # Create some example agent cards
    search_agent_card = AgentCard(
        name="Search Agent",
        description="Provides search capabilities across multiple data sources",
        version="1.0.0",
        url="http://localhost:8081"
    )

    # Add capabilities
    search_agent_card.add_capability(A2ACapability(
        name="web_search",
        description="Search the web for information",
        enabled=True
    ))
    search_agent_card.add_capability(A2ACapability(
        name="document_search",
        description="Search through document collections",
        enabled=True
    ))

    analysis_agent_card = AgentCard(
        name="Analysis Agent",
        description="Provides data analysis and visualization capabilities",
        version="1.0.0",
        url="http://localhost:8082"
    )

    analysis_agent_card.add_capability(A2ACapability(
        name="data_analysis",
        description="Analyze datasets and generate insights",
        enabled=True
    ))
    analysis_agent_card.add_capability(A2ACapability(
        name="visualization",
        description="Create charts and visualizations",
        enabled=True
    ))

    # Register agents
    try:
        search_result = await discovery.register_agent(
            "search_agent_001",
            "http://localhost:8081",
            search_agent_card
        )
        print(f"✓ Registered search agent: {search_result}")

        analysis_result = await discovery.register_agent(
            "analysis_agent_001",
            "http://localhost:8082",
            analysis_agent_card
        )
        print(f"✓ Registered analysis agent: {analysis_result}")

    except Exception as e:
        print(f"Note: Agent registration failed (expected in demo): {e}")

    # Discover all agents
    print("\n--- Discovering All Agents ---")
    all_agents = discovery.discover_agents()
    for agent in all_agents:
        print(f"Agent: {agent['name']} ({agent['agent_id']})")
        print(f"  Status: {agent['status']}")
        print(f"  Capabilities: {agent['capabilities']}")
        print(f"  Health Score: {agent['health_score']}")
        print()

    # Discover agents with specific capabilities
    print("--- Discovering Agents with 'web_search' Capability ---")
    search_agents = discovery.discover_agents(capability_filter=["web_search"])
    for agent in search_agents:
        print(f"Found: {agent['name']} with web_search capability")

    # Get formation status
    print("\n--- Formation Status ---")
    status = discovery.get_formation_status()
    print(json.dumps(status, indent=2))

    # Stop the service
    await discovery.stop()
    print("\n✓ Discovery service stopped")


async def example_multi_formation():
    """Example of managing multiple formations"""
    print("\n=== Multi-Formation Discovery Example ===\n")

    # Create discovery service manager
    manager = DiscoveryServiceManager()

    # Create services for different formations
    config = DiscoveryConfig(health_check_interval=0, enable_persistence=False)

    await manager.create_service("frontend_formation", config)
    await manager.create_service("backend_formation", config)

    print("✓ Created discovery services for multiple formations")

    # List all formations
    formations = manager.list_formations()
    print(f"Active formations: {formations}")

    # Get global status
    global_status = manager.get_global_status()
    print(f"Global status: {json.dumps(global_status, indent=2)}")

    # Stop all services
    await manager.stop_all_services()
    print("✓ All discovery services stopped")


async def example_agent_monitoring():
    """Example of agent health monitoring"""
    print("\n=== Agent Health Monitoring Example ===\n")

    config = DiscoveryConfig(
        health_check_interval=5,  # Fast health checks for demo
        agent_timeout=15,
        enable_persistence=False
    )

    discovery = LocalDiscoveryService(config)
    await discovery.start("monitoring_formation", 8080)

    print("✓ Started discovery service with health monitoring")

    # Create a test agent card
    test_card = AgentCard(
        name="Test Agent",
        description="Agent for monitoring demonstration",
        version="1.0.0",
        url="http://localhost:8083"
    )
    test_card.add_capability(A2ACapability(name="test", enabled=True))

    # Register agent (will fail health checks since no real server)
    try:
        await discovery.register_agent("test_agent", "http://localhost:8083", test_card)
        print("✓ Registered test agent")
    except Exception as e:
        print(f"Note: Registration failed (expected): {e}")

    # Show how to get detailed agent info
    agent_info = discovery.get_agent_info("test_agent")
    if agent_info:
        print(f"Agent info: {json.dumps(agent_info, indent=2)}")

    await discovery.stop()
    print("✓ Monitoring example completed")


async def main():
    """Run all discovery service examples"""
    print("A2A DISCOVERY SERVICE EXAMPLES")
    print("=" * 50)

    await example_basic_discovery()
    await example_multi_formation()
    await example_agent_monitoring()

    print("\n" + "=" * 50)
    print("🎉 All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
