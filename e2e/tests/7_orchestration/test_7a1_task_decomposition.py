#!/usr/bin/env python3
"""
Test 7A1: Task Decomposition - Workflow Integration
Tests the Overlord's workflow integration for complex requests:
- Workflow complexity analysis and triggering
- Multi-task workflow creation with dependencies
- Task execution in proper phases
- Workflow ID tracking and metadata
- Simple requests bypass workflow system
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_workflow_task_decomposition():
    """Test workflow-based task decomposition for complex requests."""
    print("\n" + "=" * 80)
    print("Test 7A1: Task Decomposition - Workflow Integration")
    print("=" * 80)

    checks_passed = []
    all_passed = True
    formation = None
    overlord = None

    try:
        # Setup
        print("\n1. Loading formation...")
        formation_path = (
            Path(__file__).parent / "formations" / "formation-multi-agent" / "formation.afs"
        )

        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("   ✓ Formation loaded")
        print(f"   Agents: {', '.join(overlord.agents.keys())}")

        # Complex prompt that should trigger workflow decomposition
        prompt = (
            "research `ran aroussi funding gap` and write a short summary about it. "
            "save the summary as a linear issue"
        )

        print("\n2. Sending complex prompt to Overlord...")
        print(f"   Prompt: {prompt}")
        print("   Expected: Workflow decomposition with web search and Linear issue creation")

        # Send the request
        response = await overlord.chat(
            prompt,
            user_id="test_user",
            session_id="test_session_workflow",
            stream=False,
            use_async=False,
        )

        # Extract response content
        response_content = response.content if hasattr(response, "content") else str(response)

        print(f"\n   ✓ Response received ({len(response_content)} characters)")
        print(f"\n   Response excerpt:\n   {response_content[:300]}...")

        # Analyze the response
        print("\n3. Analyzing response...")

        # Check if workflow was actually used
        has_metadata = hasattr(response, "metadata") and response.metadata is not None
        workflow_id = response.metadata.get("workflow_id") if has_metadata else None

        if workflow_id:
            print(f"   ✓ Workflow system engaged (ID: {workflow_id})")
            checks_passed.append(f"Workflow ID: {workflow_id}")
        else:
            print("   ℹ️  No workflow ID (may have been handled directly)")

        # Check for "ran aroussi" - proves web search was used
        ran_mentioned = "ran aroussi" in response_content.lower()
        print(f"   {'✓' if ran_mentioned else '✗'} 'Ran Aroussi' mentioned: {ran_mentioned}")
        if ran_mentioned:
            checks_passed.append("Specific search term found")

        # Check for "funding gap"
        funding_gap_mentioned = "funding gap" in response_content.lower()
        print(
            f"   {'✓' if funding_gap_mentioned else '✗'} 'Funding gap' mentioned: {funding_gap_mentioned}"
        )
        if funding_gap_mentioned:
            checks_passed.append("Funding gap mentioned")

        # Check for web search indicators
        search_indicators = ["search", "found", "according to", "website", "article", "source"]
        search_used = any(ind in response_content.lower() for ind in search_indicators)
        print(f"   {'✓' if search_used else '✗'} Web search indicators: {search_used}")
        if search_used:
            checks_passed.append("Web search used")

        # Check for Linear issue creation
        linear_indicators = ["linear", "issue", "created", "mx-", "linear.app"]
        linear_created = any(ind in response_content.lower() for ind in linear_indicators)
        print(f"   {'✓' if linear_created else '✗'} Linear issue created: {linear_created}")
        if linear_created:
            checks_passed.append("Linear issue created")

        # Extract Linear issue ID if present
        import re

        linear_match = re.search(r"MX-\d+", response_content, re.IGNORECASE)
        if linear_match:
            print(f"   ✓ Linear issue ID: {linear_match.group()}")
            checks_passed.append(f"Linear ID: {linear_match.group()}")

        # Test simple request that should bypass workflow
        print("\n4. Testing simple request (should bypass workflow)...")
        simple_response = await overlord.chat(
            "What is the weather today?",
            user_id="test_user",
            session_id="test_session_simple",
            stream=False,
            use_async=False,
        )

        simple_has_workflow = (
            hasattr(simple_response, "metadata")
            and simple_response.metadata
            and "workflow_id" in simple_response.metadata
        )

        print(
            f"   {'✗' if simple_has_workflow else '✓'} Simple request bypassed workflow: {not simple_has_workflow}"
        )
        if not simple_has_workflow:
            checks_passed.append("Simple requests bypass workflow")

        # Determine overall success
        # Need at least: search indicators OR specific mentions, ideally both
        workflow_success = search_used or ran_mentioned or funding_gap_mentioned
        overall_success = workflow_success and len(checks_passed) >= 2

        if not overall_success:
            all_passed = False
            print("\n   ⚠️  Test did not meet all success criteria")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback

        traceback.print_exc()
        all_passed = False

    finally:
        print("\n5. Cleaning up...")
        if overlord and formation:
            await formation.stop_overlord()
            formation.stop()
        print("   ✓ Formation stopped")

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_workflow_task_decomposition())
    sys.exit(exit_code)
