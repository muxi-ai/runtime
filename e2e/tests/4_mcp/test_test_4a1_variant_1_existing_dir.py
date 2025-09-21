#!/usr/bin/env python3
"""Test 4A1: File creation in existing directory via MCP filesystem tools."""

import asyncio
import time
from pathlib import Path

from .base_mcp_test import BaseMCPTest


class Test4A1VariantExistingDir(BaseMCPTest):
    """Test file creation in existing directory using MCP filesystem tools."""

    async def run_test(self):
        """Run the test for file creation in existing directory."""
        test_name = "Test 4A1: File Creation in Existing Directory"
        description = "Create file in existing directory using MCP filesystem tools"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Setup formation with filesystem MCP
            await self.setup_mcp_formation("filesystem")

            # Ensure test directory exists
            test_dir = Path("/Users/ran/Desktop/test_variant_1_existing")
            test_dir.mkdir(exist_ok=True)
            print(f"  ✓ Created test directory: {test_dir}")
            checks.append(f"Created test directory: {test_dir}")

            # Test file creation request
            user_request = f"Create a file called 'success_existing.txt' with content 'Created in existing directory!' in {test_dir}"  # noqa: E501
            print(f"\n  Sending request: {user_request}")
            transcript.append(("User", user_request))

            # Execute through overlord
            response = await self.overlord.chat(
                user_request, user_id="test_user", use_async=False, stream=False
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

            # Check if file was created
            file_path = test_dir / "success_existing.txt"
            if file_path.exists():
                file_content = file_path.read_text()
                print(f"  ✓ File created successfully: {file_path}")
                print(f"  ✓ File content: '{file_content}'")
                checks.extend(
                    [
                        "File created successfully",
                        f"File content matches expected: '{file_content}'",
                    ]
                )

                # Verify content matches
                if "Created in existing directory!" in file_content:
                    success = True
                    checks.append("File content verification passed")
                else:
                    checks.append("File content verification failed")
            else:
                print(f"  ❌ File not created: {file_path}")
                checks.append("File creation failed - file not found")

        except Exception as e:
            print(f"  ❌ Test failed with error: {e}")
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed with error: {e}")

        finally:
            # Cleanup
            await self.cleanup()

            # Clean up test file if it exists
            test_file = Path("/Users/ran/Desktop/test_variant_1_existing/success_existing.txt")
            if test_file.exists():
                test_file.unlink()

        duration = time.time() - start_time
        self.print_test_result(test_name, success, checks, transcript, duration)

        return success


async def main():
    """Main test execution."""
    test = Test4A1VariantExistingDir()
    success = await test.run_test()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
