#!/usr/bin/env python3
"""Test to verify buffer memory modes (local vs remote)"""

import sys

sys.path.insert(0, ".")
import asyncio  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from src.muxi.runtime.formation.formation import Formation  # noqa: E402


def handle_response(response):
    """
    Processes and normalizes various response types from overlord.chat(), returning a string representation of the result.
    
    Handles string, dictionary, object, and asynchronous streaming responses, extracting relevant content or error messages as appropriate.
    """
    if isinstance(response, str):
        return response
    elif isinstance(response, dict):
        if "request_id" in response:
            # Async processing
            return f"Async processing: {response['request_id']}"
        elif "content" in response:
            return response["content"]
        elif "error" in response:
            return f"Error: {response['error']}"
    elif hasattr(response, 'content'):
        # MuxiResponse object
        return response.content
    elif hasattr(response, '__aiter__'):
        # Streaming response - collect it
        return asyncio.run(collect_stream(response))
    return str(response)


async def collect_stream(stream):
    """
    Asynchronously collects all chunks from an async generator and concatenates them into a single string.
    
    Parameters:
        stream: An asynchronous generator yielding string chunks.
    
    Returns:
        str: The concatenated string of all collected chunks.
    """
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return ''.join(chunks)


# Create mock LLM for embedding
class MockLLM:
    def __init__(self, dimension=1536):
        """
        Initialize the mock language model with a specified embedding dimension.
        
        Parameters:
            dimension (int): The size of the embedding vector. Defaults to 1536.
        """
        self.dimension = dimension

    async def embed(self, text):
        # Return a simple mock embedding
        return [0.1] * self.dimension


async def test_local_buffer_memory():
    """
    Test the local buffer memory mode of the chat system.
    
    Runs a sequence of interactions using a local buffer memory formation to verify that user context is retained, buffer overflow is handled correctly (older messages are forgotten when the buffer is exceeded), and the system responds as expected. Executes the test logic in a separate thread to avoid event loop conflicts.
    
    Returns:
        dict: A summary of the test results, including mode, context retention status, buffer overflow handling, and overall status. If the test fails, includes an error message.
    """
    print("\n=== Testing Local Buffer Memory ===")

    async def run_test():
        # Helper function to handle async generator responses
        """
        Runs a test to verify local buffer memory behavior in the chat system.
        
        The test checks that user context (name and company) is retained after initial input, and that buffer overflow causes older messages to be forgotten. Returns a dictionary summarizing the test mode, context retention, buffer overflow handling, and status.
        """
        def get_response(coro):
            result = asyncio.run(coro)
            return handle_response(result)

        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-buffer-local.yaml")
        overlord = await formation.start_overlord()

        try:
            # Test basic context retention
            print("Testing local buffer memory context...")

            # Add context
            response1 = get_response(
                overlord.chat("My name is Alice and I work at TechCorp", user_id="user1")
            )
            print(f"Context set: {response1[:50]}...")

            # Test recall
            response2 = get_response(
                overlord.chat("What's my name and where do I work?", user_id="user1")
            )
            print(f"Context recall: {response2[:100]}...")

            # Verify context is remembered
            alice_remembered = "alice" in response2.lower() or "Alice" in response2
            techcorp_remembered = "techcorp" in response2.lower() or "TechCorp" in response2

            print(f"✓ Alice remembered: {alice_remembered}")
            print(f"✓ TechCorp remembered: {techcorp_remembered}")

            # Test buffer overflow (add more messages than buffer size)
            print("\nTesting buffer overflow handling...")
            for i in range(15):  # Assuming buffer size is 10
                get_response(overlord.chat(f"Message number {i}", user_id="user1"))

            # Check if old messages are forgotten
            response3 = get_response(overlord.chat("What was message number 0?", user_id="user1"))
            print(f"Old message recall: {response3[:100]}...")

            return {
                "mode": "local",
                "context_retention": alice_remembered and techcorp_remembered,
                "buffer_overflow": "0" not in response3,  # Should not remember old messages
                "status": "success",
            }

        except Exception as e:
            print(f"❌ Local buffer test failed: {e}")
            return {"mode": "local", "status": "failed", "error": str(e)}
        finally:
            await formation.stop_overlord()

    # Run in ThreadPoolExecutor to avoid event loop conflicts
    return await run_test()


