#!/usr/bin/env python3
"""
Test Linear issue creation WITH workflow approval flow.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    """Test workflow with approval."""

    print("🚀 MUXI Runtime - Testing Workflow Approval Flow")
    print("="*60)

    formation_path = Path(__file__).parent / "formations" / "formation-multi-agent"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n✅ Formation loaded")
        print("📋 Sending complex request to trigger workflow...")

        # Complex request WITHOUT agent_name to trigger workflow
        response = await overlord.chat(
            message="Research the latest developments in quantum computing, analyze the key players and breakthroughs, then create a comprehensive Linear issue with findings, timeline, and future predictions",  # noqa: E501
            user_id="test_user",
            session_id="workflow_test",
            # NO agent_name - let workflow decide
            stream=False
        )

        # Get response
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = ""
            async for chunk in response:
                content += chunk

        print("\n📋 Response:")
        print("-"*60)
        print(content)
        print("-"*60)

        # Check if approval was requested
        if "proposed approach" in content.lower() or "does this approach work" in content.lower():
            print("\n✅ Workflow approval requested!")
            print("📝 The system asked for approval before proceeding")

            # Simulate approval
            print("\n🔄 Approving the workflow...")

            response2 = await overlord.chat(
                message="Yes, please proceed with the plan",
                user_id="test_user",
                session_id="workflow_test",
                stream=False
            )

            if hasattr(response2, 'content'):
                content2 = response2.content
            else:
                content2 = ""
                async for chunk in response2:
                    content2 += chunk

            print("\n📋 After Approval:")
            print("-"*60)
            print(content2[:500] + "..." if len(content2) > 500 else content2)
            print("-"*60)

        else:
            print("\n⚠️  No approval requested - complexity might be below threshold")

        await formation.stop_overlord()
        formation.shutdown()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
