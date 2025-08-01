"""
Debug test for verifying true A2A peer-to-peer communication.
This test adds logging and intercepts to verify agents are directly communicating.
"""

import pytest
import asyncio
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation
from tests.utils.env_setup import load_api_keys


# Global list to track A2A calls
a2a_calls = []


@pytest.mark.asyncio
async def test_debug_a2a_communication():
    """Debug test to trace A2A communication flow."""
    load_api_keys()
    
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml"
    )
    
    print("\n" + "="*80)
    print("DEBUG: A2A Communication Flow Test")
    print("="*80)
    
    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()
    
    # Patch the agents' A2A methods to log calls
    for agent_id, agent in overlord.agents.items():
        # Store original methods
        original_send = agent.send_a2a_message
        original_handle = agent.handle_a2a_message
        original_consultation = agent.request_consultation
        
        # Create wrapper for send_a2a_message
        async def make_send_wrapper(agent_id, original_method):
            async def send_wrapper(*args, **kwargs):
                target = kwargs.get('target_agent_id', args[0] if args else 'unknown')
                message = kwargs.get('message', args[1] if len(args) > 1 else 'unknown')
                
                print(f"\n🔵 A2A SEND: {agent_id} → {target}")
                print(f"   Message: {message}")
                
                a2a_calls.append({
                    'type': 'send',
                    'from': agent_id,
                    'to': target,
                    'message': message
                })
                
                # Call original method
                result = await original_method(*args, **kwargs)
                return result
            return send_wrapper
        
        # Create wrapper for handle_a2a_message
        async def make_handle_wrapper(agent_id, original_method):
            async def handle_wrapper(*args, **kwargs):
                source = kwargs.get('source_agent_id', args[0] if args else 'unknown')
                message = kwargs.get('message', args[1] if len(args) > 1 else 'unknown')
                
                print(f"\n🟢 A2A RECEIVE: {agent_id} ← {source}")
                print(f"   Message: {message}")
                
                a2a_calls.append({
                    'type': 'receive',
                    'from': source,
                    'to': agent_id,
                    'message': message
                })
                
                # Call original method
                result = await original_method(*args, **kwargs)
                print(f"   Response: {result}")
                return result
            return handle_wrapper
        
        # Create wrapper for request_consultation
        async def make_consultation_wrapper(agent_id, original_method):
            async def consultation_wrapper(*args, **kwargs):
                target = kwargs.get('target_agent_id', args[0] if args else 'unknown')
                topic = kwargs.get('topic', args[1] if len(args) > 1 else 'unknown')
                
                print(f"\n🟡 A2A CONSULTATION: {agent_id} → {target}")
                print(f"   Topic: {topic}")
                
                a2a_calls.append({
                    'type': 'consultation',
                    'from': agent_id,
                    'to': target,
                    'topic': topic
                })
                
                # Call original method
                result = await original_method(*args, **kwargs)
                return result
            return consultation_wrapper
        
        # Patch the methods
        agent.send_a2a_message = await make_send_wrapper(agent_id, original_send)
        agent.handle_a2a_message = await make_handle_wrapper(agent_id, original_handle)
        agent.request_consultation = await make_consultation_wrapper(agent_id, original_consultation)
    
    # Clear previous calls
    a2a_calls.clear()
    
    # Test 1: Direct agent request that requires A2A
    print("\n" + "-"*40)
    print("Test 1: IT Support asked to create Linear issue")
    print("-"*40)
    
    response = await overlord.chat(
        message="Create a Linear issue about the current disk space usage",
        agent_name="it-support",
        user_id="debug_test"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"\nFinal response preview: {response[:200]}...")
    
    # Analyze A2A calls
    print("\n" + "="*40)
    print(f"A2A Communication Analysis")
    print("="*40)
    print(f"Total A2A calls: {len(a2a_calls)}")
    
    for i, call in enumerate(a2a_calls):
        print(f"\n{i+1}. {call['type'].upper()}: {call['from']} → {call.get('to', 'N/A')}")
        if 'message' in call:
            print(f"   Message: {str(call['message'])[:100]}...")
        if 'topic' in call:
            print(f"   Topic: {call['topic']}")
    
    # Test 2: General request that might trigger A2A
    print("\n\n" + "-"*40)
    print("Test 2: General request for system info + Linear")
    print("-"*40)
    
    a2a_calls.clear()
    
    response = await overlord.chat(
        message="Create a Linear issue with the current CPU and memory usage",
        user_id="debug_test"
    )
    
    # Handle streaming
    if hasattr(response, '__aiter__'):
        full_response = ""
        async for chunk in response:
            full_response += chunk
        response = full_response
    
    print(f"\nFinal response preview: {response[:200]}...")
    
    print("\n" + "="*40)
    print(f"A2A Communication Analysis for Test 2")
    print("="*40)
    print(f"Total A2A calls: {len(a2a_calls)}")
    
    for i, call in enumerate(a2a_calls):
        print(f"\n{i+1}. {call['type'].upper()}: {call['from']} → {call.get('to', 'N/A')}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if len(a2a_calls) > 0:
        print("✅ A2A communication detected!")
        print(f"   - Total A2A interactions: {len(a2a_calls)}")
        
        # Count by type
        sends = sum(1 for c in a2a_calls if c['type'] == 'send')
        receives = sum(1 for c in a2a_calls if c['type'] == 'receive')
        consultations = sum(1 for c in a2a_calls if c['type'] == 'consultation')
        
        print(f"   - Sends: {sends}")
        print(f"   - Receives: {receives}")
        print(f"   - Consultations: {consultations}")
    else:
        print("❌ No A2A communication detected!")
        print("   Agents may be using other mechanisms or A2A is not properly configured")


if __name__ == "__main__":
    asyncio.run(test_debug_a2a_communication())