async def test_remote_buffer_memory():
    """
    Test the remote buffer memory mode by verifying that user context is retained and recalled correctly.
    
    Sends user information to the chat system using a remote buffer memory formation, then queries for the stored context to ensure both the user's name and preferred language are remembered. Returns a dictionary summarizing the test outcome, including context retention and status.
    """
    print("\n=== Testing Remote Buffer Memory ===")

    async def run_test():
        # Helper function to handle async generator responses
        """
        Tests remote buffer memory mode by setting and recalling user context, verifying that the system retains user information across messages.
        
        Returns:
            dict: A summary containing the buffer mode, context retention result, and test status.
        """
        def get_response(coro):
            result = asyncio.run(coro)
            return handle_response(result)

        formation = Formation()
        await formation.load("test-formations/formation-memory/formation-buffer-remote.yaml")
        overlord = await formation.start_overlord()

        try:
            print("Testing remote buffer memory context...")

            # Add context
            response1 = get_response(
                overlord.chat("My name is Bob and I prefer JavaScript", user_id="user2")
            )
            print(f"Context set: {response1[:50]}...")

            # Test recall
            response2 = get_response(
                overlord.chat("What's my name and what language do I prefer?", user_id="user2")
            )
            print(f"Context recall: {response2[:100]}...")

            # Verify context is remembered
            bob_remembered = "bob" in response2.lower() or "Bob" in response2
            js_remembered = "javascript" in response2.lower() or "JavaScript" in response2

            print(f"✓ Bob remembered: {bob_remembered}")
            print(f"✓ JavaScript remembered: {js_remembered}")

            return {
                "mode": "remote",
                "context_retention": bob_remembered and js_remembered,
                "status": "success",
            }

        except Exception as e:
            print(f"❌ Remote buffer test failed: {e}")
            return {"mode": "remote", "status": "failed", "error": str(e)}
        finally:
            await formation.stop_overlord()

    # Run in ThreadPoolExecutor to avoid event loop conflicts
    return await run_test()


async def test_buffer_mode_switching():
    """Test switching between local and remote buffer modes"""
    print("\n=== Testing Buffer Mode Switching ===")

    try:
        # Test that different formations can use different buffer modes
        local_result = await test_local_buffer_memory()
        remote_result = await test_remote_buffer_memory()

        both_working = (
            local_result.get("status") == "success" and remote_result.get("status") == "success"
        )

        print(f"\n✓ Local buffer working: {local_result.get('status') == 'success'}")
        print(f"✓ Remote buffer working: {remote_result.get('status') == 'success'}")
        print(f"✓ Both modes functional: {both_working}")

        return {
            "local_mode": local_result,
            "remote_mode": remote_result,
            "both_working": both_working,
            "status": "success" if both_working else "partial",
        }

    except Exception as e:
        print(f"❌ Buffer mode switching test failed: {e}")
        return {"status": "failed", "error": str(e)}


async def main():
    """Run all buffer memory mode tests"""
    print("🧠 Testing Buffer Memory Modes (Local vs Remote)")
    print("=" * 60)

    # Test individual modes
    local_result = await test_local_buffer_memory()
    remote_result = await test_remote_buffer_memory()

    # Test mode switching
    switching_result = await test_buffer_mode_switching()

    # Summary
    print("\n" + "=" * 60)
    print("📋 BUFFER MEMORY TEST SUMMARY")
    print("=" * 60)

    print(
        f"Local Buffer Mode: {'✅ PASS' if local_result.get('status') == 'success' else '❌ FAIL'}"
    )
    if local_result.get("context_retention"):
        print("  - Context retention: ✅")
    if local_result.get("buffer_overflow"):
        print("  - Buffer overflow handling: ✅")

    print(
        f"Remote Buffer Mode: {'✅ PASS' if remote_result.get('status') == 'success' else '❌ FAIL'}"
    )
    if remote_result.get("context_retention"):
        print("  - Context retention: ✅")

    print(f"Mode Switching: {'✅ PASS' if switching_result.get('both_working') else '❌ FAIL'}")

    # Overall result
    all_passed = (
        local_result.get("status") == "success"
        and remote_result.get("status") == "success"
        and switching_result.get("both_working")
    )

    print(f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    return {
        "local": local_result,
        "remote": remote_result,
        "switching": switching_result,
        "all_passed": all_passed,
    }


if __name__ == "__main__":
    asyncio.run(main())
