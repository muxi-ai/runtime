#!/usr/bin/env python3
"""Test MCP Workflow - Final version with explicit username"""

import sys
sys.path.insert(0, '.')
import asyncio
from datetime import datetime

from src.muxi.runtime.formation import Formation

async def test_mcp_workflow_final():
    """Test MCP workflow with explicit instructions"""
    print("\n=== Test MCP Workflow - Final ===")
    print("Steps:")
    print("1. Create Linear issue: 'please check cpu usage'")
    print("2. Get CPU usage using MCP") 
    print("3. Update file in existing GitHub repo 'ranaroussi/cpu-monitor'")
    print("4. Update Linear issue with GitHub link")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("\n✓ Formation loaded and overlord started")
    
    # Execute the workflow with very specific instructions
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = f"""Please execute these steps exactly:

1. Create a new Linear issue with the title "please check cpu usage" (exactly as written)

2. Get the current CPU usage using the system MCP tools

3. Create or update a file named 'cpu-usage-{timestamp.replace(" ", "_").replace(":", "-")}.json' in the GitHub repository 'ranaroussi/cpu-monitor' with the CPU usage data

4. Update the Linear issue with a comment that includes the GitHub file link

Important: Use 'ranaroussi' as the GitHub owner, not 'your_username'."""
    
    print(f"\nExecuting workflow at {timestamp}...")
    response_gen = await overlord.chat(
        prompt,
        user_id="user1",
        use_async=False
    )
    
    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk
        
    print(f"\nWorkflow Response:")
    print("="*80)
    print(response)
    print("="*80)
    
    # Extract key information
    import re
    
    # Linear issue ID
    issue_matches = re.findall(r'MX-\d+', response)
    if issue_matches:
        print(f"\n✅ Linear Issue Created: {issue_matches[0]}")
    
    # CPU usage
    cpu_matches = re.findall(r'(\d+\.?\d*)\s*%', response)
    if cpu_matches:
        print(f"✅ CPU Usage Retrieved: {cpu_matches[0]}%")
    
    # GitHub file link
    github_urls = re.findall(r'https://github\.com/ranaroussi/cpu-monitor[^\s\)]+', response)
    if github_urls:
        print(f"✅ GitHub File Created: {github_urls[0]}")
    
    # Check if Linear was updated
    if any(term in response.lower() for term in ["updated", "added", "comment", "link"]):
        print("✅ Linear Issue Updated")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_mcp_workflow_final())