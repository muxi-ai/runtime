#!/usr/bin/env python3
"""Test 1a6: Simple formation test using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402
from muxi.datatypes.intent import IntentType  # noqa: E402


class TestSimpleFormation(BaseE2ETest):
    """Test simple formation with schema v1.0.0."""

    def __init__(self):
        super().__init__(
            test_name="test_1a6_simple_formation",
            test_description="Test simple formation loading",
            test_area="1_foundation",
        )

    async def test_1a6_simple_formation(self):
        """Test loading and basic functionality of minimal formation."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1a6_simple_formation",
            description="Test simple formation with schema v1.0.0",
        )

        try:
            # Setup formation using minimal template
            print("\n1. Loading formation and starting overlord...")
            await self.setup_formation(template="minimal")
            overlord = self.overlord  # Overlord is already started by setup_formation
            print("✅ Formation and overlord ready")

            # Check basic structure
            print("\n2. Checking overlord structure...")
            print(f"   Formation ID: {overlord.formation_id}")
            print(f"   Agents loaded: {list(overlord.agents.keys())}")
            assert overlord.formation_id is not None
            assert "assistant" in overlord.agents
            print("✅ Basic structure verified")

            # Check IntentDetectionService
            print("\n3. Checking IntentDetectionService in agent...")
            agent = overlord.agents["assistant"]

            has_intent_service = hasattr(agent, "intent_service")
            print(f"   Agent has intent_service attribute: {has_intent_service}")

            if has_intent_service and agent.intent_service:
                print("   ✅ IntentDetectionService is initialized")

                # Test the service (fallback mode)
                result = asyncio.run(
                    agent.intent_service.detect_intent(
                        "Do you remember what we discussed?", IntentType.QUERY_TYPE
                    )
                )
                print(
                    f"   Fallback detection result: {result.intent} (confidence: {result.confidence})"
                )
            else:
                print("   ℹ️ IntentDetectionService not available (OK for minimal setup)")

            # Check memory system
            print("\n4. Checking memory system...")
            has_memory = hasattr(overlord, "memory_manager")
            print(f"   Memory manager available: {has_memory}")
            if has_memory and overlord.memory_manager:
                print("   ✅ Memory system is initialized")
            else:
                print("   ℹ️ No memory system (OK for minimal configuration)")

            # Test basic chat
            print("\n5. Testing basic chat...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(
                overlord.chat("Hello", user_id="test_user"), timeout=timeout
            )
            assert response is not None
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:100]}...")
            print("✅ Chat functionality works")

            # Stop overlord
            print("\n6. Stopping overlord...")
            await self.cleanup_formation()
            print("✅ Overlord stopped successfully")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a6_simple_formation",
                success=True,
                checks=[
                    "Formation loaded",
                    "Overlord started",
                    "Structure verified",
                    "IntentDetectionService checked",
                    "Memory system checked",
                    "Chat functionality works",
                    "Clean shutdown",
                ],
                transcript=[("Hello", response_text)],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a6_simple_formation",
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
        return asyncio.run(self.test_1a6_simple_formation())


if __name__ == "__main__":
    test = TestSimpleFormation()
    sys.exit(test.run_test())
