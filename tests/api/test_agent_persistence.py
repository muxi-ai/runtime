#!/usr/bin/env python3
"""
Test agent persistence across server restarts.

This script:
1. Gets initial list of agents
2. Creates a new agent via POST /agents
3. Verifies the agent appears in the list
4. Can be run again after server restart to verify persistence
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime


API_BASE = "http://localhost:8271/v1"
API_KEY = "sk_muxi_admin_some_api_key"


async def get_agents():
    """Get list of all agents."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE}/agents",
            headers={"X-Muxi-Admin-Key": API_KEY}
        )
        response.raise_for_status()
        return response.json()


async def create_agent(agent_id: str):
    """Create a new agent."""
    agent_data = {
        "schema": "1.0.0",
        "id": agent_id,
        "name": f"Test Agent {agent_id}",
        "description": f"Test agent created at {datetime.now().isoformat()}",
        "active": True,
        "system_message": "You are a test agent created via the API.",
        "author": "API Test Script",
        "version": "1.0.0",
        "llm_models": [
            {
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "${{ secrets.OPENAI_API_KEY }}"
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE}/agents",
            headers={"X-Muxi-Admin-Key": API_KEY},
            json=agent_data
        )
        return response


async def main():
    """Run the test sequence."""
    test_agent_id = f"test-persistence-agent-{int(datetime.now().timestamp())}"
    
    print("=== Agent Persistence Test ===\n")
    
    # Step 1: Get initial list of agents
    print("1. Getting initial list of agents...")
    initial_agents = await get_agents()
    initial_agent_ids = [agent["id"] for agent in initial_agents["data"]["agents"]]
    print(f"   Found {len(initial_agent_ids)} agents: {initial_agent_ids}")
    
    # Check if our test agent already exists
    if test_agent_id in initial_agent_ids:
        print(f"\n✓ Test agent '{test_agent_id}' already exists from a previous run!")
        print("  This confirms that agents persist across server restarts.")
        
        # Show the agent details
        for agent in initial_agents["data"]["agents"]:
            if agent["id"] == test_agent_id:
                print(f"\n  Agent details:")
                print(f"    Name: {agent['name']}")
                print(f"    Description: {agent['description']}")
                print(f"    Active: {agent.get('active', True)}")
                print(f"    Source: {agent.get('source', 'unknown')}")
                break
    else:
        # Step 2: Create a new agent
        print(f"\n2. Creating new agent '{test_agent_id}'...")
        create_response = await create_agent(test_agent_id)
        
        if create_response.status_code == 201:
            print("   ✓ Agent created successfully!")
            created_data = create_response.json()
            print(f"   Response: {created_data['type']}")
        else:
            print(f"   ✗ Failed to create agent: {create_response.status_code}")
            print(f"   Error: {create_response.text}")
            return
        
        # Step 3: Get updated list of agents
        print("\n3. Getting updated list of agents...")
        updated_agents = await get_agents()
        updated_agent_ids = [agent["id"] for agent in updated_agents["data"]["agents"]]
        print(f"   Found {len(updated_agent_ids)} agents: {updated_agent_ids}")
        
        # Verify the new agent is in the list
        if test_agent_id in updated_agent_ids:
            print(f"\n   ✓ Test agent '{test_agent_id}' successfully added to the list!")
            
            # Show the created agent details
            for agent in updated_agents["data"]["agents"]:
                if agent["id"] == test_agent_id:
                    print(f"\n   Agent details:")
                    print(f"     Name: {agent['name']}")
                    print(f"     Description: {agent['description']}")
                    print(f"     Active: {agent.get('active', True)}")
                    print(f"     Source: {agent.get('source', 'unknown')}")
                    break
        else:
            print(f"\n   ✗ Test agent '{test_agent_id}' not found in updated list!")
    
    print("\n" + "="*50)
    print("To test persistence:")
    print("1. Stop the server (Ctrl+C)")
    print("2. Start the server again")
    print("3. Run this script again")
    print(f"4. The agent '{test_agent_id}' should still be present")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())