#!/usr/bin/env python3
"""
Debug script for testing registration and deregistration URL matching
"""

import asyncio
import sys
import yaml

# Add the runtime directory to Python path
sys.path.insert(0, '../runtime')

from muxi.runtime.overlord import Overlord  # noqa: E402
from muxi.runtime.llm import LLM  # noqa: E402


async def debug_registration_deregistration():
    """Debug registration and deregistration URL matching"""

    print("🔍 Debug: Testing Registration/Deregistration URL Matching")
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
    overlord = Overlord(formation_config=formation_config)

    # Create a test agent
    print("\n1️⃣ Creating agent...")
    agent = overlord.create_agent(
        agent_id="debug-agent",
        model=model,
        system_message="Debug test agent",
        a2a_external=True
    )

    print(f"   ✅ Created agent: {agent.agent_id}")

    # Wait for registration to complete
    print("\n2️⃣ Waiting for auto-registration...")
    await asyncio.sleep(3)

    # Check if agent appears in discovery
    print("\n3️⃣ Checking discovery...")
    if overlord.external_registry_client:
        responses = await overlord.external_registry_client.discover_agents()
        for registry_url, agents in responses.items():
            agent_names = [agent.name for agent in agents]
            print(f"   Registry {registry_url}: {len(agents)} agents")
            if "debug-agent" in agent_names:
                print("   ✅ debug-agent found in registry!")
            else:
                print("   ❌ debug-agent NOT found in registry")
                print(f"   Available agents: {agent_names}")

    # Test manual deregistration
    print("\n4️⃣ Testing manual deregistration...")
    if overlord.external_registry_client:
        result = await overlord.external_registry_client.deregister_agent(
            "http://localhost:8080/debug-agent"
        )
        for registry_url, response in result.items():
            if response.success:
                print(f"   ✅ Manual deregistration successful on {registry_url}")
            else:
                print(f"   ❌ Manual deregistration failed on {registry_url}: {response.error}")

    # Test automatic deregistration via remove_agent
    print("\n5️⃣ Testing automatic deregistration via remove_agent...")

    # First re-register the agent for clean test
    if overlord.external_registry_client:
        success = await overlord.register_agent_with_external_registry("debug-agent")
        if success:
            print("   ✅ Re-registered agent for deregistration test")
        else:
            print("   ❌ Failed to re-register agent")

    # Wait a moment
    await asyncio.sleep(2)

    # Now remove the agent (should trigger auto-deregistration)
    try:
        overlord.remove_agent("debug-agent")
        print("   ✅ Called remove_agent")

        # Wait for async deregistration
        await asyncio.sleep(3)

        # Check if agent was deregistered
        if overlord.external_registry_client:
            responses = await overlord.external_registry_client.discover_agents()
            for registry_url, agents in responses.items():
                agent_names = [agent.name for agent in agents]
                if "debug-agent" in agent_names:
                    print("   ❌ debug-agent still found in registry after removal!")
                else:
                    print("   ✅ debug-agent successfully removed from registry!")

    except Exception as e:
        print(f"   ❌ Error during remove_agent: {e}")

    print("\n🏁 Debug complete")


if __name__ == "__main__":
    asyncio.run(debug_registration_deregistration())
