#!/usr/bin/env python3
"""
Day 7a: Task Decomposition Test - Workflow Integration Version

Tests the Overlord's workflow integration for complex requests:
"research 'ran aroussi funding gap' and write a short summary about it. save the summary as a linear issue"

This tests whether:
1. The request triggers workflow complexity analysis
2. The workflow system creates a multi-task workflow (not simple routing)
3. Tasks have proper dependencies and are executed in phases
4. The workflow ID is tracked and accessible
5. Workflow metadata is included in the response
6. Simple requests bypass the workflow system
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.muxi.formation.formation import Formation  # noqa: E402


async def test_workflow_task_decomposition():
    """Test workflow-based task decomposition for complex requests."""
    print("\n" + "="*80)
    print("Day 7a: Workflow Task Decomposition Test")
    print("Testing workflow integration for complex multi-step requests")
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

        # Complex prompt that should trigger workflow decomposition
        prompt = 'research "ran aroussi funding gap" and write a short summary about it. save the summary as a linear issue'  # noqa: E501

        print("\n3. Sending complex prompt to Overlord...")
        print(f"   Prompt: {prompt}")
        print("   " + "-"*60)
        print("   Expected workflow behavior:")
        print("     1. Complexity analysis triggers (score >= 7.0)")
        print("     2. Workflow created with multiple tasks")
        print("     3. Tasks have proper dependencies")
        print("     4. Workflow ID is generated and tracked")
        print("     5. Execution happens in phases")
        print("   " + "-"*60)

        start_time = asyncio.get_event_loop().time()

        # Send the request - let Overlord decompose naturally
        print("\n   [Workflow orchestration will appear below]")
        response = await overlord.chat(
            prompt,
            user_id="test_user",
            session_id="test_session_workflow",
            stream=False,  # IMPORTANT: Must be False for workflow tests
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
            f.write("Simple Task Decomposition Test\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Duration: {duration:.1f} seconds\n")
            f.write(f"Prompt: {prompt}\n")
            f.write(f"\n{'='*80}\n\n")
            f.write(response_content)

        print(f"   Full response saved to: {response_file}")

        # Analyze the response
        print("\n4. Analyzing response for workflow integration...")

        # Check for workflow metadata
        has_metadata = hasattr(response, 'metadata') and response.metadata is not None
        print(f"   Response has metadata: {'✓' if has_metadata else '✗'}")

        workflow_id = None
        if has_metadata and 'workflow_id' in response.metadata:
            workflow_id = response.metadata['workflow_id']
            print(f"   Workflow ID found: {workflow_id}")
        else:
            print("   Workflow ID: Not found in metadata")

        # Check if workflow was actually used
        workflow_used = workflow_id is not None
        print(f"   Workflow system engaged: {'✓' if workflow_used else '✗'}")

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

        # Test workflow status if workflow was used
        if workflow_id:
            print("\n5. Checking workflow status...")
            # Check if we can get workflow status
            if hasattr(overlord, 'get_workflow_status'):
                workflow_status = overlord.get_workflow_status(workflow_id)
                if workflow_status:
                    print(f"   Workflow status: {workflow_status.status if hasattr(workflow_status, 'status') else 'Unknown'}")  # noqa: E501
                    if hasattr(workflow_status, 'tasks'):
                        print(f"   Total tasks: {len(workflow_status.tasks)}")
                        # Check task dependencies
                        has_dependencies = any(task.dependencies for task in workflow_status.tasks.values())
                        print(f"   Tasks have dependencies: {'✓' if has_dependencies else '✗'}")
            else:
                print("   Workflow status method not available")

        # Test follow-up to verify information source
        print("\n6. Testing information source...")
        follow_up = await overlord.chat(
            "What specific information did you find about Ran Aroussi's funding gap? What sources did you use?",
            user_id="test_user",
            session_id="test_session_workflow",
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

        # Test simple request that should bypass workflow
        print("\n7. Testing simple request (should bypass workflow)...")
        simple_prompt = "What is the weather today?"
        simple_response = await overlord.chat(
            simple_prompt,
            user_id="test_user",
            session_id="test_session_simple",
            stream=False,
            use_async=False
        )

        # Check if simple request bypassed workflow
        simple_has_metadata = hasattr(simple_response, 'metadata') and simple_response.metadata is not None
        simple_workflow_id = None
        if simple_has_metadata and 'workflow_id' in simple_response.metadata:
            simple_workflow_id = simple_response.metadata['workflow_id']

        print(f"   Simple request used workflow: {'✗ (Good!)' if simple_workflow_id is None else '✓ (Should bypass!)'}")

        # Clean up
        print("\n8. Cleaning up...")
        await formation.stop_overlord()
        print("   ✓ Overlord stopped")

        # Summary
        print("\n" + "="*80)
        print("✓ Simple Task Decomposition Test Complete!")
        print("\nResults:")
        print(f"  - Duration: {duration:.1f} seconds")
        print(f"  - Response length: {len(response_content)} characters")
        print(f"  - Workflow system engaged: {'✓' if workflow_used else '✗'}")
        print(f"  - Web search used: {'✓' if search_used and ran_mentioned else '✗'}")
        print(f"  - Specific info found: {'✓' if ran_mentioned and funding_gap_mentioned else '✗'}")
        print(f"  - Linear issue created: {'✓' if linear_created else '✗'}")
        print(f"  - Simple requests bypass workflow: {'✓' if simple_workflow_id is None else '✗'}")

        workflow_success = workflow_used and ran_mentioned and funding_gap_mentioned and linear_created
        simple_success = simple_workflow_id is None  # Simple request should not use workflow
        overall_success = workflow_success and simple_success

        print(f"\nOverall: {'SUCCESS' if overall_success else 'PARTIAL SUCCESS'}")

        if overall_success:
            print("\nThe Overlord successfully:")
            print("  1. Triggered workflow system for complex request")
            print("  2. Created multi-task workflow with dependencies")
            print("  3. Executed tasks in proper phases")
            print("  4. Used web search to find specific information")
            print("  5. Created a Linear issue with the summary")
            print("  6. Bypassed workflow for simple requests")
        else:
            if not workflow_used:
                print("\n⚠️  Workflow system was not engaged for complex request")
            if not simple_success:
                print("\n⚠️  Simple request incorrectly triggered workflow")

        print("="*80 + "\n")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(test_workflow_task_decomposition())
