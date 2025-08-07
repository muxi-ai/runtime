#!/usr/bin/env python3
"""
Test Formation 1 with Filtering Debug - Requester
This formation makes requests and shows filtering debug information.
"""

import asyncio
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_external_a2a_with_filtering():
    """Test external A2A communication with filtering debug output."""
    print("Starting Formation 1 (Requester) with Filtering Debug...")
    print("=" * 60)
    print("\nMake sure Formation 2 is running first!")
    print("Run: python test_formation2_provider.py")
    print("=" * 60)

    # Give user time to read the message
    await asyncio.sleep(2)

    formation = Formation()

    try:
        # Load the formation configuration
        await formation.load("test-formations/formation-a2a/formation1/formation.yaml")

        # Start the overlord
        overlord = await formation.start_overlord()

        print("\n✅ Formation 1 is running with filtering enabled!")
        print("\nConfiguration:")
        print(f"  - Filtering enabled: {overlord.formation_config.get('a2a', {}).get('filtering', {}).get('enabled', False)}")  # noqa: E501
        print(f"  - Threshold: {overlord.formation_config.get('a2a', {}).get('filtering', {}).get('threshold', 50)}")  # noqa: E501
        print(f"  - Min relevance score: {overlord.formation_config.get('a2a', {}).get('filtering', {}).get('min_relevance_score', 0.3)}")  # noqa: E501

        print("\nLocal agents:")
        for agent_id in overlord.agents.keys():
            print(f"  - {agent_id}")

        # Wait a moment for everything to initialize
        await asyncio.sleep(2)

        # Get the A2A coordinator
        a2a_coordinator = overlord.a2a_coordinator

        # Test 1: Check all available agents (before filtering)
        print("\n" + "=" * 60)
        print("TEST 1: Getting all available agents (internal + external)")
        print("=" * 60)

        all_agents = await a2a_coordinator.get_all_available_agents(
            requesting_agent_id="test-requester",
            include_external=True
        )

        print(f"\nTotal agents available: {len(all_agents)}")
        for agent_id, agent_info in all_agents.items():
            print(f"\n  Agent: {agent_id}")
            print(f"    Type: {agent_info.get('type')}")
            print(f"    Formation: {agent_info.get('formation')}")
            print(f"    Capabilities: {agent_info.get('capabilities', [])}")
            print(f"    Allow filtering: {agent_info.get('allow_filtering', True)}")

        # Test 2: Test filtering with a specific task
        print("\n" + "=" * 60)
        print("TEST 2: Testing filtering for task planning")
        print("=" * 60)

        test_task = "Create a Linear issue with system information"
        print(f"\nTask: {test_task}")

        # Check if planning filter is initialized
        if a2a_coordinator.planning_filter:
            print("\n✅ Planning filter is initialized!")

            # Get relevant agents for planning
            print("\nApplying filtering...")
            relevant_agents = await a2a_coordinator.get_relevant_agents_for_planning(
                requesting_agent_id="test-requester",
                task=test_task,
                context={"type": "issue_creation", "target": "linear"}
            )

            print(f"\nFiltered agents count: {len(relevant_agents)} (from {len(all_agents)} total)")

            if len(relevant_agents) < len(all_agents):
                print("✅ Filtering reduced agent pool!")
            else:
                print("⚠️ No filtering occurred (all agents included)")

            print("\nFiltered agents:")
            for agent_id, agent_info in relevant_agents.items():
                print(f"  - {agent_id} ({agent_info.get('type')})")

            # Test cache
            print("\n" + "=" * 60)
            print("TEST 3: Testing cache functionality")
            print("=" * 60)

            # Call again to test cache
            print("\nCalling filtering again (should use cache)...")
            relevant_agents_2 = await a2a_coordinator.get_relevant_agents_for_planning(
                requesting_agent_id="test-requester",
                task=test_task,
                context={"type": "issue_creation", "target": "linear"}
            )

            if relevant_agents == relevant_agents_2:
                print("✅ Cache is working (same results returned)")
            else:
                print("⚠️ Different results returned (cache might not be working)")

            # Test bypass cache
            print("\nBypassing cache for fresh analysis...")
            # Add 'id' field to agents for planning_filter
            agents_with_id = []
            for agent_id, agent_info in all_agents.items():
                agent_with_id = agent_info.copy()
                agent_with_id['id'] = agent_id
                agents_with_id.append(agent_with_id)

            relevant_agents_3 = await a2a_coordinator.planning_filter.get_relevant_agents(
                task=test_task,
                all_agents=agents_with_id,
                context={"type": "issue_creation", "target": "linear"},
                bypass_cache=True
            )
            print(f"Fresh filtering returned {len(relevant_agents_3)} agents")

        else:
            print("\n⚠️ Planning filter not initialized - check configuration")

        # Test 4: Actually execute the task
        print("\n" + "=" * 60)
        print("TEST 4: Executing actual task")
        print("=" * 60)

        response = await overlord.chat(
            test_task,
            user_id="test_user",
            stream=False
        )

        response_text = response.text if hasattr(response, 'text') else str(response)
        print("\nTask completed successfully!")
        print(f"Response preview: {response_text[:200]}...")

        # Check cache stats
        if hasattr(overlord, 'a2a_cache_manager'):
            print("\n" + "=" * 60)
            print("CACHE STATISTICS")
            print("=" * 60)
            cache_stats = overlord.a2a_cache_manager.get_cache_stats()
            print(json.dumps(cache_stats, indent=2))

    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean shutdown
        print("\nShutting down Formation 1...")
        try:
            await formation.stop_overlord()
            formation.shutdown()
            print("Formation 1 stopped cleanly.")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(test_external_a2a_with_filtering())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
