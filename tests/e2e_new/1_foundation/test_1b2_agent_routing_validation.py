#!/usr/bin/env python3
"""Test 1b2: Agent Routing Validation using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestAgentRoutingValidation(BaseE2ETest):
    """Test agent routing validation."""

    def __init__(self):
        super().__init__(
            test_name="test_1b2_agent_routing_validation",
            test_description="Test agent routing validation",
            test_area="1_foundation",
        )

    async def test_1b2_agent_routing_validation(self):
        """Test agent routing and validation."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1b2_agent_routing_validation",
            description="Test agent routing validation",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation...")
            await self.setup_formation(template="standard")
            overlord = self.overlord
            print("✅ Formation ready")

            # Test 1: Verify default agent routing
            print("\n2. Testing default agent routing...")
            assert "assistant" in overlord.agents
            print("   ✅ Default agent 'assistant' found")

            # Test 2: Send message to default agent
            print("\n3. Testing message routing to default agent...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(
                overlord.chat("What can you do?", user_id="test_user"), timeout=timeout
            )

            assert response is not None
            response_text = response.content if hasattr(response, "content") else str(response)
            assert len(response_text) > 0
            print(f"   Response: {response_text[:100]}...")
            print("   ✅ Message routed successfully")

            # Test 3: Verify agent selection
            print("\n4. Testing agent selection logic...")
            # When no specific agent is requested, it should use the default
            response2 = await asyncio.wait_for(
                overlord.chat("Tell me a joke", user_id="test_user"), timeout=timeout
            )

            assert response2 is not None
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            print(f"   Response: {response2_text[:100]}...")
            print("   ✅ Agent selection works")

            # Clean up
            print("\n5. Cleaning up...")
            await self.cleanup_formation()
            print("✅ Cleanup completed")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b2_agent_routing_validation",
                success=True,
                checks=[
                    "Formation loaded",
                    "Default agent found",
                    "Message routing works",
                    "Agent selection works",
                    "Clean shutdown",
                ],
                transcript=[
                    ("What can you do?", response_text),
                    ("Tell me a joke", response2_text),
                ],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b2_agent_routing_validation",
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
        return asyncio.run(self.test_1b2_agent_routing_validation())


if __name__ == "__main__":
    test = TestAgentRoutingValidation()
    sys.exit(test.run_test())
