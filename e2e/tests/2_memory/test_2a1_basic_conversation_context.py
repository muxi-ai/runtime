#!/usr/bin/env python3
"""Test 2A1: Basic Conversation Context - Buffer Memory Configuration

This test validates:
1. Buffer memory configuration (local vs remote)
2. Conversation context retention
3. Memory functionality across messages
"""

import asyncio
import time
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from base_memory_test import BaseMemoryTest


class TestBasicConversationContext(BaseMemoryTest):
    """Test basic conversation context with buffer memory."""

    async def test_buffer_configurations(self):
        """Test loading different buffer configurations."""
        test_name = "2a1_buffer_configurations"
        self.print_test_header(test_name, "Test local and remote buffer memory configurations")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        # Test local buffer configuration
        try:
            await self.setup_memory_formation("buffer_local")
            config = self.formation.config.get("memory", {}).get("buffer", {})

            mode = config.get("mode", "local")
            size = config.get("size", 10)

            print(f"  ✓ Local buffer loaded: mode={mode}, size={size}")
            checks_passed.append(f"Local buffer configuration loaded (size={size})")

            await self.cleanup()

        except Exception as e:
            print(f"  ✗ Failed to load local buffer: {e}")
            all_passed = False

        # Test remote buffer configuration
        try:
            await self.setup_memory_formation("buffer_remote")
            config = self.formation.config.get("memory", {}).get("buffer", {})

            mode = config.get("mode", "remote")
            size = config.get("size", 10)

            print(f"  ✓ Remote buffer loaded: mode={mode}, size={size}")
            checks_passed.append(f"Remote buffer configuration loaded (size={size})")

            await self.cleanup()

        except Exception as e:
            print(f"  ✗ Failed to load remote buffer: {e}")
            all_passed = False

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def test_conversation_retention(self):
        """Test conversation context retention with buffer memory."""
        test_name = "2a1_conversation_retention"
        self.print_test_header(test_name, "Test conversation context retention across messages")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation with local buffer
            await self.setup_memory_formation("buffer_local")

            # Use consistent session_id for all messages in this conversation
            test_session_id = "test_conversation_retention"

            # First exchange - store information
            user_msg1 = "My name is Alice and I work at TechCorp as a software engineer."
            response1 = await self.overlord.chat(
                user_msg1, user_id="test_user", session_id=test_session_id, use_async=False, stream=False
            )

            # Handle response
            if hasattr(response1, "__aiter__"):
                response1_text = ""
                async for chunk in response1:
                    response1_text += chunk
            else:
                response1_text = (
                    response1.content if hasattr(response1, "content") else str(response1)
                )

            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            # Wait for memory storage
            await asyncio.sleep(3)

            # Second exchange - test retention
            user_msg2 = "Where do I work again?"
            response2 = await self.overlord.chat(
                user_msg2, user_id="test_user", session_id=test_session_id, use_async=False, stream=False
            )

            # Handle response
            if hasattr(response2, "__aiter__"):
                response2_text = ""
                async for chunk in response2:
                    response2_text += chunk
            else:
                response2_text = (
                    response2.content if hasattr(response2, "content") else str(response2)
                )

            transcript.append((user_msg2, response2_text))
            print(f"\nUser: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            # Check retention
            context_retained = (
                "alice" in response2_text.lower()
                or "techcorp" in response2_text.lower()
                or "software engineer" in response2_text.lower()
            )

            if context_retained:
                print("  ✓ Context was retained - mentioned Alice/TechCorp/engineer")
                checks_passed.append("Context retained across messages")
            else:
                print("  ✗ Context was not retained")
                all_passed = False

            # Third exchange - test deeper retention
            user_msg3 = "What is my profession?"
            response3 = await self.overlord.chat(
                user_msg3, user_id="test_user", session_id=test_session_id, use_async=False, stream=False
            )

            # Handle response
            if hasattr(response3, "__aiter__"):
                response3_text = ""
                async for chunk in response3:
                    response3_text += chunk
            else:
                response3_text = (
                    response3.content if hasattr(response3, "content") else str(response3)
                )

            transcript.append((user_msg3, response3_text))
            print(f"\nUser: {user_msg3}")
            print(f"Assistant: {response3_text[:200]}...")

            profession_retained = (
                "engineer" in response3_text.lower() or "software" in response3_text.lower()
            )

            if profession_retained:
                print("  ✓ Profession was retained - mentioned engineering/software")
                checks_passed.append("Detailed information retained")
            else:
                print("  ✗ Profession was not retained")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🧠 AREA 2A1: BASIC CONVERSATION CONTEXT")
        print("=" * 60)

        # Run test cases
        config_passed = await self.test_buffer_configurations()
        retention_passed = await self.test_conversation_retention()

        # Overall result
        all_passed = config_passed and retention_passed

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- Local buffer mode uses in-memory FAISS for vector search")
        print("- Remote buffer mode connects to external FAISSx servers")
        print("- Buffer memory retains conversation context across messages")
        print("- Context is preserved for subsequent queries")

        return all_passed


def main():
    """Main entry point."""
    test = TestBasicConversationContext()
    result = asyncio.run(test.run_test())
    if result:
        print("SUCCESS", flush=True)
    import os; os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
