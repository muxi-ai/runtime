#!/usr/bin/env python3
"""
Demonstrate the workflow approval flow.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def main():
    """Demo approval flow."""
    
    print("🚀 MUXI Runtime - Workflow Approval Flow Demo")
    print("="*60)
    print("\n📋 Configuration:")
    print("   • complexity_threshold: 4.0 (triggers workflow)")
    print("   • plan_approval_threshold: 5 (triggers approval)")
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-approval-test"
    
    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        print("\n✅ Formation loaded")
        print("\n1️⃣ Sending complex request...")
        
        # Complex request to trigger workflow AND approval
        response = await overlord.chat(
            message="Create a comprehensive report on AI trends including research, analysis, and recommendations",
            user_id="demo_user",
            session_id="approval_demo",
            stream=False
        )
        
        # Get response
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = ""
            async for chunk in response:
                content += chunk
        
        print("\n📋 System Response:")
        print("-"*60)
        print(content)
        print("-"*60)
        
        # Check what happened
        if "proposed approach" in content.lower():
            print("\n✅ SUCCESS: Workflow approval was requested!")
            print("   The system is waiting for user confirmation")
            print("\n💡 In the Linear tests, we set plan_approval_threshold: 10")
            print("   This prevented approval prompts during testing")
        else:
            print("\n⚠️  No approval requested")
        
        await formation.stop()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())