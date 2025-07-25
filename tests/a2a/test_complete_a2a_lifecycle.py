#!/usr/bin/env python3
"""
Complete A2A Lifecycle Test

This test verifies the full A2A lifecycle:
1. Auto-registration when agents are created
2. Auto-deregistration when agents are removed
3. Auto-deregistration when overlord shuts down
"""

import asyncio
import sys
import yaml

# Add the runtime directory to Python path
sys.path.insert(0, '..')

from src.muxi.overlord import Overlord  # noqa: E402
from src.muxi.llm import LLM  # noqa: E402


async def test_complete_a2a_lifecycle():
    """Test the complete A2A lifecycle with auto-registration and deregistration"""

    print("🚀 Testing Complete A2A Lifecycle")
    print("=" * 60)

    # Load formation config
    with open('test-formation.yaml', 'r') as f:
        formation_config = yaml.safe_load(f)

    # Create model
    model = LLM(
        model="gpt-4o-mini",
        api_key="test-key-not-used",
        temperature=0.7
    )

    # Create overlord with formation config
    overlord = Overlord(
        formation_config=formation_config,
        request_timeout=30
    )

    print("✅ Created overlord with external registry configuration")

    # Initialize external registry async
    await overlord.initialize_external_registry_async()

    print("✅ Initialized external registry client")

    # Check registry health
    if overlord.external_registry_client:
        health_responses = await overlord.external_registry_client.health_check_all()
        if health_responses:
            print(f"✅ Registry health check passed: {list(health_responses.keys())}")
        else:
            print("❌ Registry health check failed")
            return
    else:
        print("❌ No external registry client configured")
        return

    print("\n🔄 Phase 1: Auto-Registration Test")
    print("-" * 40)

    # Create agents (should auto-register)
    overlord.create_agent(
        agent_id="lifecycle-agent-1",
        model=model,
        system_message="I am a test agent for lifecycle testing",
        description="Agent for testing A2A lifecycle functionality",
        a2a_external=True
    )

    overlord.create_agent(
        agent_id="lifecycle-agent-2",
        model=model,
        system_message="I am another test agent",
        description="Second agent for lifecycle testing",
        a2a_external=True
    )

    print("✅ Created 2 agents with a2a_external=True")

    # Wait a moment for registration to complete
    await asyncio.sleep(2)

    # Check if agents are registered
    discovery_responses = await overlord.external_registry_client.discover_agents()

    registered_agents = []
    for registry_url, response in discovery_responses.items():
        if hasattr(response, 'success') and response.success and response.data:
            agents = response.data.get('agents', [])
            registered_agents.extend([
                agent.get('name') for agent in agents if isinstance(agent, dict)
            ])
        elif isinstance(response, list):
            # Handle case where response is directly a list of agents
            registered_agents.extend([
                agent.get('name') for agent in response if isinstance(agent, dict)
            ])

    lifecycle_agents = [
        name for name in registered_agents if name.startswith('lifecycle-agent')
    ]

    print(f"✅ Found {len(lifecycle_agents)} lifecycle agents in registry:")
    for agent_name in lifecycle_agents:
        print(f"   - {agent_name}")

    if len(lifecycle_agents) >= 2:
        print("✅ Auto-registration working correctly")
    else:
        print("❌ Auto-registration failed - not all agents registered")

    print("\n🗑️ Phase 2: Manual Deregistration Test")
    print("-" * 40)

    # Remove one agent (should auto-deregister)
    success = overlord.remove_agent("lifecycle-agent-1")
    print(f"✅ Removed agent 'lifecycle-agent-1': {success}")

    # Wait for deregistration
    await asyncio.sleep(2)

    # Check registry again
    discovery_responses = await overlord.external_registry_client.discover_agents()

    remaining_agents = []
    for registry_url, response in discovery_responses.items():
        if hasattr(response, 'success') and response.success and response.data:
            agents = response.data.get('agents', [])
            remaining_agents.extend([
                agent.get('name') for agent in agents if isinstance(agent, dict)
            ])
        elif isinstance(response, list):
            # Handle case where response is directly a list of agents
            remaining_agents.extend([
                agent.get('name') for agent in response if isinstance(agent, dict)
            ])

    lifecycle_agents_remaining = [
        name for name in remaining_agents if name.startswith('lifecycle-agent')
    ]

    print(f"✅ Found {len(lifecycle_agents_remaining)} lifecycle agents remaining:")
    for agent_name in lifecycle_agents_remaining:
        print(f"   - {agent_name}")

    manual_dereg_success = (
        len(lifecycle_agents_remaining) == 1 and
        'lifecycle-agent-2' in lifecycle_agents_remaining
    )
    if manual_dereg_success:
        print("✅ Manual deregistration working correctly")
    else:
        print("❌ Manual deregistration failed")

    print("\n💀 Phase 3: Shutdown Deregistration Test")
    print("-" * 40)

    # Test graceful shutdown (should deregister remaining agents)
    print("🔄 Testing graceful shutdown...")
    await overlord.shutdown()

    # Wait for shutdown to complete
    await asyncio.sleep(3)

    # Check registry one final time
    # Note: We can't use the overlord's client anymore since it's shut down
    # So we'll create a fresh client for this check
    from src.muxi.a2a.registry_client import A2ARegistryClient  # noqa: E402

    fresh_client = A2ARegistryClient(
        registries=formation_config['a2a']['registries']
    )
    discovery_responses = await fresh_client.discover_agents()

    final_agents = []
    for registry_url, response in discovery_responses.items():
        if hasattr(response, 'success') and response.success and response.data:
            agents = response.data.get('agents', [])
            final_agents.extend([
                agent.get('name') for agent in agents if isinstance(agent, dict)
            ])
        elif isinstance(response, list):
            # Handle case where response is directly a list of agents
            final_agents.extend([
                agent.get('name') for agent in response if isinstance(agent, dict)
            ])

    final_lifecycle_agents = [
        name for name in final_agents if name.startswith('lifecycle-agent')
    ]

    print(f"✅ Found {len(final_lifecycle_agents)} lifecycle agents after shutdown:")
    for agent_name in final_lifecycle_agents:
        print(f"   - {agent_name}")

    await fresh_client.close()

    if len(final_lifecycle_agents) == 0:
        print("✅ Shutdown deregistration working correctly")
    else:
        print("❌ Shutdown deregistration failed - agents still registered")

    print("\n🎯 Test Summary")
    print("=" * 60)

    # Calculate results
    auto_reg_pass = len(lifecycle_agents) >= 2
    shutdown_dereg_pass = len(final_lifecycle_agents) == 0

    print(f"Auto-registration:     {'✅ PASS' if auto_reg_pass else '❌ FAIL'}")
    print(f"Manual deregistration: {'✅ PASS' if manual_dereg_success else '❌ FAIL'}")
    print(f"Shutdown deregistration: {'✅ PASS' if shutdown_dereg_pass else '❌ FAIL'}")

    if auto_reg_pass and manual_dereg_success and shutdown_dereg_pass:
        print("\n🎉 ALL TESTS PASSED! A2A lifecycle working correctly.")
        return True
    else:
        print("\n💥 SOME TESTS FAILED! Check the implementation.")
        return False


async def main():
    """Main test runner"""
    try:
        success = await test_complete_a2a_lifecycle()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
