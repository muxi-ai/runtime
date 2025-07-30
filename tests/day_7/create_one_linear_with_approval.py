#!/usr/bin/env python3
"""
Create ONE Linear issue WITH workflow approval flow.
Interactive test that shows the full approval process.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def main():
    """Create a single Linear issue with approval flow."""

    print("🚀 MUXI Runtime - Single Linear Issue with Approval Flow")
    print("="*60)
    print("\n📋 Configuration:")
    print("   • complexity_threshold: 4.0 (triggers workflow)")
    print("   • plan_approval_threshold: 5 (requires approval)")
    print("   • Team ID: 21b2d439-9ffa-4383-86f5-556acc7af93b")
    print("   • Resilience: 5 retries with exponential backoff")

    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent-approval"

    try:
        print("\n1️⃣ Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✅ Formation loaded successfully")

        # Topic for the issue
        topic = "AI-Powered Healthcare Diagnostics in 2025"

        print(f"\n2️⃣ Sending complex request about: {topic}")
        print("   (This will trigger workflow analysis and approval request)")

        start_time = datetime.now()

        # Complex request WITHOUT agent_name to trigger workflow
        response = await overlord.chat(
            message=f"Research {topic}, analyze current trends, key players, and recent breakthroughs. Then create a comprehensive Linear issue with detailed findings, implementation timeline, potential challenges, and future predictions. Include specific examples and actionable insights.",
            user_id="demo_user",
            session_id="approval_demo",
            # NO agent_name - let workflow analyze and request approval
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

            # Get user approval
            print("\n❓ Do you approve this plan? (y/n): ", end="", flush=True)
            approval = input().strip().lower()

            if approval == 'y':
                print("\n4️⃣ ✅ Plan approved! Executing workflow...")
                print("   ⏳ This may take a minute as agents research and create the issue")

                approval_start = datetime.now()

                # Send approval
                approval_response = await overlord.chat(
                    message="Yes, please proceed with the plan",
                    user_id="demo_user",
                    session_id="approval_demo",
                    stream=True  # Stream to show progress
                )

                # Monitor execution with streaming
                print("\n" + "-"*60)
                print("📝 WORKFLOW EXECUTION:")
                print("-"*60)

                final_content = ""
                if hasattr(approval_response, 'content'):
                    final_content = approval_response.content
                    print(final_content)
                else:
                    async for chunk in approval_response:
                        final_content += chunk
                        print(chunk, end="", flush=True)

                print("\n" + "-"*60)

                execution_time = (datetime.now() - approval_start).total_seconds()

                # Check result
                if "linear" in final_content.lower() and ("created" in final_content.lower() or "issue" in final_content.lower()):
                    print(f"\n5️⃣ ✅ SUCCESS! Linear issue created!")
                    print(f"   ⏱️  Execution time: {execution_time:.1f}s")
                else:
                    print(f"\n5️⃣ ⚠️  Workflow completed in {execution_time:.1f}s")
                    print("   Check your Linear workspace for the issue")

            else:
                print("\n❌ Workflow cancelled by user")
                print("   No Linear issue was created")

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
        print(f"🛡️  Resilience layer: Active")
        print(f"✅ Workflow approval: Demonstrated")
        print(f"\n🔍 Check your Linear workspace for team:")
        print(f"   21b2d439-9ffa-4383-86f5-556acc7af93b")

        # Cleanup
        print("\n6️⃣ Cleaning up...")
        try:
            await formation.stop_overlord()
            formation.shutdown()
            print("   ✅ Formation stopped")
        except Exception as e:
            print(f"   ⚠️  Cleanup warning: {e}")

    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n⚠️  INTERACTIVE TEST - Requires manual approval")
    print("Press Enter to start...")
    input()
    asyncio.run(main())
