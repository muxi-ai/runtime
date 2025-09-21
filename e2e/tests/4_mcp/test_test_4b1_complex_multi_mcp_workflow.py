#!/usr/bin/env python3
"""Test 4B1: Complex Multi-MCP Workflow - Linear → System → GitHub → Linear."""

import asyncio
import time

from .base_mcp_test import BaseMCPTest


class Test4B1ComplexMultiMCPWorkflow(BaseMCPTest):
    """Test complex multi-MCP orchestration workflow."""

    async def run_test(self):
        """Run the test for complex multi-MCP workflow."""
        test_name = "Test 4B1: Complex Multi-MCP Workflow"
        description = "Orchestrate Linear → System → GitHub → Linear workflow"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Setup formation with multi MCP servers
            await self.setup_mcp_formation("multi")
            checks.append("Formation loaded with multiple MCP servers")

            # Test complex multi-MCP workflow
            print("\n  1. Testing complex multi-MCP workflow...")
            print("     Flow: Create issue → Get CPU stats → Create gist → Update issue")

            # Complex workflow request
            workflow_request = (
                "Create a Linear issue asking to document system CPU usage. "
                "The issue should request creating a GitHub gist with the current CPU stats. "
                "After creating the gist, update the Linear issue as completed with a link to the gist."
            )

            print(f"\n  Sending workflow request: {workflow_request}")
            transcript.append(("User", workflow_request))

            # Execute workflow through overlord
            response = await self.overlord.chat(
                workflow_request, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            print(f"  Workflow Response: {response_text}")
            transcript.append(("System", response_text))

            # Verify workflow components were executed
            response_lower = response_text.lower()

            # Check for issue creation
            issue_mentioned = any(
                term in response_lower for term in ["issue", "linear", "created", "ticket"]
            )
            if issue_mentioned:
                checks.append("Linear issue creation mentioned")

            # Check for CPU stats
            cpu_mentioned = any(
                term in response_lower for term in ["cpu", "processor", "usage", "stats"]
            )
            if cpu_mentioned:
                checks.append("CPU statistics mentioned")

            # Check for gist creation
            gist_mentioned = any(term in response_lower for term in ["gist", "github", "created"])
            if gist_mentioned:
                checks.append("GitHub gist creation mentioned")

            # Check for completion/update
            completion_mentioned = any(
                term in response_lower for term in ["completed", "updated", "done", "finished"]
            )
            if completion_mentioned:
                checks.append("Issue completion/update mentioned")

            workflow_success = (
                issue_mentioned and cpu_mentioned and gist_mentioned and completion_mentioned
            )
            print(f"  ✓ Complex multi-MCP workflow: {'PASSED' if workflow_success else 'PARTIAL'}")

            # Test 2: Workflow error handling
            print("\n  2. Testing workflow error handling...")
            error_request = (
                "Create a Linear issue to document disk usage, "
                "then try to create a gist in a non-existent repository"
            )

            print(f"  Sending error test request: {error_request}")
            transcript.append(("User", error_request))

            error_response = await self.overlord.chat(
                error_request, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(error_response, "__aiter__"):
                error_response_text = ""
                async for chunk in error_response:
                    error_response_text += chunk
            else:
                error_response_text = (
                    error_response.content
                    if hasattr(error_response, "content")
                    else str(error_response)
                )

            print(f"  Error Handling Response: {error_response_text}")
            transcript.append(("System", error_response_text))

            # Check error handling
            error_response_lower = error_response_text.lower()
            error_handled = (
                any(term in error_response_lower for term in ["error", "failed", "unable", "issue"])
                or "linear" in error_response_lower
            )

            if error_handled:
                checks.append("Workflow error handling successful")

            error_test_success = error_handled
            print(f"  ✓ Workflow error handling: {'PASSED' if error_test_success else 'FAILED'}")

            # Test 3: Tool availability check
            print("\n  3. Testing MCP tool availability...")
            tools_request = (
                "What MCP tools do you have available for Linear, GitHub, and system monitoring?"
            )
            transcript.append(("User", tools_request))

            tools_response = await self.overlord.chat(
                tools_request, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(tools_response, "__aiter__"):
                tools_response_text = ""
                async for chunk in tools_response:
                    tools_response_text += chunk
            else:
                tools_response_text = (
                    tools_response.content
                    if hasattr(tools_response, "content")
                    else str(tools_response)
                )

            print(f"  Tools Response: {tools_response_text}")
            transcript.append(("System", tools_response_text))

            # Check tool availability mentions
            tools_response_lower = tools_response_text.lower()
            linear_tools = "linear" in tools_response_lower
            github_tools = "github" in tools_response_lower
            system_tools = any(
                term in tools_response_lower for term in ["system", "cpu", "memory", "monitoring"]
            )

            if linear_tools:
                checks.append("Linear tools available")
            if github_tools:
                checks.append("GitHub tools available")
            if system_tools:
                checks.append("System monitoring tools available")

            tools_success = linear_tools or github_tools or system_tools
            print(f"  ✓ MCP tool availability: {'PASSED' if tools_success else 'FAILED'}")

            # Overall success - at least partial workflow success and error handling
            success = workflow_success and error_test_success and tools_success

            if success:
                checks.append("Complex multi-MCP workflow operations successful")
            else:
                checks.append("Some multi-MCP workflow operations failed")

        except Exception as e:
            print(f"  ❌ Test failed with error: {e}")
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed with error: {e}")

        finally:
            # Cleanup
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, success, checks, transcript, duration)

        return success


async def main():
    """Main test execution."""
    test = Test4B1ComplexMultiMCPWorkflow()
    success = await test.run_test()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
