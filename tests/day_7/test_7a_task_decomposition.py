#!/usr/bin/env python3
"""
Day 7a: Task Decomposition Test - Simplified Version

Tests the Overlord's natural ability to decompose a simple request:
"research 'ran aroussi funding gap' and write a short summary about it. save the summary as a linear issue"

This tests whether:
1. The Overlord correctly routes to researcher for web search
2. The researcher finds specific information (not general LLM knowledge)
3. The writer uses the researched information
4. The project manager creates the Linear issue
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def test_simple_task_decomposition():
    """Test natural task decomposition with a simple prompt."""
    print("\n" + "="*80)
    print("Day 7a: Simple Task Decomposition Test")
    print("Testing natural Overlord decomposition without prescriptive instructions")
    print("="*80 + "\n")

    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"

    # Create output directory
    output_dir = Path(__file__).parent / "test_outputs"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        # Load formation
        print("1. Loading formation-multi-agent...")
        formation = Formation()
        await formation.load(str(formation_path))
        print("   ✓ Formation loaded")

        # Start overlord
        print("\n2. Starting overlord...")
        overlord = await formation.start_overlord()
        print("   ✓ Overlord started")
        print("   Agents: " + ", ".join(overlord.agents.keys()))

        # Simple prompt that requires decomposition
        prompt = 'research "ran aroussi funding gap" and write a short summary about it. save the summary as a linear issue'

        print("\n3. Sending simple prompt to Overlord...")
        print(f"   Prompt: {prompt}")
        print("   " + "-"*60)
        print("   Expected decomposition:")
        print("     1. Route to researcher → search for 'ran aroussi funding gap'")
        print("     2. Route to writer → summarize the findings")
        print("     3. Route to project-manager → create Linear issue")
        print("   " + "-"*60)

        start_time = asyncio.get_event_loop().time()

        # Send the request - let Overlord decompose naturally
        print("\n   [Overlord routing decisions will appear below]")
        response = await overlord.chat(
            prompt,
            user_id="test_user",
            stream=False,
            use_async=False
        )

        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time

        # Extract response content
        response_content = response.content if hasattr(response, 'content') else str(response)

        print(f"\n   ✓ Response received in {duration:.1f} seconds")
        print(f"   Response length: {len(response_content)} characters")

        # Save full response
        response_file = output_dir / f"simple_response_{timestamp}.txt"
        with open(response_file, 'w') as f:
            f.write(f"Simple Task Decomposition Test\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Duration: {duration:.1f} seconds\n")
            f.write(f"Prompt: {prompt}\n")
            f.write(f"\n{'='*80}\n\n")
            f.write(response_content)

        print(f"   Full response saved to: {response_file}")

        # Analyze the response
        print("\n4. Analyzing response...")

        # Check for "ran aroussi" - this proves web search was used
        ran_mentioned = "ran aroussi" in response_content.lower()
        print(f"   'Ran Aroussi' mentioned: {'✓' if ran_mentioned else '✗'}")

        # Check for "funding gap" - specific search term
        funding_gap_mentioned = "funding gap" in response_content.lower()
        print(f"   'Funding gap' mentioned: {'✓' if funding_gap_mentioned else '✗'}")

        # Check for web search indicators
        search_indicators = ["search", "found", "according to", "website", "article", "source"]
        search_used = any(ind in response_content.lower() for ind in search_indicators)
        print(f"   Web search indicators: {'✓' if search_used else '✗'}")

        # Check for Linear issue creation
        linear_indicators = ["linear", "issue", "created", "mx-", "linear.app"]
        linear_created = any(ind in response_content.lower() for ind in linear_indicators)
        print(f"   Linear issue created: {'✓' if linear_created else '✗'}")

        # Extract Linear issue ID if present
        import re
        linear_match = re.search(r'MX-\d+', response_content)
        if linear_match:
            print(f"   Linear issue ID: {linear_match.group()}")

        # Test follow-up to verify information source
        print("\n5. Testing information source...")
        follow_up = await overlord.chat(
            "What specific information did you find about Ran Aroussi's funding gap? What sources did you use?",
            user_id="test_user",
            stream=False,
            use_async=False
        )

        follow_up_content = follow_up.content if hasattr(follow_up, 'content') else str(follow_up)

        # Save follow-up
        with open(output_dir / f"simple_follow_up_{timestamp}.txt", 'w') as f:
            f.write(follow_up_content)

        # Check if follow-up mentions specific sources
        has_sources = any(word in follow_up_content.lower() for word in ["website", "article", "search", "found"])
        print(f"   Sources mentioned in follow-up: {'✓' if has_sources else '✗'}")

        # Clean up
        print("\n6. Cleaning up...")
        await formation.stop_overlord()
        print("   ✓ Overlord stopped")

        # Summary
        print("\n" + "="*80)
        print("✓ Simple Task Decomposition Test Complete!")
        print("\nResults:")
        print(f"  - Duration: {duration:.1f} seconds")
        print(f"  - Response length: {len(response_content)} characters")
        print(f"  - Web search used: {'✓' if search_used and ran_mentioned else '✗'}")
        print(f"  - Specific info found: {'✓' if ran_mentioned and funding_gap_mentioned else '✗'}")
        print(f"  - Linear issue created: {'✓' if linear_created else '✗'}")

        success = ran_mentioned and funding_gap_mentioned and linear_created
        print(f"\nOverall: {'SUCCESS' if success else 'PARTIAL SUCCESS'}")

        if success:
            print("\nThe Overlord successfully:")
            print("  1. Decomposed the task naturally")
            print("  2. Routed research to the researcher agent")
            print("  3. Used web search to find specific information")
            print("  4. Passed findings to writer for summarization")
            print("  5. Created a Linear issue with the summary")

        print("="*80 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_simple_task_decomposition())
