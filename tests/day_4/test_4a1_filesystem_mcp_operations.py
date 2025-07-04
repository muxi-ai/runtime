#!/usr/bin/env python3
"""Test 4A1: Filesystem MCP Operations - CRUD operations via MCP"""

import asyncio
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def run_async_test():
    """Run the entire test in a single async context."""

    print("\nTEST 4A1: Filesystem MCP Operations")
    print("Goal: Validate file creation, reading, updating, and deletion via MCP")
    print()

    # Create a temporary directory for testing
    test_dir = Path(tempfile.mkdtemp(prefix="muxi_test_"))
    print(f"Using test directory: {test_dir}")

    try:
        # Use the actual test formation which has database configured
        formation_path = Path("test-formations/formation-mcp")
        
        # Load formation
        formation = Formation()
        
        # Run sync operations in executor to avoid blocking
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, formation.load, str(formation_path))
        overlord = await loop.run_in_executor(None, formation.start_overlord)

        print("\n1. Testing file creation...")
        prompt = f"Create a file called 'test.txt' with content 'Hello World' in {test_dir}"
        print(f"Prompt: {prompt}")
        
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,  # Force synchronous processing
            stream=False,  # Force non-streaming
        )
        
        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            # Async processing - wait for it to complete
            print(f"Async response received: {response}")
            await asyncio.sleep(3)  # Give it time to process
        elif hasattr(response, '__aiter__'):
            # Streaming response - collect it
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response
        
        print(f"Response: {response}")
        
        # Verify file was created
        test_file = test_dir / "test.txt"
        if not test_file.exists():
            # Try waiting a bit more for async processing
            await asyncio.sleep(2)
        assert test_file.exists(), "File should have been created"
        assert test_file.read_text() == "Hello World", "File content should match"
        print("✓ File creation successful")

        print("\n2. Testing file reading...")
        prompt = f"Read the contents of test.txt from {test_dir}"
        print(f"Prompt: {prompt}")
        
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,  # Force synchronous processing
            stream=False,
        )
        
        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            print(f"Async response received: {response}")
            await asyncio.sleep(3)
        elif hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response
        
        print(f"Response: {response}")
        
        # For async responses, we may not have the content in the response
        if not isinstance(response, dict) or "request_id" not in response:
            assert "hello world" in str(response).lower(), "Response should contain file contents"
        print("✓ File reading successful")

        print("\n3. Testing file update...")
        prompt = f"Update test.txt in {test_dir} to say 'Hello MUXI'"
        print(f"Prompt: {prompt}")
        
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,  # Force synchronous processing
            stream=False,
        )
        
        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            print(f"Async response received: {response}")
            await asyncio.sleep(3)
        elif hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response
        
        print(f"Response: {response}")
        
        # Verify file was updated
        if test_file.read_text() != "Hello MUXI":
            await asyncio.sleep(2)
        assert test_file.read_text() == "Hello MUXI", "File content should be updated"
        print("✓ File update successful")

        print("\n4. Testing file deletion...")
        prompt = f"Delete test.txt from {test_dir}"
        print(f"Prompt: {prompt}")
        
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,  # Force synchronous processing
            stream=False,
        )
        
        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            print(f"Async response received: {response}")
            await asyncio.sleep(3)
        elif hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response
        
        print(f"Response: {response}")
        
        # Verify file was deleted
        if test_file.exists():
            await asyncio.sleep(2)
        assert not test_file.exists(), "File should have been deleted"
        print("✓ File deletion successful")

        print("\n5. Testing file creation with subdirectory...")
        json_content = '{"test": true}'
        prompt = f"Create a file called 'nested/data.json' with content '{json_content}' in {test_dir}"
        print(f"Prompt: {prompt}")
        
        response = await overlord.chat(
            user_id="user1",
            message=prompt,
            use_async=False,  # Force synchronous processing
            stream=False,
        )
        
        # Handle different response types
        if isinstance(response, dict) and "request_id" in response:
            print(f"Async response received: {response}")
            await asyncio.sleep(3)
        elif hasattr(response, '__aiter__'):
            full_response = ""
            async for chunk in response:
                full_response += chunk
            response = full_response
        
        print(f"Response: {response}")
        
        nested_file = test_dir / "nested" / "data.json"
        if not nested_file.exists():
            await asyncio.sleep(2)
        assert nested_file.exists(), "Nested file should have been created"
        assert json_content in nested_file.read_text(), "JSON content should match"
        print("✓ Nested file creation successful")

        print("\n🔚 Stopping overlord...")
        await loop.run_in_executor(None, formation.stop_overlord, 10.0)
        print("✅ Test complete!")

        return True

    except Exception as e:
        print(f"\n❌ Test 4A1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test directory
        if test_dir.exists():
            shutil.rmtree(test_dir)
            print(f"Cleaned up test directory: {test_dir}")


def main():
    """Main entry point."""
    print("Starting test with persistent event loop...")

    # Run everything in a single event loop that persists until completion
    try:
        success = asyncio.run(run_async_test())
        if success:
            print("\n✅ Test 4A1 PASSED: All filesystem MCP operations successful")
        else:
            print("\n❌ Test 4A1 FAILED")
        return success
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)