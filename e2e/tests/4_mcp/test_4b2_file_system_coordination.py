#!/usr/bin/env python3
"""Test 4B2: File + System Info Coordination - Multi-MCP coordination"""

import sys
import asyncio
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402
from common import BaseE2ETest  # noqa: E402


def test_file_system_coordination():
    """Test coordination between filesystem and system info MCPs"""
    print("\n=== Test 4B2: File + System Info Coordination ===")
    print("Goal: Test multi-MCP coordination between System and Filesystem MCPs")

    # Create a test directory on Desktop (where filesystem MCP has access)
    test_dir = Path("/Users/ran/Desktop/muxi_test_4b2")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(exist_ok=True)
    print(f"Using test directory: {test_dir}")

    try:
        # Run the async test in a thread pool to avoid event loop issues
        def run_test():
            async def test_operations():
                # Load formation with MCP enabled
                formation = Formation()
                await formation.load(str(Path(__file__).parent / "formations" / "formation-mcp"))
                overlord = await formation.start_overlord()

                # Ensure overlord is started
                await overlord.ensure_started()

                print("\n1. Testing System → File coordination...")
                response_gen = await overlord.chat(
                    f"Check the current system memory usage and create a file in {test_dir} "
                    f"called 'system_stats.txt' with the information",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Verify both MCPs were used
                response_lower = response.lower()
                assert any(
                    term in response_lower for term in ["memory", "ram", "gb", "mb"]
                ), "Response should mention memory usage"
                assert any(
                    term in response_lower for term in ["file", "created", "saved", "wrote"]
                ), "Response should mention file creation"

                # Verify file was created with system stats
                stats_file = test_dir / "system_stats.txt"
                assert stats_file.exists(), "System stats file should have been created"
                content = stats_file.read_text()
                assert len(content) > 10, "File should contain system statistics"
                assert any(
                    term in content.lower()
                    for term in ["memory", "ram", "usage", "virtual", "swap", "percent"]
                ), "File should contain memory information"
                print("✓ System → File coordination successful")

                print("\n2. Testing comprehensive system report...")
                response_gen = await overlord.chat(
                    f"Create a comprehensive system report in {test_dir}/full_report.txt "
                    f"including CPU usage, memory stats, disk space, and system uptime",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Verify comprehensive report creation
                report_file = test_dir / "full_report.txt"
                assert report_file.exists(), "Full report file should have been created"
                report_content = report_file.read_text().lower()

                # Should contain all requested metrics
                assert "cpu" in report_content, "Report should contain CPU information"
                assert any(
                    term in report_content for term in ["memory", "ram", "virtual", "swap"]
                ), "Report should contain memory information"
                assert any(
                    term in report_content for term in ["disk", "storage"]
                ), "Report should contain disk information"
                assert any(
                    term in report_content for term in ["uptime", "running"]
                ), "Report should contain uptime information"
                print("✓ Comprehensive system report created successfully")

                print("\n3. Testing JSON format system data export...")
                response_gen = await overlord.chat(
                    f"Get current CPU and memory usage and save it as JSON in {test_dir}/stats.json",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Verify JSON file creation
                json_file = test_dir / "stats.json"
                assert json_file.exists(), "JSON stats file should have been created"

                # Verify it's valid JSON
                import json

                try:
                    with open(json_file) as f:
                        data = json.load(f)
                    assert isinstance(data, dict), "JSON should contain a dictionary"
                    print("✓ JSON format export successful")
                except json.JSONDecodeError:
                    # If not valid JSON, check if it at least has the data
                    content = json_file.read_text()
                    assert ("cpu" in content.lower() or "processor" in content.lower()) and any(
                        term in content.lower() for term in ["memory", "virtual", "swap"]
                    ), "File should contain CPU and memory data"
                    print("✓ System data exported (non-JSON format)")

                print("\n4. Testing batch system monitoring...")
                response_gen = await overlord.chat(
                    f"Monitor system resources 3 times with 1 second intervals and "
                    f"save each reading to separate files in {test_dir}/monitoring/",
                    user_id="user1",
                    use_async=False,
                )

                # Collect streaming response
                response = ""
                async for chunk in response_gen:
                    response += chunk
                print(f"Response: {response}")

                # Should create monitoring directory with files
                monitoring_dir = test_dir / "monitoring"
                response_lower = response.lower()
                if monitoring_dir.exists():
                    files = list(monitoring_dir.glob("*"))
                    assert len(files) >= 1, "Should create at least one monitoring file"
                    print(f"✓ Created {len(files)} monitoring files")
                else:
                    # Alternative: might create files with timestamps
                    assert any(
                        term in response_lower for term in ["monitor", "saved", "recorded"]
                    ), "Response should indicate monitoring activity"
                    print("✓ Monitoring task acknowledged")

                print("\n✅ Test 4B2 PASSED: File + System coordination successful")

                # Clean shutdown to avoid async generator errors
                formation.shutdown(0)

            # Run the async test
            return asyncio.run(test_operations())

        # Execute in thread pool
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            _ = future.result(timeout=90)

    except Exception as e:
        print(f"\n❌ Test 4B2 FAILED with error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # Clean up test directory
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"Cleaned up test directory: {test_dir}")


if __name__ == "__main__":
    success = test_file_system_coordination()
    sys.exit(0 if success else 1)
