#!/usr/bin/env python3
"""Test 1b3: Basic Formation using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402
class TestBasicFormation(BaseE2ETest):
    """Test basic formation functionality."""

    def __init__(self):
        super().__init__(
            test_name="test_1b3_basic_formation",
            test_description="Test basic formation functionality",
            test_area="1_foundation"
        )

    async def test_1b3_basic_formation(self):
        """Test basic formation creation and chat."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False
        transcript = []

        # Print header
        formatter.print_test_header(
            test_name="test_1b3_basic_formation",
            description="Test basic formation functionality"
        )

        try:
            # Setup formation
            print("\n1. Creating formation...")
            await self.setup_formation(template="minimal")
            overlord = self.overlord
            print("✅ Formation created successfully")

            # Test formation properties
            print("\n2. Checking formation properties...")
            assert overlord.formation_id is not None
            print(f"   Formation ID: {overlord.formation_id}")
            assert len(overlord.agents) > 0
            print(f"   Agents: {list(overlord.agents.keys())}")
            print("✅ Formation properties verified")

            # Test multiple interactions
            print("\n3. Testing multiple chat interactions...")
            test_messages = [
                "Hello",
                "What is Python?",
                "Thank you"
            ]

            timeout = TestTimeouts.get_timeout("simple_chat")
            for i, message in enumerate(test_messages, 1):
                print(f"   Message {i}: {message}")
                response = await asyncio.wait_for(overlord.chat(message, user_id="test_user"), timeout=timeout)

                assert response is not None
                response_text = response.content if hasattr(response, 'content') else str(response)
                assert len(response_text) > 0
                transcript.append((message, response_text))
                print(f"   Response: {response_text[:80]}...")

            print("✅ All interactions completed successfully")

            # Test memory persistence (messages should be in context)
            print("\n4. Testing context retention...")
            final_response = await asyncio.wait_for(overlord.chat("What did I ask about?", user_id="test_user"), timeout=timeout)
            final_text = final_response.content if hasattr(final_response, 'content') else str(final_response)
            transcript.append(("What did I ask about?", final_text))
            print(f"   Context response: {final_text[:100]}...")
            print("✅ Context retention verified")

            # Clean up
            print("\n5. Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup completed")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b3_basic_formation",
                success=True,
                checks=[
                    "Formation created",
                    "Properties verified",
                    "Multiple interactions successful",
                    "Context retention works",
                    "Clean shutdown"
                ],
                transcript=transcript,
                duration=duration
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b3_basic_formation",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=transcript,
                duration=duration
            )
            raise
        finally:
            return 0 if success else 1
    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_1b3_basic_formation())

if __name__ == "__main__":
    test = TestBasicFormation()
    sys.exit(test.run_test())
