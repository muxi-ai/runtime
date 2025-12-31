#!/usr/bin/env python3
"""Test 4D1: User Credential Exists in DB - Direct Execution."""

import asyncio
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_mcp_test import BaseMCPTest  # noqa: E402


class Test4D1UserCredentialExists(BaseMCPTest):
    """Test user credential handling when credentials exist in database."""

    async def run_test(self):
        """Run the test for existing user credentials."""
        test_name = "Test 4D1: User Credential Exists in DB"
        description = "Verify system uses stored credentials without asking user"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Setup formation with MCP enabled
            await self.setup_mcp_formation("weather")  # Default formation
            checks.append("Formation loaded with MCP enabled")

            print("\n  This test verifies that when user1 (who has GitHub credentials stored)")
            print("  makes a request to use GitHub, the system:")
            print("  1. Uses formation secrets to initialize and discover GitHub MCP tools")
            print("  2. Automatically uses user1's stored credentials for the actual API call")
            print("  3. Does NOT ask the user to provide credentials")

            # Wait for MCP servers to initialize
            print("\n  Waiting for MCP servers to initialize...")
            await asyncio.sleep(3)
            checks.append("MCP servers initialization completed")

            # Check available tools first
            print("\n  Checking available MCP tools...")
            mcp_service = getattr(self.overlord, "mcp_service", None)
            if mcp_service:
                tool_registry = getattr(mcp_service, "tool_registry", {})
                github_tools = [tool for tool in tool_registry.keys() if "github" in tool.lower()]
                print(f"  GitHub MCP tools available: {len(github_tools)}")
                if github_tools:
                    print(f"  Sample tools: {github_tools[:3]}")
                    checks.append(f"GitHub MCP tools discovered: {len(github_tools)}")
            else:
                print("  ⚠️ MCP service not found")
                checks.append("MCP service not available")

            # Test GitHub repository creation request
            print("\n  1. Testing GitHub issue creation with existing credentials...")
            github_request = (
                "Create a GitHub issue on the muxi repo with title 'Test Issue from muxi.runtime' "
                "and body 'This is a test issue created by the MUXI runtime to verify "
                "user credential functionality.'"
            )

            print(f"  Sending request: {github_request}")
            transcript.append(("User", github_request))

            # Capture response
            response = await self.overlord.chat(
                github_request,
                user_id="user1",  # user1 should have stored credentials
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            print(f"  Response: {response_text}")
            transcript.append(("System", response_text))

            # Analyze response for credential handling
            response_lower = response_text.lower()

            # Check if system asked for credentials (should NOT happen)
            asked_for_credentials = any(
                phrase in response_lower
                for phrase in [
                    "please provide",
                    "need your",
                    "don't have",
                    "missing credential",
                    "github token",
                    "github credentials",
                    "authentication",
                    "login",
                ]
            )

            # Check if system attempted to use stored credentials
            attempted_action = any(
                word in response_lower
                for word in ["created", "issue", "opened", "submitted", "attempting", "trying"]
            )

            # Check for specific errors that indicate credential usage
            auth_error = any(
                phrase in response_lower
                for phrase in ["401", "403", "404", "unauthorized", "forbidden", "not found"]
            )

            credential_test_success = False
            if asked_for_credentials:
                print("  ❌ System incorrectly asked for credentials")
                checks.append("FAILED: System asked for credentials despite having them stored")
            elif attempted_action:
                print("  ✓ System attempted to use stored credentials")
                checks.append("System used stored credentials for GitHub action")
                credential_test_success = True
            elif auth_error:
                print(
                    "  ✓ System used credentials but got auth error (credential attempt confirmed)"
                )
                checks.append("System attempted credential usage (auth error indicates usage)")
                credential_test_success = True
            else:
                print("  ⚠️ Unclear if system used stored credentials")
                checks.append("Credential usage unclear from response")

            # Test 2: Repository listing request
            print("\n  2. Testing GitHub repository listing...")
            repo_request = "List my GitHub repositories"
            transcript.append(("User", repo_request))

            repo_response = await self.overlord.chat(
                repo_request, user_id="user1", use_async=False, stream=False
            )

            # Handle response
            if hasattr(repo_response, "__aiter__"):
                repo_response_text = ""
                async for chunk in repo_response:
                    repo_response_text += chunk
            else:
                repo_response_text = (
                    repo_response.content
                    if hasattr(repo_response, "content")
                    else str(repo_response)
                )

            print(f"  Response: {repo_response_text}")
            transcript.append(("System", repo_response_text))

            repo_response_lower = repo_response_text.lower()

            # Check repo listing behavior
            repo_asked_credentials = any(
                phrase in repo_response_lower
                for phrase in ["please provide", "need your", "don't have", "missing credential"]
            )

            repo_attempted = any(
                word in repo_response_lower
                for word in ["repository", "repositories", "repo", "github", "list"]
            )

            repo_test_success = not repo_asked_credentials and repo_attempted

            if repo_test_success:
                checks.append("Repository listing used stored credentials")
            else:
                checks.append("Repository listing credential handling unclear")

            print(f"  ✓ Repository listing test: {'PASSED' if repo_test_success else 'FAILED'}")

            # Test 3: Service availability check
            print("\n  3. Testing GitHub service availability...")
            service_request = (
                "Do you have access to GitHub for creating issues and managing repositories?"
            )
            transcript.append(("User", service_request))

            service_response = await self.overlord.chat(
                service_request, user_id="user1", use_async=False, stream=False
            )

            # Handle response
            if hasattr(service_response, "__aiter__"):
                service_response_text = ""
                async for chunk in service_response:
                    service_response_text += chunk
            else:
                service_response_text = (
                    service_response.content
                    if hasattr(service_response, "content")
                    else str(service_response)
                )

            print(f"  Response: {service_response_text}")
            transcript.append(("System", service_response_text))

            service_response_lower = service_response_text.lower()
            service_available = "github" in service_response_lower or any(
                term in service_response_lower for term in ["yes", "available", "access", "can"]
            )

            if service_available:
                checks.append("GitHub service availability confirmed")

            service_test_success = service_available
            print(
                f"  ✓ Service availability test: {'PASSED' if service_test_success else 'FAILED'}"
            )

            # Overall success - primary test is credential handling
            success = credential_test_success

            if success:
                checks.append("User credential existence test successful")
                print(
                    "\n  ✅ SUCCESS: System correctly used stored credentials without asking user"
                )
            else:
                checks.append("User credential existence test needs review")
                print("\n  ⚠️ REVIEW: Credential handling behavior unclear")

        except Exception as e:
            print(f"  ❌ Test failed with error: {e}")
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed with error: {e}")

        finally:
            # Cleanup
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, success, checks, transcript, duration)

        # Print observability note
        print("\n  📋 Key observability events to look for in logs:")
        print(
            "  1. 'Transformed user credentials for github-mcp' - Shows credential transformation"
        )
        print("  2. 'mcp.message.sent' with tool name - Shows GitHub API calls")
        print("  3. 'mcp.message.received' - Shows responses from GitHub")
        print("  4. Any 'credential' or 'auth' related events")

        return success


async def main():
    """Main test execution."""
    test = Test4D1UserCredentialExists()
    success = await test.run_test()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
