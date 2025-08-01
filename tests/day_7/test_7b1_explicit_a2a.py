"""
Test 7B1 with explicit A2A instructions in agent system messages.
"""

import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


# Global to track A2A calls
a2a_interactions = []


@pytest.mark.asyncio
async def test_7b1_explicit_a2a_instructions():
    """Test A2A by adding explicit instructions to use A2A methods."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("TEST 7B1: Explicit A2A Communication Test")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    # Enhance agent system messages to explicitly use A2A
    print("\n📝 Enhancing agent system messages for explicit A2A...")
    
    # Update IT Support's system message
    if "it-support" in overlord.agents:
        it_agent = overlord.agents["it-support"]
        original_msg = it_agent.system_message
        it_agent.system_message = original_msg + """

IMPORTANT A2A COLLABORATION INSTRUCTIONS:
- You have access to filesystem and system-info tools ONLY
- You do NOT have access to Linear tools
- When asked to create Linear issues, you MUST use send_a2a_message() or request_consultation() to ask the project-manager agent for help
- Always check which tools you have access to before attempting tasks
- Use this format for A2A requests: await self.request_consultation('project-manager', 'Need help creating Linear issue', context={'details': '...'})
"""
        print("✓ IT Support agent enhanced with A2A instructions")
    
    # Update Project Manager's system message  
    if "project-manager" in overlord.agents:
        pm_agent = overlord.agents["project-manager"]
        original_msg = pm_agent.system_message
        pm_agent.system_message = original_msg + """

IMPORTANT A2A COLLABORATION INSTRUCTIONS:
- You have access to Linear tools ONLY
- You do NOT have access to system information tools
- When asked for system information, you MUST use send_a2a_message() or request_consultation() to ask the it-support agent for help
- Always be ready to help other agents who request Linear issue creation
- Use this format for A2A requests: await self.request_consultation('it-support', 'Need system information', context={'type': 'CPU/memory/disk'})
"""
        print("✓ Project Manager agent enhanced with A2A instructions")
    
    # Add logging to track A2A
    def track_a2a_calls(overlord):
        for agent_id, agent in overlord.agents.items():
            original_send = agent.send_a2a_message
            original_consultation = agent.request_consultation
            original_handle = agent.handle_a2a_message
            
            async def send_wrapper(*args, **kwargs):
                target = kwargs.get('target_agent_id', args[0] if args else 'unknown')
                print(f"\n🔵 A2A DETECTED: {agent_id} → {target}")
                a2a_interactions.append(f"{agent_id} → {target}")
                return await original_send(*args, **kwargs)
            
            async def consultation_wrapper(*args, **kwargs):
                target = kwargs.get('target_agent_id', args[0] if args else 'unknown')
                topic = kwargs.get('topic', args[1] if len(args) > 1 else 'unknown')
                print(f"\n🟡 CONSULTATION: {agent_id} → {target} (Topic: {topic})")
                a2a_interactions.append(f"CONSULTATION: {agent_id} → {target}")
                return await original_consultation(*args, **kwargs)
            
            async def handle_wrapper(*args, **kwargs):
                source = kwargs.get('source_agent_id', args[0] if args else 'unknown')
                print(f"\n🟢 A2A RECEIVED: {agent_id} ← {source}")
                a2a_interactions.append(f"{agent_id} ← {source}")
                return await original_handle(*args, **kwargs)
            
            agent.send_a2a_message = send_wrapper
            agent.request_consultation = consultation_wrapper
            agent.handle_a2a_message = handle_wrapper
    
    track_a2a_calls(overlord)
    
    # Test 1: IT Support needs Linear
    print("\n" + "-"*60)
    print("Test 1: IT Support asked to create Linear issue")
    print("-"*60)
    
    a2a_interactions.clear()
    
    response = await overlord.chat(
        message="You must create a Linear issue about disk space. Remember to use A2A to ask project-manager for help since you don't have Linear access.",
        agent_name="it-support",
        user_id="test_explicit"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"\nResponse preview: {response[:200]}...")
    
    # Check results
    print("\n" + "="*60)
    print("A2A Analysis")
    print("="*60)
    
    if a2a_interactions:
        print(f"✅ A2A COMMUNICATION DETECTED!")
        for interaction in a2a_interactions:
            print(f"   - {interaction}")
    else:
        print("❌ No A2A communication detected")
        print("\nDiagnostic info:")
        print("- Check if agents have a2a_internal=True")
        print("- Check if agent's process includes A2A logic")
        print("- May need to implement A2A in agent's tool selection logic")
    
    # Test 2: Project Manager needs system info
    print("\n\n" + "-"*60)
    print("Test 2: Project Manager asked for system info")
    print("-"*60)
    
    a2a_interactions.clear()
    
    response = await overlord.chat(
        message="Create a Linear issue with current memory usage. You'll need to use A2A to ask it-support for the system information.",
        agent_name="project-manager",
        user_id="test_explicit"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"\nResponse preview: {response[:200]}...")
    
    if a2a_interactions:
        print(f"\n✅ A2A COMMUNICATION DETECTED in Test 2!")
        for interaction in a2a_interactions:
            print(f"   - {interaction}")
    else:
        print("\n❌ No A2A communication in Test 2")


if __name__ == "__main__":
    asyncio.run(test_7b1_explicit_a2a_instructions())