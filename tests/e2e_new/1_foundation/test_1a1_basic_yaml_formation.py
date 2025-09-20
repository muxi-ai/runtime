#!/usr/bin/env python3
"""Test 1a1: Basic YAML Formation Loading using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402
class TestBasicYamlFormation(BaseE2ETest):
    """Test basic YAML formation loading."""

    def __init__(self):
        super().__init__(
            test_name="test_1a1_basic_yaml_formation",
            test_description="Test basic YAML formation loading",
            test_area="1_foundation"
        )

    async def test_1a1_basic_yaml_formation(self):
        """Test basic YAML formation loading and configuration verification."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1a1_basic_yaml_formation",
            description="Test basic YAML formation loading"
        )

        try:
            # Test 1: Load formation and verify structure
            print("\n1. Loading formation from YAML...")
            formation = await self.setup_formation(template="standard")
            overlord = self.overlord
            print("✅ Formation loaded successfully")

            # Test 2: Verify formation ID
            print("\n2. Verifying formation configuration...")
            assert overlord.formation_id is not None
            print(f"   Formation ID: {overlord.formation_id}")

            # Test 3: Verify configuration structure
            assert hasattr(formation, 'config')
            config_keys = list(formation.config.keys()) if formation.config else []
            print(f"   Configuration keys: {config_keys}")

            # Verify key configuration sections exist
            assert "llm" in formation.config or hasattr(formation, 'llm_config')
            assert "memory" in formation.config or hasattr(formation, 'memory_config')
            print("✅ Configuration structure verified")

            # Test 4: Verify agents loaded
            print("\n3. Verifying agents loaded...")
            assert len(overlord.agents) > 0
            print(f"   Agents loaded: {list(overlord.agents.keys())}")
            print("✅ Agents verified")

            # Test 5: Test basic functionality
            print("\n4. Testing basic chat functionality...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(overlord.chat("Hello", user_id="test_user"), timeout=timeout)

            assert response is not None
            response_text = response.content if hasattr(response, 'content') else str(response)
            assert len(response_text) > 0
            print(f"   Response: {response_text[:100]}...")
            print("✅ Basic functionality verified")

            # Clean up
            print("\n5. Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup completed")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a1_basic_yaml_formation",
                success=True,
                checks=[
                    "Formation loaded",
                    "Configuration verified",
                    "Agents loaded",
                    "Basic functionality works",
                    "Clean shutdown"
                ],
                transcript=[("Hello", response_text)],
                duration=duration
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a1_basic_yaml_formation",
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
        return asyncio.run(self.test_1a1_basic_yaml_formation())
if __name__ == "__main__":
    test = TestBasicYamlFormation()
    sys.exit(test.run_test())
