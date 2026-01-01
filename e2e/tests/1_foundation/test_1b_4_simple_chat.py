#!/usr/bin/env python3
"""Test 1b4: Simple chat with minimal formation using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from the common module
from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSimpleChat(BaseE2ETest):
    """Test simple chat functionality with standardized approach."""

    def __init__(self):
        super().__init__(
            test_name="test_1b4_simple_chat",
            test_description="Test simple chat with minimal formation",
            test_area="1_foundation",
        )

    async def test_1b4_simple_chat(self):
        """Test simple chat with minimal formation."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1b4_simple_chat", description="Test simple chat with minimal formation"
        )

        try:
            # Setup formation using Pattern 1 (minimal template)
            print("\n1. Setting up formation and starting overlord...")
            await self.setup_formation(template="minimal")
            overlord = self.overlord  # Overlord is already started by setup_formation
            print("✅ Formation and overlord ready")

            # Check basic structure
            print("\n2. Checking overlord structure...")
            print(f"   Formation ID: {overlord.formation_id}")
            print(f"   Agents: {list(overlord.agents.keys())}")
            assert overlord.formation_id is not None
            assert "assistant" in overlord.agents
            print("✅ Structure verified")

            # Check agent initialization
            print("\n3. Checking agent is properly initialized...")
            agent = overlord.agents["assistant"]
            assert agent is not None
            print(f"   Agent type: {type(agent).__name__}")
            print("✅ Agent properly initialized")

            # Test simple chat
            print("\n4. Testing simple chat...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(
                overlord.chat("Hello, how are you?", user_id="test_user"), timeout=timeout
            )

            # Verify response
            assert response is not None
            # Handle both string and object responses
            if hasattr(response, "content"):
                response_text = response.content
            else:
                response_text = str(response)
            assert len(response_text) > 0
            print(f"   Response: {response_text[:100]}...")
            print("✅ Chat response received")

            # Stop overlord
            print("\n5. Stopping overlord...")
            await self.cleanup_formation()
            print("✅ Overlord stopped successfully")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b4_simple_chat",
                success=True,
                checks=[
                    "Formation loaded",
                    "Overlord started",
                    "Structure verified",
                    "Agent initialized",
                    "Chat response received",
                    "Clean shutdown",
                ],
                transcript=[("Hello, how are you?", response_text)],
                duration=duration,
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b4_simple_chat",
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
        return asyncio.run(self.test_1b4_simple_chat())


if __name__ == "__main__":
    test = TestSimpleChat()
    sys.exit(test.run_test())
