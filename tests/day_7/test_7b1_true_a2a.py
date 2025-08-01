"""
Test 7B1 with patched agent tools to force true A2A communication.
"""

import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys
from patch_agent_tools import patch_agent_tools, prepare_agents_for_a2a


# Global list to track A2A calls
a2a_calls = []


def setup_a2a_logging(overlord):
    """Set up logging for A2A communication."""
    for agent_id, agent in overlord.agents.items():
        # Store original methods
        original_send = agent.send_a2a_message
        original_handle = agent.handle_a2a_message
        original_agent_id = agent_id  # Capture in closure
        
        # Create wrapper for send_a2a_message
        async def send_wrapper(*args, **kwargs):
            target = kwargs.get('target_agent_id', args[0] if args else 'unknown')
            message = kwargs.get('message', args[1] if len(args) > 1 else 'unknown')
            
            print(f"\n🔵 A2A SEND: {original_agent_id} → {target}")
            print(f"   Message type: {kwargs.get('message_type', 'unknown')}")
            
            a2a_calls.append({
                'type': 'send',
                'from': original_agent_id,
                'to': target,
                'message': str(message)[:100]
            })
            
            result = await original_send(*args, **kwargs)
            return result
        
        # Create wrapper for handle_a2a_message  
        async def handle_wrapper(*args, **kwargs):
            source = kwargs.get('source_agent_id', args[0] if args else 'unknown')
            
            print(f"\n🟢 A2A RECEIVE: {original_agent_id} ← {source}")
            
            a2a_calls.append({
                'type': 'receive',
                'from': source,
                'to': original_agent_id
            })
            
            result = await original_handle(*args, **kwargs)
            return result
        
        # Apply wrappers
        agent.send_a2a_message = send_wrapper
        agent.handle_a2a_message = handle_wrapper


@pytest.mark.asyncio
async def test_7b1_true_a2a_with_patch():
    """Test true A2A communication with tool filtering patch."""
    load_api_keys()
    
    # Apply the patch BEFORE loading formation
    patch_agent_tools()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("TEST 7B1: True A2A Communication with Tool Filtering")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    # Prepare agents with their specific MCP servers
    prepare_agents_for_a2a(overlord)
    
    # Set up A2A logging
    setup_a2a_logging(overlord)
    
    # Clear previous calls
    a2a_calls.clear()
    
    print("\n" + "-"*60)
    print("Test: IT Support asked to create Linear issue")
    print("(IT Support has NO access to Linear MCP)")
    print("-"*60)
    
    response = await overlord.chat(
        message="Create a Linear issue about the current disk space usage",
        agent_name="it-support",
        user_id="test_true_a2a"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"\nResponse preview: {response[:200]}...")
    
    # Analyze results
    print("\n" + "="*60)
    print("A2A Communication Analysis")
    print("="*60)
    
    if len(a2a_calls) > 0:
        print(f"✅ TRUE A2A DETECTED! {len(a2a_calls)} A2A interactions")
        for i, call in enumerate(a2a_calls):
            print(f"\n{i+1}. {call['type'].upper()}: {call['from']} → {call['to']}")
            if 'message' in call:
                print(f"   Message: {call['message']}")
    else:
        print("❌ No A2A communication detected")
        print("\nPossible reasons:")
        print("1. Agent didn't recognize it needs help")
        print("2. Agent system message needs to encourage collaboration")
        print("3. A2A methods need to be called explicitly")
    
    # Check the response content
    response_lower = response.lower()
    
    if "don't have access" in response_lower or "need help" in response_lower:
        print("\n✓ Agent recognized it doesn't have Linear access")
    elif "linear" in response_lower and "issue" in response_lower:
        print("\n? Agent somehow created Linear issue without A2A")
    else:
        print("\n✓ Agent couldn't complete the task")


if __name__ == "__main__":
    asyncio.run(test_7b1_true_a2a_with_patch())