#!/usr/bin/env python3
"""Test MCP Workflow with specific requirements"""

import sys
sys.path.insert(0, '.')
import asyncio
from datetime import datetime

from src.muxi.runtime.formation import Formation

async def test_mcp_workflow_custom():
    """Test MCP workflow with specific steps"""
    print("\n=== Test MCP Workflow - Custom ===")
    print("Steps:")
    print("1. Create Linear issue: 'please check cpu usage'")
    print("2. Get CPU usage using MCP")
    print("3. Create GitHub repo 'cpu-monitor' (already exists)")
    print("4. Update Linear issue with GitHub link")
    
    formation = Formation()
    await formation.load("test-formations/formation-mcp")
    overlord = await formation.start_overlord()
    
    print("\n✓ Formation loaded and overlord started")
    
    # Execute the workflow
    prompt = """Please execute the following workflow:
1. Create a Linear issue with the title "please check cpu usage" and a description asking to monitor and document the current CPU usage
2. Get the current CPU usage from the system using the MCP system tools
3. Create a GitHub repository named "cpu-monitor" and add a file with the CPU usage data (note: this repo might already exist)
4. Update the Linear issue with a link to the GitHub repository

Please handle any errors gracefully if the GitHub repository already exists."""
    
    print("\nExecuting workflow...")
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
    
    # Check for key elements
    response_lower = response.lower()
    
    print("\n=== Verification ===")
    
    # Check Linear issue creation
    if "linear" in response_lower and any(term in response_lower for term in ["created", "issue", "mx-"]):
        print("✅ Linear issue created")
    else:
        print("❌ Linear issue creation unclear")
    
    # Check CPU usage retrieval
    if "cpu" in response_lower and any(term in response_lower for term in ["usage", "percent", "%"]):
        print("✅ CPU usage retrieved")
    else:
        print("❌ CPU usage retrieval unclear")
    
    # Check GitHub handling
    if "github" in response_lower and "cpu-monitor" in response_lower:
        if "already exists" in response_lower or "existing" in response_lower:
            print("✅ Handled existing repository gracefully")
        else:
            print("✅ GitHub repository/file created or updated")
    else:
        print("❌ GitHub operation unclear")
    
    # Check Linear update
    if any(term in response_lower for term in ["updated", "update", "completed", "added link"]):
        print("✅ Linear issue updated")
    else:
        print("❌ Linear issue update unclear")
    
    # Look for the Linear issue ID
    import re
    issue_matches = re.findall(r'MX-\d+', response)
    if issue_matches:
        print(f"\nLinear Issue ID: {issue_matches[0]}")
    
    # Look for GitHub URLs
    github_urls = re.findall(r'https://github\.com/[^\s\)]+', response)
    if github_urls:
        print(f"\nGitHub URLs found:")
        for url in github_urls:
            print(f"  - {url}")
    
    # Proper shutdown
    formation.shutdown()

if __name__ == "__main__":
    asyncio.run(test_mcp_workflow_custom())