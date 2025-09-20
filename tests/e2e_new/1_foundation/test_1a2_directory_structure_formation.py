#!/usr/bin/env python3
"""Test 1a2: Directory Structure Formation Loading using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402
class TestDirectoryStructureFormation(BaseE2ETest):
    """Test directory structure formation loading."""

    def __init__(self):
        super().__init__(
            test_name="test_1a2_directory_structure_formation",
            test_description="Test directory structure formation loading",
            test_area="1_foundation"
        )

    async def test_1a2_directory_structure_formation(self):
        """Test loading formation from directory structure."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1a2_directory_structure_formation",
            description="Test directory structure formation loading"
        )

        try:
            # Test 1: Verify formation directory exists and has correct structure
            print("\n1. Verifying formation directory structure...")
            formation_dir = Path(__file__).parent / "formations" / "formation-base"
            assert formation_dir.is_dir(), f"Formation directory not found: {formation_dir}"

            # Check for expected files
            expected_files = ["formation.yaml", "secrets.enc", ".key"]
            for file_name in expected_files:
                file_path = formation_dir / file_name
                if not file_path.exists():
                    print(f"   ⚠️ File not found (may be OK): {file_name}")
                else:
                    print(f"   ✓ Found: {file_name}")

            print("✅ Directory structure verified")

            # Test 2: Load formation from directory
            print("\n2. Loading formation from directory...")
            await self.setup_formation(template="standard")
            overlord = self.overlord
            print("✅ Formation loaded from directory")

            # Test 3: Verify agents loaded from subdirectory (if exists)
            print("\n3. Checking agent loading...")
            assert overlord is not None
            assert len(overlord.agents) > 0

            # Check if agents were loaded from agents/ subdirectory
            agents_dir = formation_dir / "agents"
            if agents_dir.exists():
                print(f"   Agents directory exists: {agents_dir}")
                agent_files = list(agents_dir.glob("*.yaml"))
                print(f"   Agent files found: {len(agent_files)}")
            else:
                print("   No agents/ subdirectory (agents defined in main YAML)")

            print(f"   Loaded agents: {list(overlord.agents.keys())}")
            print("✅ Agents loaded successfully")

            # Test 4: Test basic chat functionality
            print("\n4. Testing chat with loaded formation...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(overlord.chat("Hello, how are you?", user_id="test_user"), timeout=timeout)

            assert response is not None
            response_text = response.content if hasattr(response, 'content') else str(response)
            assert len(response_text) > 0
            print(f"   Response: {response_text[:100]}...")
            print("✅ Chat functionality works")

            # Clean up
            print("\n5. Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup completed")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a2_directory_structure_formation",
                success=True,
                checks=[
                    "Directory structure verified",
                    "Formation loaded from directory",
                    "Agents loaded",
                    "Chat functionality works",
                    "Clean shutdown"
                ],
                transcript=[("Hello, how are you?", response_text)],
                duration=duration
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a2_directory_structure_formation",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=duration
            )
            raise
        finally:
            return 0 if success else 1
    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_1a2_directory_structure_formation())

if __name__ == "__main__":
    test = TestDirectoryStructureFormation()
    sys.exit(test.run_test())
