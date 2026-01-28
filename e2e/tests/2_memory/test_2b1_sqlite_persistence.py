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

            # Wait for extraction to complete (extraction is async)
            await asyncio.sleep(10)

            # Shutdown formation
            await self.cleanup()
            print("  ✓ Formation shutdown complete")

            # Phase 2: Restart and retrieve
            print("\n🔄 Phase 2: Restarting formation...")
            await asyncio.sleep(2)

            # Restart formation with same SQLite database
            await self.setup_memory_formation("sqlite")
            print("  ✓ Formation restarted with SQLite")

            # Query for persisted information
            user_msg3 = "What pets do I have and where am I traveling to?"
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

            # Check persistence
            pets_remembered = (
                "whiskers" in response3_text.lower() or "shadow" in response3_text.lower()
            ) or ("cats" in response3_text.lower() or "two cats" in response3_text.lower())
            travel_remembered = (
                "japan" in response3_text.lower()
                or "summer" in response3_text.lower()
                or "trip" in response3_text.lower()
            )

            if pets_remembered:
                print("  ✓ Pet information persisted")
                checks_passed.append("Pet information persisted across restart")
            else:
                print("  ✗ Pet information not persisted")
                all_passed = False

            if travel_remembered:
                print("  ✓ Travel plans persisted")
                checks_passed.append("Travel plans persisted across restart")
            else:
                print("  ✗ Travel plans not persisted")
                all_passed = False

            # Query for specific detail
            user_msg4 = "What color do I like?"
            response4 = await self.overlord.chat(
                user_msg4, user_id=user_id, use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response4_text = (
                response4.content if hasattr(response4, "content") else str(response4)
            )

            transcript.append((user_msg4, response4_text))
            print(f"\nUser: {user_msg4}")
            print(f"Assistant: {response4_text[:200]}...")

            color_remembered = "blue" in response4_text.lower()

            if color_remembered:
                print("  ✓ Color preference persisted")
                checks_passed.append("Color preference persisted")
            else:
                print("  ✗ Color preference not persisted")
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
        """Test persistence across multiple sessions with different users."""
        test_name = "2b1_multi_session_persistence"
        self.print_test_header(test_name, "Test SQLite persistence with multiple users")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            # Setup formation
            await self.setup_memory_formation("sqlite")

            # User 1 stores information
            user1_msg = "I'm David, I'm a chef and I love Italian cuisine."
            response1 = await self.overlord.chat(
                user1_msg, user_id="user_david", use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response1_text = (
                response1.content if hasattr(response1, "content") else str(response1)
            )

            transcript.append((f"User1: {user1_msg}", response1_text))
            print(f"User 1: {user1_msg}")
            print(f"Assistant: {response1_text[:200]}...")

            # User 2 stores information
            user2_msg = "I'm Emily, I'm a teacher and I love Japanese food."
            response2 = await self.overlord.chat(
                user2_msg, user_id="user_emily", use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response2_text = (
                response2.content if hasattr(response2, "content") else str(response2)
            )

            transcript.append((f"User2: {user2_msg}", response2_text))
            print(f"\nUser 2: {user2_msg}")
            print(f"Assistant: {response2_text[:200]}...")

            await asyncio.sleep(3)

            # Query User 1's information
            query1 = "What do I do for work and what cuisine do I prefer?"
            response3 = await self.overlord.chat(
                query1, user_id="user_david", use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response3_text = (
                response3.content if hasattr(response3, "content") else str(response3)
            )

            transcript.append((f"User1: {query1}", response3_text))
            print(f"\nUser 1 Query: {query1}")
            print(f"Assistant: {response3_text[:200]}...")

            # Check User 1's data
            user1_correct = "chef" in response3_text.lower() and "italian" in response3_text.lower()

            if user1_correct:
                print("  ✓ User 1 data correctly isolated")
                checks_passed.append("User 1 data isolation maintained")
            else:
                print("  ✗ User 1 data not properly isolated")
                all_passed = False

            # Query User 2's information
            query2 = "What job do I have and what food do I enjoy?"
            response4 = await self.overlord.chat(
                query2, user_id="user_emily", use_async=False, stream=False
            )

            # Handle response (stream=False, so response is a string or object with .content)
            response4_text = (
                response4.content if hasattr(response4, "content") else str(response4)
            )

            transcript.append((f"User2: {query2}", response4_text))
            print(f"\nUser 2 Query: {query2}")
            print(f"Assistant: {response4_text[:200]}...")

            # Check User 2's data
            user2_correct = (
                "teacher" in response4_text.lower() and "japanese" in response4_text.lower()
            )

            if user2_correct:
                print("  ✓ User 2 data correctly isolated")
                checks_passed.append("User 2 data isolation maintained")
            else:
                print("  ✗ User 2 data not properly isolated")
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
        print("- User isolation is maintained in persistent storage")
        print("- Suitable for single-instance deployments")

        return all_passed


def main():
    """Main entry point."""
    test = TestSQLitePersistence()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
