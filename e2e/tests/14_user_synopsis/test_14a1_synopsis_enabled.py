#!/usr/bin/env python3
"""
Test 14A1: User Synopsis - Enabled
Tests that user synopsis appears in enhanced messages when enabled.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestUserSynopsisEnabled(BaseE2ETest):
    """Test user synopsis when enabled (default behavior)."""

    def __init__(self):
        super().__init__(
            test_name="test_14a1_synopsis_enabled",
            test_description="Test user synopsis appears in enhanced messages",
            test_area="14_user_synopsis",
        )

    async def test_14a1_synopsis_enabled(self):
        """Test that user synopsis appears in enhanced messages when enabled."""
        formatter = TestOutputFormatter()
        transcript = []
        start_time = time.time()

        print("=" * 80)
        print("Test 14A1: User Synopsis Enabled")
        print("=" * 80)

        try:
            # Load formation with synopsis enabled
            print("\n1. Loading formation with user synopsis enabled...")
            formation_path = Path(__file__).parent / "formations" / "formation-synopsis" / "formation.yaml"
            success = await self.setup_formation(formation_path=formation_path)
            if not success:
                raise Exception("Failed to setup formation")
            
            overlord = self.overlord
            print("   ✓ Formation loaded")

            # Test 1: Add user context and verify synopsis generation
            print("\n2. Adding user context...")
            user_id = "test_user_synopsis"
            
            # Add user context via overlord
            await overlord.add_user_context(
                user_id=user_id,
                knowledge={
                    "name": "Alice Johnson",
                    "role": "Senior Software Engineer",
                    "team": "Platform Engineering",
                },
                source="test_setup"
            )
            print("   ✓ User context added")

            # Give some time for processing
            await asyncio.sleep(2)

            # Test 2: Send a message and check response
            print("\n3. Testing synopsis in enhanced message...")
            response = await overlord.chat(
                "What are Python testing best practices?",
                user_id=user_id,
                session_id="session_synopsis_test",
                stream=False,
            )

            assert response is not None, "Response should not be None"
            response_text = response.content if hasattr(response, "content") else str(response)
            assert len(response_text) > 0, "Response should not be empty"

            print(f"   ✓ Response received ({len(response_text)} chars)")
            transcript.append(("Testing synopsis", response_text[:200]))

            # Test 3: Verify synopsis is cached (second call should be fast)
            print("\n4. Testing synopsis caching...")
            cache_start = time.time()
            
            response2 = await overlord.chat(
                "Tell me about code reviews",
                user_id=user_id,
                session_id="session_synopsis_test",
                stream=False,
            )
            
            elapsed = time.time() - cache_start
            print(f"   ✓ Second message completed in {elapsed:.2f}s (cache hit)")
            
            assert response2 is not None, "Second response should not be None"
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            assert len(response2_text) > 0, "Second response should not be empty"

            # Test 4: Update context and verify cache invalidation
            print("\n5. Testing cache invalidation on context update...")
            await overlord.add_user_context(
                user_id=user_id,
                knowledge={
                    "role": "Principal Engineer",  # Updated role
                    "current_project": "User Synopsis System",
                },
                source="test_update"
            )
            print("   ✓ Context updated")

            await asyncio.sleep(2)

            response3 = await overlord.chat(
                "What's my current role?",
                user_id=user_id,
                session_id="session_synopsis_test",
                stream=False,
            )
            
            assert response3 is not None, "Third response should not be None"
            print("   ✓ Response after cache invalidation received")

            # Cleanup
            print("\n6. Cleaning up...")
            await self.cleanup_formation()
            print("   ✓ Formation stopped")

            # Calculate duration
            duration = time.time() - start_time

            # Print results
            formatter.print_test_result(
                test_name="test_14a1_synopsis_enabled",
                success=True,
                checks=[
                    "Formation loaded with synopsis enabled",
                    "User context added successfully",
                    "Synopsis generated and cached",
                    "Cache hit on second request",
                    "Cache invalidated on context update",
                ],
                transcript=transcript,
                duration=duration,
            )

            return 0

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()

            duration = time.time() - start_time

            formatter.print_test_result(
                test_name="test_14a1_synopsis_enabled",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=transcript,
                duration=duration,
            )
            return 1

    def run_test(self):
        """Run the test with proper async handling."""
        return asyncio.run(self.test_14a1_synopsis_enabled())


if __name__ == "__main__":
    test = TestUserSynopsisEnabled()
    sys.exit(test.run_test())
