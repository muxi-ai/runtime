#!/usr/bin/env python3
"""Test 1b1: Single agent response tests using standardized structure."""

import asyncio
import time
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestSingleAgentResponse(BaseE2ETest):
    """Test single agent response functionality."""

    def __init__(self):
        super().__init__(
            test_name="test_1b1_single_agent_response",
            test_description="Test single agent response functionality",
            test_area="1_foundation"
        )

    def test_1b1_single_agent_response(self):
        """Test single agent response with standard formation."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        transcript = []
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1b1_single_agent_response",
            description="Test single agent response functionality"
        )

        try:
            # Setup formation using standard template (Pattern 1)
            print("\n1. Setting up formation and starting overlord...")
            formation = asyncio.run(self.setup_formation(template="standard"))
            overlord = self.overlord  # Overlord is already started by setup_formation
            print("✅ Formation and overlord ready")

            # Test 1: Basic helpfulness query
            print("\n2. Testing basic helpfulness query...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = asyncio.run(
                asyncio.wait_for(
                    overlord.chat("What can you help me with?", user_id="test_user", stream=False),
                    timeout=timeout
                )
            )

            assert response is not None
            response_text = response.content if hasattr(response, "content") else str(response)
            assert len(response_text) > 0

            # Verify response mentions helping
            response_lower = response_text.lower()
            assert any(word in response_lower for word in ["help", "assist", "support", "can"])
            print(f"   Response: {response_text[:100]}...")
            print("✅ Helpfulness query passed")
            transcript.append(("What can you help me with?", response_text))

            # Test 2: Fun fact query
            print("\n3. Testing fun fact query...")
            response2 = asyncio.run(
                asyncio.wait_for(
                    overlord.chat("Tell me a fun fact", user_id="test_user", stream=False),
                    timeout=timeout
                )
            )

            assert response2 is not None
            response2_text = response2.content if hasattr(response2, "content") else str(response2)
            assert len(response2_text) > 0
            print(f"   Response: {response2_text[:100]}...")
            print("✅ Fun fact query passed")
            transcript.append(("Tell me a fun fact", response2_text))

            # Stop overlord
            print("\n4. Stopping overlord...")
            asyncio.run(self.cleanup_formation())
            print("✅ Overlord stopped successfully")

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b1_single_agent_response",
                success=True,
                checks=[
                    "Formation loaded",
                    "Overlord started",
                    "Helpfulness query passed",
                    "Fun fact query passed",
                    "Clean shutdown"
                ],
                transcript=transcript,
                duration=duration
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b1_single_agent_response",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=transcript,
                duration=duration
            )
            raise
        finally:
            return 0 if success else 1

    def test_1b1_response_consistency(self):
        """Test response consistency across multiple queries."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        transcript = []
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_1b1_response_consistency",
            description="Test agent response consistency"
        )

        try:
            # Setup formation
            print("\n1. Setting up formation...")
            formation = asyncio.run(self.setup_formation(template="standard"))
            overlord = self.overlord  # Overlord is already started by setup_formation
            print("✅ Formation ready")

            # Test multiple queries
            print("\n2. Testing multiple queries for consistency...")
            queries = [
                "Hello",
                "What's the weather like?",
                "Can you help me learn Python?",
                "What's 10 divided by 2?",
            ]

            responses = []
            timeout = TestTimeouts.get_timeout("simple_chat")

            for i, query in enumerate(queries, 1):
                print(f"   Query {i}: {query}")
                response = asyncio.run(
                    asyncio.wait_for(
                        overlord.chat(query, stream=False, user_id="test_user"),
                        timeout=timeout
                    )
                )
                assert response is not None
                response_text = response.content if hasattr(response, "content") else str(response)
                assert len(response_text) > 0
                assert not response_text.isspace()
                responses.append(response_text)
                transcript.append((query, response_text))
                print(f"   Response: {response_text[:50]}...")

            # All responses should be unique
            assert len(set(responses)) == len(responses)
            print("✅ All responses are unique")

            # Clean up
            asyncio.run(self.cleanup_formation())

            # Print results
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b1_response_consistency",
                success=True,
                checks=[
                    "Formation loaded",
                    "All queries received responses",
                    "All responses are unique",
                    "No empty responses"
                ],
                transcript=transcript,
                duration=duration
            )
            success = True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1b1_response_consistency",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=transcript,
                duration=duration
            )
            raise
        finally:
            return 0 if success else 1


if __name__ == "__main__":
    test = TestSingleAgentResponse()
    print("\n" + "="*60)
    print("Running Test 1b1: Single Agent Response")
    print("="*60)
    result1 = test.test_1b1_single_agent_response()
    print("\n" + "="*60)
    print("Running Test 1b1: Response Consistency")
    print("="*60)
    result2 = test.test_1b1_response_consistency()
    sys.exit(0 if (result1 == 0 and result2 == 0) else 1)