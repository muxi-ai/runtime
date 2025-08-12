#!/usr/bin/env python3
"""
Test A2A flow using overlord.chat() exactly as requested
"""

import asyncio
import sys
from pathlib import Path
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    """Test A2A flow with overlord.chat()"""

    print("\n" + "=" * 60)
    print("A2A OVERLORD.CHAT() TEST")
    print("=" * 60)

    # Suppress most logs
    import logging

    logging.getLogger().setLevel(logging.WARNING)

    # Load formation
    print("\n1. Loading formation...")
    formation = Formation()
    await formation.load(
        str(
            Path(__file__).parent
            / "formations"
            / "formation-multi-agent-segregated"
            / "formation.yaml"
        )
    )  # noqa: E501
    overlord = await formation.start_overlord()
    print("   ✓ Formation loaded")

    # The exact call requested
    print("\n2. Calling overlord.chat() WITHOUT agent_name (auto-routing):")
    print("   agent_name=None")
    print('   message="create a linear issue with system usage info like cpu, memory, etc"')
    print("\n" + "-" * 60)

    # Add debugging to capture raw agent responses and A2A communication
    print("\n   [DEBUG] Adding response interceptors...")

    # Store all responses
    # all_responses = []
    raw_agent_response = None

    # Store original methods
    original_apply_persona = overlord._apply_persona

    async def debug_apply_persona(raw_response, user_message):
        nonlocal raw_agent_response
        raw_agent_response = raw_response
        print("\n   [DEBUG] Raw agent response before persona:")
        print(f"   Type: {type(raw_response)}")
        print(f"   Content length: {len(raw_response) if raw_response else 0}")
        print(f"   First 1000 chars: {raw_response[:1000] if raw_response else 'None'}")

        # Try to parse and extract meaningful data
        if raw_response:
            # Check for Linear issue mentions
            if "linear" in raw_response.lower():
                print("   ✓ Contains 'linear' keyword")
            if "issue" in raw_response.lower():
                print("   ✓ Contains 'issue' keyword")
            if "created" in raw_response.lower():
                print("   ✓ Contains 'created' keyword")
            if "http" in raw_response or "linear.app" in raw_response:
                print("   ✓ Contains URL")
                # Extract URLs
                import re

                urls = re.findall(r'https?://[^\s\'"]+', raw_response)
                if urls:
                    print(f"   URLs found: {urls}")

        print("   ---")
        return await original_apply_persona(raw_response, user_message)

    # Also intercept agent communication if possible
    if hasattr(overlord, "_process_agent_response"):
        original_process_agent = overlord._process_agent_response

        async def debug_process_agent(agent_id, response):
            print(f"\n   [DEBUG] Agent {agent_id} raw response:")
            print(f"   Response type: {type(response)}")
            if hasattr(response, "__dict__"):
                print(f"   Response attrs: {response.__dict__.keys()}")
            print(f"   Response: {str(response)[:500]}")
            return await original_process_agent(agent_id, response)

        overlord._process_agent_response = debug_process_agent

    # Monkey-patch for this test
    overlord._apply_persona = debug_apply_persona

    # Make the call WITHOUT specifying agent_name
    response = await overlord.chat(
        message="create a linear issue with system usage info like cpu, memory, etc",
        # message="create a linear issue with system usage info like cpu, memory, etc. reply with the information as a json object. do not include any other text in the response.",  # noqa: E501
        agent_name=None,  # Let overlord auto-route
        user_id="test_user",
        session_id="test_session",
        stream=False,  # Try with stream=False like the working test
        use_async=False,
    )

    # Restore original
    overlord._apply_persona = original_apply_persona

    # Collect and display response
    # Handle response based on type
    if isinstance(response, str):
        # String response - use directly
        result = response
    elif hasattr(response, "content"):
        # MuxiResponse object - extract content
        result = response.content
    elif hasattr(response, "__aiter__"):
        # Async generator - collect chunks
        result = ""
        async for chunk in response:
            result += chunk
    else:
        # Fallback for other types
        result = str(response)

    print("\n" + "=" * 60)
    print("\nOverlord Response (auto-routed):")
    print(result)  # ACTUALLY PRINT THE RESULT!
    print("\n" + "=" * 60)

    # Also show the raw agent response if captured
    if raw_agent_response:
        print("\n[DEBUG] Analysis of raw agent response:")
        print(f"   Length: {len(raw_agent_response)} chars")

        # Try to detect JSON in the response
        try:
            # Look for JSON blocks
            if "{" in raw_agent_response and "}" in raw_agent_response:
                start = raw_agent_response.find("{")
                end = raw_agent_response.rfind("}") + 1
                potential_json = raw_agent_response[start:end]
                parsed = json.loads(potential_json)
                print(f"   Found JSON data: {json.dumps(parsed, indent=2)}")
        except Exception:
            pass

        # Check for Linear issue mentions
        if "linear" in raw_agent_response.lower():
            print("   ✓ Linear issue mentioned in raw response")
        else:
            print("   ✗ No Linear issue mention in raw response")

        # Check for URLs
        if "http" in raw_agent_response.lower() or "linear.app" in raw_agent_response.lower():
            print("   ✓ URL found in raw response")
        else:
            print("   ✗ No URL in raw response")

    print("\n" + "=" * 60)

    # Track the behavior
    print("\n3. Behavior tracking:")

    # Check if system info was obtained
    if "cpu" in result.lower() or "%" in result:
        print("   ✓ System info obtained")
    else:
        print("   ✗ System info not found in response")

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

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("Check your Linear dashboard for the new issue!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
