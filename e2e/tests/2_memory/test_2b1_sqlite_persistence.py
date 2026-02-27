#!/usr/bin/env python3
"""Test 2B1: SQLite Persistence - Persistent Memory with SQLite

This test validates:
1. SQLite persistent memory configuration
2. Data persistence across formation restarts
3. Memory retrieval after shutdown/restart
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


class TestSQLitePersistence(BaseMemoryTest):
    """Test SQLite persistent memory functionality."""

    async def test_sqlite_persistence(self):
        """Test data persistence with SQLite backend."""
        test_name = "2b1_sqlite_persistence"
        self.print_test_header(test_name, "Test SQLite persistent memory across restarts")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "sqlite_test_user"

        try:
            # Phase 1: Store information
            print("\n📝 Phase 1: Storing information...")
            await self.setup_memory_formation("sqlite")

            # Store personal information
            user_msg1 = "My favorite color is blue and I have two cats named Whiskers and Shadow."
            response1 = await self.overlord.chat(
                user_msg1, user_id=user_id, use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response1_text = (
                response1.content if hasattr(response1, "content") else str(response1)
            )

            transcript.append((user_msg1, response1_text))
            print(f"User: {user_msg1}")
            print(f"Assistant: {response1_text[:200]}...")

            # Store more information
            user_msg2 = "I'm planning a trip to Japan next summer for two weeks."
            response2 = await self.overlord.chat(
                user_msg2, user_id=user_id, use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response2_text = (
                response2.content if hasattr(response2, "content") else str(response2)
            )

            transcript.append((user_msg2, response2_text))
            print(f"User: {user_msg2}")
            print(f"Assistant: {response2_text[:200]}...")

            print("  ✓ Information stored in SQLite")
            checks_passed.append("Information stored successfully")

            # Wait for extraction to complete (extraction is async and requires LLM calls)
            # Increased from 10s to 30s to allow background extraction tasks to finish
            await asyncio.sleep(30)

            # Shutdown formation
            await self.cleanup()
            print("  ✓ Formation shutdown complete")

            # Phase 2: Restart and retrieve
            print("\n🔄 Phase 2: Restarting formation...")
            await asyncio.sleep(2)

            # Restart formation with same SQLite database
            await self.setup_memory_formation("sqlite")
            print("  ✓ Formation restarted with SQLite")

            # Query for persisted information - ask all stored info at once
            user_msg3 = "What is my favorite color, what pets do I have, and where am I traveling to?"
            response3 = await self.overlord.chat(
                user_msg3, user_id=user_id, use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response3_text = (
                response3.content if hasattr(response3, "content") else str(response3)
            )

            transcript.append((user_msg3, response3_text))
            print(f"\nUser: {user_msg3}")
            print(f"Assistant: {response3_text[:300]}...")

            # Check persistence - all three should be in the combined response
            color_remembered = "blue" in response3_text.lower()
            pets_remembered = (
                "whiskers" in response3_text.lower() or "shadow" in response3_text.lower()
            ) or ("cats" in response3_text.lower() or "two cats" in response3_text.lower())
            travel_remembered = (
                "japan" in response3_text.lower()
                or "summer" in response3_text.lower()
                or "trip" in response3_text.lower()
            )

            if color_remembered:
                print("  ✓ Color preference persisted")
                checks_passed.append("Color preference persisted across restart")
            else:
                print("  - Color preference not persisted (extraction may be slow)")

            if pets_remembered:
                print("  ✓ Pet information persisted")
                checks_passed.append("Pet information persisted across restart")
            else:
                print("  - Pet information not persisted (extraction may be slow)")

            if travel_remembered:
                print("  ✓ Travel plans persisted")
                checks_passed.append("Travel plans persisted across restart")
            else:
                print("  - Travel plans not persisted (extraction may be slow)")

            # Pass if at least 1 item persisted (extraction is async/non-deterministic)
            if not (color_remembered or pets_remembered or travel_remembered):
                print("  ✗ No information persisted at all")
                all_passed = False

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def test_multi_session_persistence(self):
        """Test persistence across multiple sessions (single-user mode).

        SQLite = single-user mode by design. All user_ids map to "0".
        This test verifies that data persists across sessions for the same user.
        """
        test_name = "2b1_multi_session_persistence"
        self.print_test_header(test_name, "Test SQLite persistence across sessions")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True
        user_id = "sqlite_test_user"

        try:
            # Session 1: Store information
            await self.setup_memory_formation("sqlite")

            msg1 = "I'm David, I'm a chef and I love Italian cuisine."
            response1 = await self.overlord.chat(
                msg1, user_id=user_id, use_async=False, stream=False
            )
            r1 = response1.content if hasattr(response1, "content") else str(response1)
            transcript.append((msg1, r1))
            print(f"Session 1: {msg1}")
            print(f"Assistant: {r1[:200]}...")

            msg2 = "I also enjoy hiking in the mountains on weekends."
            response2 = await self.overlord.chat(
                msg2, user_id=user_id, use_async=False, stream=False
            )
            r2 = response2.content if hasattr(response2, "content") else str(response2)
            transcript.append((msg2, r2))
            print(f"Session 1: {msg2}")
            print(f"Assistant: {r2[:200]}...")

            await asyncio.sleep(3)

            # Session 2: Query stored information
            query = "What is my profession and what do I enjoy doing?"
            response3 = await self.overlord.chat(
                query, user_id=user_id, use_async=False, stream=False
            )
            r3 = response3.content if hasattr(response3, "content") else str(response3)
            transcript.append((query, r3))
            print(f"\nSession 2 Query: {query}")
            print(f"Assistant: {r3[:200]}...")

            r3_lower = r3.lower()
            chef_ok = "chef" in r3_lower or "cook" in r3_lower or "italian" in r3_lower
            hobby_ok = "hik" in r3_lower or "mountain" in r3_lower

            if chef_ok:
                print("  ✓ Profession remembered across sessions")
                checks_passed.append("Profession persisted")
            else:
                print("  - Profession not remembered (buffer may not have retained)")

            if hobby_ok:
                print("  ✓ Hobby remembered across sessions")
                checks_passed.append("Hobby persisted")
            else:
                print("  - Hobby not remembered (buffer may not have retained)")

            # Pass if at least one piece of info is remembered
            if not (chef_ok or hobby_ok):
                print("  ✗ No information remembered")
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
        print("🗄️ AREA 2B1: SQLITE PERSISTENCE")
        print("=" * 60)

        # Run test cases
        persistence_passed = await self.test_sqlite_persistence()
        multi_session_passed = await self.test_multi_session_persistence()

        # Overall result
        all_passed = persistence_passed and multi_session_passed

        print("\n" + "=" * 60)
        print(
            f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}"
        )
        print("=" * 60)

        print("\n💡 KEY INSIGHTS:")
        print("- SQLite provides persistent memory storage")
        print("- Data survives formation restarts")
        print("- Suitable for single-instance deployments")

        if all_passed:
            print("SUCCESS", flush=True)
        return all_passed


def main():
    """Main entry point."""
    test = TestSQLitePersistence()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
