#!/usr/bin/env python3
"""
Test A2A flow using overlord.chat() exactly as requested
"""

import asyncio
import sys
from pathlib import Path
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    """Test A2A flow with overlord.chat()"""

    print("\n" + "="*60)
    print("A2A OVERLORD.CHAT() TEST")
    print("="*60)

    # Suppress most logs
    import logging
    logging.getLogger().setLevel(logging.WARNING)

    # Load formation
    print("\n1. Loading formation...")
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-multi-agent-segregated" / "formation.yaml"))  # noqa: E501
    overlord = await formation.start_overlord()
    print("   ✓ Formation loaded")

    # The exact call requested
    print("\n2. Calling overlord.chat() WITHOUT agent_name (auto-routing):")
    print('   agent_name=None')
    print('   message="create a linear issue with system usage info like cpu, memory, etc"')
    print("\n" + "-"*60)

    # Make the call WITHOUT specifying agent_name
    response = await overlord.chat(
        message="create a linear issue with system usage info like cpu, memory, etc",
        agent_name=None,  # Let overlord auto-route
        user_id="test_user",
        session_id="test_session",
        stream=False,  # Try with stream=False like the working test
        use_async=False
    )

    # Collect and display response
    # Handle response like the working test
    if hasattr(response, 'content'):
        result = response.content
    else:
        result = ""
        async for chunk in response:
            result += chunk
            # print(chunk, end="", flush=True)

    print("\n" + "="*60)
    print("\nOverlord Response (auto-routed):")
    print(result)  # ACTUALLY PRINT THE RESULT!
    print("\n" + "="*60)

    # Track the behavior
    print("\n3. Behavior tracking:")

    # Check if system info was obtained
    if "cpu" in result.lower() or "%" in result:
        print("   ✓ System info obtained")
    else:
        print("   ✗ System info not found in response")

    # Check if delegation occurred
    if "project manager" in result.lower() or "project-manager" in result.lower():
        print("   ✓ Delegation to Project Manager mentioned")
    else:
        print("   ✗ No mention of Project Manager delegation")

    # Check if Linear issue was created
    if "linear" in result.lower() and ("created" in result.lower() or "issue" in result.lower()):
        print("   ✓ Linear issue creation mentioned")
    else:
        print("   ✗ Linear issue creation not confirmed")

    # Check for errors
    if "error" in result.lower() or "failed" in result.lower():
        print("   ⚠ Possible error in response")

    # Cleanup
    print("\n4. Cleaning up...")
    await formation.stop_overlord()
    formation.shutdown()

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("Check your Linear dashboard for the new issue!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
