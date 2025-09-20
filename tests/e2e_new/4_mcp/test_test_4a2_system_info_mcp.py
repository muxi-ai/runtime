#!/usr/bin/env python3
"""Test 4A2: System information retrieval via MCP system tools."""

import asyncio
import time

from base_mcp_test import BaseMCPTest
class Test4A2SystemInfoMCP(BaseMCPTest):
    """Test system information retrieval using MCP system tools."""

    async def run_test(self):
        """Run the test for system information MCP operations."""
        test_name = "Test 4A2: System Info MCP"
        description = "Validate CPU, memory, and system stats retrieval via MCP"

        self.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Setup formation with MCP enabled
            await self.setup_mcp_formation("weather")  # Default formation with system info
            checks.append("Formation loaded with MCP enabled")

            # Test 1: CPU and memory usage retrieval
            print("\n  1. Testing CPU and memory usage retrieval...")
            request1 = "What is the current CPU usage and available memory on this system?"
            transcript.append(("User", request1))

            response1 = await self.overlord.chat(
                request1,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Handle response
            if hasattr(response1, "__aiter__"):
                response1_text = ""
                async for chunk in response1:
                    response1_text += chunk
            else:
                response1_text = response1.content if hasattr(response1, "content") else str(response1)

            print(f"  Response: {response1_text}")
            transcript.append(("System", response1_text))

            # Verify response contains system stats
            response1_lower = response1_text.lower()
            cpu_mentioned = any(term in response1_lower for term in ["cpu", "processor"])
            memory_mentioned = any(term in response1_lower for term in ["memory", "ram", "gb", "mb"])
            usage_mentioned = any(char in response1_text for char in ["%", "percent"]) or "usage" in response1_lower

            if cpu_mentioned:
                checks.append("CPU information retrieved")
            if memory_mentioned:
                checks.append("Memory information retrieved")
            if usage_mentioned:
                checks.append("Usage statistics included")

            test1_success = cpu_mentioned and memory_mentioned
            print(f"  ✓ CPU and memory stats test: {'PASSED' if test1_success else 'FAILED'}")

            # Test 2: Detailed system information
            print("\n  2. Testing detailed system information...")
            request2 = "Give me detailed system information including CPU cores, total memory, and disk usage"
            transcript.append(("User", request2))

            response2 = await self.overlord.chat(
                request2,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Handle response
            if hasattr(response2, "__aiter__"):
                response2_text = ""
                async for chunk in response2:
                    response2_text += chunk
            else:
                response2_text = response2.content if hasattr(response2, "content") else str(response2)

            print(f"  Response: {response2_text}")
            transcript.append(("System", response2_text))

            response2_lower = response2_text.lower()
            cores_mentioned = any(term in response2_lower for term in ["core", "thread", "processor"])
            detailed_response = len(response2_text) > 100

            if cores_mentioned:
                checks.append("CPU cores/threads information retrieved")
            if detailed_response:
                checks.append("Detailed response provided")

            test2_success = cores_mentioned and detailed_response
            print(f"  ✓ Detailed system info test: {'PASSED' if test2_success else 'FAILED'}")

            # Test 3: Specific metric queries
            print("\n  3. Testing specific metric queries...")
            request3 = "What percentage of memory is currently being used?"
            transcript.append(("User", request3))

            response3 = await self.overlord.chat(
                request3,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Handle response
            if hasattr(response3, "__aiter__"):
                response3_text = ""
                async for chunk in response3:
                    response3_text += chunk
            else:
                response3_text = response3.content if hasattr(response3, "content") else str(response3)

            print(f"  Response: {response3_text}")
            transcript.append(("System", response3_text))

            response3_lower = response3_text.lower()
            percentage_mentioned = any(char in response3_text for char in ["%", "percent"]) or any(
                term in response3_lower for term in ["memory", "ram"]
            )

            if percentage_mentioned:
                checks.append("Memory percentage retrieved")

            test3_success = percentage_mentioned
            print(f"  ✓ Specific metric query test: {'PASSED' if test3_success else 'FAILED'}")

            # Test 4: System uptime information
            print("\n  4. Testing system uptime information...")
            request4 = "How long has this system been running (uptime)?"
            transcript.append(("User", request4))

            response4 = await self.overlord.chat(
                request4,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Handle response
            if hasattr(response4, "__aiter__"):
                response4_text = ""
                async for chunk in response4:
                    response4_text += chunk
            else:
                response4_text = response4.content if hasattr(response4, "content") else str(response4)

            print(f"  Response: {response4_text}")
            transcript.append(("System", response4_text))

            response4_lower = response4_text.lower()
            uptime_mentioned = any(
                term in response4_lower
                for term in ["uptime", "running", "hours", "days", "minutes", "boot", "started"]
            )

            if uptime_mentioned:
                checks.append("System uptime information retrieved")

            test4_success = uptime_mentioned
            print(f"  ✓ System uptime query test: {'PASSED' if test4_success else 'FAILED'}")

            # Test 5: Disk space information
            print("\n  5. Testing disk space information...")
            request5 = "Show me the available disk space on the main drive"
            transcript.append(("User", request5))

            response5 = await self.overlord.chat(
                request5,
                user_id="test_user",
                use_async=False,
                stream=False
            )

            # Handle response
            if hasattr(response5, "__aiter__"):
                response5_text = ""
                async for chunk in response5:
                    response5_text += chunk
            else:
                response5_text = response5.content if hasattr(response5, "content") else str(response5)

            print(f"  Response: {response5_text}")
            transcript.append(("System", response5_text))

            response5_lower = response5_text.lower()
            disk_mentioned = any(
                term in response5_lower
                for term in ["disk", "space", "storage", "gb", "tb", "available", "free"]
            )

            if disk_mentioned:
                checks.append("Disk space information retrieved")

            test5_success = disk_mentioned
            print(f"  ✓ Disk space query test: {'PASSED' if test5_success else 'FAILED'}")

            # Overall success
            success = test1_success and test2_success and test3_success and test4_success and test5_success

            if success:
                checks.append("All system info MCP operations successful")
            else:
                checks.append("Some system info operations failed")

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
    test = Test4A2SystemInfoMCP()
    success = await test.run_test()
    return success
if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
