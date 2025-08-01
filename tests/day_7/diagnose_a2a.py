#!/usr/bin/env python3
"""
Diagnose A2A communication behavior
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


async def diagnose_a2a():
    """Check if A2A is properly configured and working."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("Loading formation...")
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    print(f"\n1. Workflow disabled: {not overlord.auto_decomposition}")
    print(f"2. A2A internal enabled: {overlord.a2a_coordinator.config.internal.enabled if hasattr(overlord, 'a2a_coordinator') else 'Not configured'}")
    
    # Check if agents have A2A methods
    print("\n3. Agent A2A capabilities:")
    for agent_id, agent in overlord.agents.items():
        has_a2a = hasattr(agent, 'send_a2a_message')
        print(f"   - {agent_id}: {'✓' if has_a2a else '✗'} A2A methods available")
    
    # Test A2A discovery
    print("\n4. Testing A2A agent discovery:")
    if hasattr(overlord, 'a2a_coordinator'):
        available = overlord.a2a_coordinator.get_available_agents_for_a2a("it-support")
        print(f"   IT Support can discover: {list(available.keys())}")
    
    # Simple direct agent request
    print("\n5. Direct agent request to IT Support (needs Linear):")
    response = await overlord.chat(
        message="Create a Linear issue about disk space",
        agent_name="it-support",
        user_id="test_diag"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"Response preview: {response[:200]}...")
    
    # Check if response indicates A2A need
    if "project manager" in response.lower() or "don't have access" in response.lower():
        print("✓ IT Support recognizes it needs help")
    else:
        print("✗ IT Support didn't indicate need for help")


if __name__ == "__main__":
    asyncio.run(diagnose_a2a())