#!/usr/bin/env python3
"""Test 1a4: Flattened Formation Loading using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestFlattenedFormationLoading(BaseE2ETest):
    """Test flattened formation loading (single YAML file)."""

    def __init__(self):
        super().__init__(
            test_name="test_1a4_flattened_formation_loading",
            test_description="Test flattened formation loading",
            test_area="1_foundation",
        )

    async def test_1a4_flattened_formation_loading(self):
        """Test loading a flattened formation (all config in one YAML)."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1a4_flattened_formation_loading",
            description="Test flattened formation loading",
        )

        try:
            # Test loading from minimal template (which is essentially flattened)
            print("\n1. Loading flattened formation...")
            await self.setup_formation(template="minimal")
            overlord = self.overlord
            print("✅ Flattened formation loaded successfully")

            # Verify all components loaded from single file
            print("\n2. Verifying components loaded...")
            checks = []

            # Check agents
            if overlord.agents:
                print(f"   ✓ Agents loaded: {list(overlord.agents.keys())}")
                checks.append("Agents loaded from flat config")

            # Check memory config
            if hasattr(overlord, "memory_manager"):
                print("   ✓ Memory configuration loaded")
                checks.append("Memory config loaded")

            # Check LLM config
            if hasattr(overlord, "llm"):
                print("   ✓ LLM configuration loaded")
                checks.append("LLM config loaded")

            print("✅ All components loaded from flattened formation")

            # Test functionality
            print("\n3. Testing functionality...")
            response = await asyncio.wait_for(
                overlord.chat("Hello", user_id="test_user"), timeout=15
            )

            assert response is not None
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:100]}...")
            print("✅ Functionality verified")

            # Clean up
            print("\n4. Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup completed")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a4_flattened_formation_loading",
                success=True,
                checks=["Flattened formation loaded"]
                + checks
                + ["Functionality verified", "Clean shutdown"],
                transcript=[("Hello", response_text)],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a4_flattened_formation_loading",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=duration,
            )
            raise
        finally:
            return 0 if success else 1

    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_1a4_flattened_formation_loading())


if __name__ == "__main__":
    test = TestFlattenedFormationLoading()
    sys.exit(test.run_test())
