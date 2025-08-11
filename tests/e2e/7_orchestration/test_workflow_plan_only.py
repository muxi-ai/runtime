#!/usr/bin/env python3
"""
Test workflow plan generation only - auto-declines to inspect the plan without execution.
This test helps debug the TaskDecomposer's dynamic capability discovery.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def main():
    """Test workflow plan generation with auto-decline."""

    print("🔍 MUXI Runtime - Workflow Plan Generation Test")
    print("="*60)
    print("\n📋 Configuration:")
    print("   • complexity_threshold: 4.0 (triggers workflow)")
    print("   • plan_approval_threshold: 5 (requires approval)")
    print("   • Auto-decline: YES (plan testing only)")

    formation_path = Path(__file__).parent / "formations" / "formation-multi-agent-approval"

    try:
        print("\n1️⃣ Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✅ Formation loaded successfully")
        
        # Debug: Check what agents are actually loaded
        print(f"\n🔍 DEBUG: Found {len(overlord.agents)} agents:")
        for agent_id, agent in overlord.agents.items():
            specialties = getattr(agent, 'specialties', []) or getattr(agent, 'specialization', [])
            agent_name = getattr(agent, 'name', agent_id)
            print(f"   - {agent_name} ({agent_id}): specialties = {specialties}")
        
        # Debug: Check MCP service
        if hasattr(overlord, 'mcp_service') and overlord.mcp_service:
            servers = getattr(overlord.mcp_service, 'servers', {})
            print(f"\n🔍 DEBUG: Found {len(servers)} MCP servers:")
            for server_id in servers.keys():
                print(f"   - {server_id}")
        else:
            print("\n🔍 DEBUG: No MCP service found")
            
        # Debug: Check TaskDecomposer setup
        if hasattr(overlord, 'task_decomposer'):
            decomposer = overlord.task_decomposer
            print(f"\n🔍 DEBUG: TaskDecomposer:")
            print(f"   - Has LLM: {decomposer.llm is not None}")
            print(f"   - Agent registry size: {len(decomposer.agent_registry) if decomposer.agent_registry else 0}")
            print(f"   - Has MCP service: {decomposer.mcp_service is not None}")
        else:
            print("\n🔍 DEBUG: No TaskDecomposer found")

        # Topic for the issue
        topic = "AI-Powered Healthcare Diagnostics in 2025"

        print(f"\n2️⃣ Sending complex request about: {topic}")
        print("   (This will trigger workflow analysis and approval request)")

        start_time = datetime.now()

        # Complex request WITHOUT agent_name to trigger workflow
        response = await overlord.chat(
            message=f"Research {topic}, analyze current trends, key players, and recent breakthroughs. Then create a comprehensive Linear issue with detailed findings, implementation timeline, potential challenges, and future predictions. Include specific examples and actionable insights.",
            user_id="demo_user",
            session_id="plan_test",
            stream=False
        )

        # Get response
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = ""
            async for chunk in response:
                content += chunk

        # Check if approval requested
        if "proposed approach" in content.lower() or "does this approach work" in content.lower():
            print("\n3️⃣ ✅ Workflow approval requested!")
            print("\n" + "="*60)
            print("📋 PROPOSED WORKFLOW PLAN:")
            print("="*60)
            print(content)
            print("="*60)

            print("\n4️⃣ 🚫 Auto-declining plan (test mode)")
            
            # Send decline
            decline_response = await overlord.chat(
                message="No, cancel this workflow",
                user_id="demo_user",
                session_id="plan_test",
                stream=False
            )
            
            decline_content = decline_response.content if hasattr(decline_response, 'content') else str(decline_response)
            print(f"\n✅ Decline processed: {decline_content[:100]}...")

        else:
            print("\n⚠️  No approval requested - request may not have been complex enough")
            print("\nResponse received:")
            print("-"*60)
            print(content)
            print("-"*60)

        total_time = (datetime.now() - start_time).total_seconds()

        print(f"\n{'='*60}")
        print("📊 SUMMARY:")
        print(f"{'='*60}")
        print(f"⏱️  Total time: {total_time:.1f}s")
        print(f"🔍 Plan generation: Tested")
        print(f"🚫 Workflow execution: Skipped (auto-declined)")
        print(f"\n💡 Check the logs above for TaskDecomposer debug info!")

        # Cleanup
        print("\n5️⃣ Cleaning up...")
        try:
            await formation.stop_overlord()
            formation.stop()
            print("   ✅ Formation stopped")
        except Exception as e:
            print(f"   ⚠️  Cleanup warning: {e}")

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n🤖 AUTOMATED TEST - Auto-declines workflow for plan inspection")
    asyncio.run(main())