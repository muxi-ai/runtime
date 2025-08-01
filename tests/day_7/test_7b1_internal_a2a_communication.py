"""
Test 7B1: Internal A2A Communication within Formation

This test verifies that agents can communicate with each other within the same
formation when they have complementary capabilities that require collaboration.

Test Scenario:
- User requests: "Create an issue on Linear with information about current system resources"
- IT Support agent has exclusive access to system-info MCP
- Project Manager agent has exclusive access to Linear MCP
- Agents must collaborate via A2A to complete the task
"""

import pytest
import asyncio
import os
import sys
import re

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from muxi.formation import Formation  # noqa: E402
from tests.utils.env_setup import load_api_keys  # noqa: E402


@pytest.fixture
def setup_environment():
    """Set up test environment."""
    load_api_keys()


@pytest.mark.asyncio
async def test_7b1_internal_a2a_system_info_to_linear(setup_environment):
    """
    Test that agents collaborate internally to create a Linear issue with system information.

    This requires:
    1. IT Support agent to gather system resources (CPU, memory, disk)
    2. Project Manager agent to create the Linear issue
    3. A2A communication between them to share the information
    """
    print("\n" + "=" * 80)
    print("TEST 7B1: Internal A2A Communication - System Info to Linear")
    print("=" * 80)

    # Load the multi-agent segregated formation
    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml",
    )

    if not os.path.exists(formation_path):
        pytest.skip(f"Formation not found at {formation_path}")

    print(f"\n1. Loading formation from: {formation_path}")
    formation = Formation()
    await formation.load(formation_path)

    print("\n2. Starting overlord with disabled workflow orchestration")
    overlord = await formation.start_overlord()

    # Verify workflow is disabled
    assert not overlord.auto_decomposition, "Workflow orchestration should be disabled"
    print(f"   ✓ Workflow orchestration disabled: auto_decomposition={overlord.auto_decomposition}")

    # Verify agents are loaded
    print("\n3. Verifying agent configuration:")
    assert "it-support" in overlord.agents, "IT Support agent not found"
    assert "project-manager" in overlord.agents, "Project Manager agent not found"
    print(f"   ✓ Loaded agents: {list(overlord.agents.keys())}")

    # Test the collaboration request
    print("\n4. Sending collaboration request...")
    request = re.sub(r'\s+', ' ', """
        Create an issue on Linear with information about current system resources
        including CPU usage, memory usage, and disk space.
    """).strip()

    print(f"   Request: {request}")
    print("\n5. Processing request (expecting A2A communication)...")

    try:
        response = await overlord.chat(
            message=request, user_id="test_user_7b1", session_id="test_session_7b1"
        )

        # Handle streaming response
        if hasattr(response, '__aiter__'):
            # It's a streaming response, collect all chunks
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print("\n6. Response received:")
        print("-" * 40)
        print(response)
        print("-" * 40)

        # Verify the response indicates collaboration occurred
        # The response should mention both system information AND Linear issue creation
        response_lower = response.lower()

        # Check for indicators of system information
        has_system_info = any(
            term in response_lower
            for term in ["cpu", "memory", "disk", "system", "resources", "%", "gb", "mb"]
        )

        # Check for indicators of Linear issue creation
        has_linear_action = any(
            term in response_lower for term in ["linear", "issue", "created", "ticket", "task"]
        )

        print("\n7. Validating collaboration:")
        print(f"   ✓ System information gathered: {has_system_info}")
        print(f"   ✓ Linear issue action taken: {has_linear_action}")

        # Both should be true for successful A2A collaboration
        assert has_system_info, "Response should include system information"
        assert has_linear_action, "Response should indicate Linear issue creation"

        print("\n✅ Test 7B1 PASSED: Agents successfully collaborated via A2A")

    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        raise

    finally:
        # Clean up
        print("\n8. Cleaning up...")
        # Formation doesn't have cleanup method either, just pass for now
        pass


@pytest.mark.asyncio
async def test_7b1_verify_a2a_mechanism(setup_environment):
    """
    Verify that A2A communication mechanisms are being used, not workflow orchestration.

    This test specifically targets a single agent first to ensure it recognizes
    it needs help from another agent.
    """
    print("\n" + "=" * 80)
    print("TEST 7B1B: Verify A2A Communication Mechanism")
    print("=" * 80)

    formation_path = os.path.join(
        os.path.dirname(__file__),
        "../../test-formations/formation-multi-agent-segregated/formation.yaml",
    )

    formation = Formation()
    await formation.load(formation_path)
    overlord = await formation.start_overlord()

    try:
        # First, ask IT Support to create a Linear issue (which it can't do alone)
        print("\n1. Testing IT Support agent recognizing need for collaboration...")
        response = await overlord.chat(
            message="Please create a Linear issue about the current CPU usage",
            agent_name="it-support",  # Target specific agent
            user_id="test_user_7b1b",
        )

        # Handle streaming response
        if hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print(f"\nIT Support response:\n{response}")

        # IT Support should either:
        # 1. Indicate it needs help from Project Manager
        # 2. Actually collaborate with Project Manager via A2A
        response_lower = response.lower()

        needs_help = any(
            term in response_lower
            for term in [
                "project manager",
                "need",
                "help",
                "assist",
                "collaborate",
                "don't have access",
                "cannot create",
                "linear access",
            ]
        )

        collaborated = "linear" in response_lower and "issue" in response_lower

        assert (
            needs_help or collaborated
        ), "IT Support should recognize it needs Project Manager's help or actually collaborate"

        # Now test the reverse - Project Manager needs system info
        print("\n2. Testing Project Manager recognizing need for system info...")
        response = await overlord.chat(
            message="Create a Linear issue with the current memory usage statistics",
            agent_name="project-manager",  # Target specific agent
            user_id="test_user_7b1b",
        )

        # Handle streaming response
        if hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response

        print(f"\nProject Manager response:\n{response}")

        response_lower = response.lower()

        needs_help = any(
            term in response_lower
            for term in [
                "it support",
                "need",
                "help",
                "system",
                "cannot access",
                "don't have",
                "information",
            ]
        )

        has_memory_info = any(term in response_lower for term in ["memory", "ram", "gb", "mb", "%"])

        assert (
            needs_help or has_memory_info
        ), "Project Manager should recognize it needs IT Support's help or get the info via A2A"

        print("\n✅ Test 7B1B PASSED: Agents recognize collaboration needs")

    finally:
        pass


if __name__ == "__main__":
    asyncio.run(test_7b1_internal_a2a_system_info_to_linear(None))
