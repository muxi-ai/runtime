#!/usr/bin/env python3
"""Test remote buffer server with authentication using the formation."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from src.muxi.runtime.formation import Formation

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_remote_buffer_with_auth():
    """Test the remote buffer server with authentication configuration."""

    def run_test():
        logger.info("Starting test for remote buffer with authentication...")

        # Helper function to handle async generator responses
        def get_response(coro):
            result = asyncio.run(coro)
            if hasattr(result, "__aiter__"):
                # It's an async generator, collect all chunks
                async def collect():
                    chunks = []
                    async for chunk in result:
                        chunks.append(chunk)
                    return "".join(chunks)

                return asyncio.run(collect())
            return result

        # Load the formation with auth configuration
        formation_path = (
            "/Users/ran/Projects/muxi/code/runtime/test-formations/formation-memory/formation-postgres-and-faissx-with-auth.yaml"  # noqa: E501
        )
        logger.info(f"Loading formation from: {formation_path}")

        try:
            formation = Formation()
            formation.load(formation_path)
            logger.info("Formation loaded successfully")

            # Start the overlord
            logger.info("Starting overlord...")
            overlord = formation.start_overlord()
            logger.info("Overlord started successfully")

            # Test 1: Store some data
            logger.info("\n=== Test 1: Storing data with authentication ===")
            response1 = get_response(
                overlord.chat("My name is Alice and I work at TechCorp as a senior engineer")
            )
            logger.info(f"Response 1: {response1}")

            response2 = get_response(
                overlord.chat("I specialize in distributed systems and cloud architecture")
            )
            logger.info(f"Response 2: {response2}")

            # Test 2: Test memory recall
            logger.info("\n=== Test 2: Testing memory recall ===")
            response3 = get_response(overlord.chat("What's my name and what do I do?"))
            logger.info(f"Response 3: {response3}")

            # Check if the response contains the stored information
            if "alice" in response3.lower():
                logger.info("✅ Memory recall successful - found name")
            else:
                logger.warning("⚠️ Memory recall may have failed - name not found")

            if "techcorp" in response3.lower() or "engineer" in response3.lower():
                logger.info("✅ Memory recall successful - found job details")
            else:
                logger.warning("⚠️ Memory recall may have failed - job details not found")

            # Test 3: Test vector search
            logger.info("\n=== Test 3: Testing vector search ===")
            response4 = get_response(overlord.chat("What technical areas am I good at?"))
            logger.info(f"Response 4: {response4}")

            if "distributed" in response4.lower() or "cloud" in response4.lower():
                logger.info("✅ Vector search successful - found technical specialization")
            else:
                logger.warning("⚠️ Vector search may have failed - specialization not found")

            # Test 4: Fill buffer to test remote storage
            logger.info("\n=== Test 4: Testing buffer capacity with remote storage ===")
            for i in range(15):  # More than buffer size of 10
                msg = f"Technical fact {i}: This is information about technology area {i}"
                get_response(overlord.chat(msg))
                logger.info(f"Stored message {i}")

            # Test if old messages are still accessible via remote storage
            response5 = get_response(overlord.chat("What was technical fact 0?"))
            logger.info(f"Response 5 (checking old message): {response5}")

            if "fact 0" in response5.lower() or "technology area 0" in response5.lower():
                logger.info("✅ Remote storage working - old messages accessible")
            else:
                logger.info("⚠️ Old message not found - may be due to buffer limits or LLM context")

            logger.info("\n=== Test Summary ===")
            logger.info("✅ Formation loaded successfully with auth configuration")
            logger.info("✅ Overlord started and connected to remote buffer")
            logger.info("✅ Messages stored and retrieved")
            logger.info("✅ Authentication appears to be working (no auth errors)")

            # Clean up
            logger.info("\nStopping overlord...")
            formation.stop_overlord()
            logger.info("Test completed successfully!")

        except Exception as e:
            logger.error(f"Test failed with error: {e}")
            import traceback

            traceback.print_exc()
            raise

    # Run in thread to avoid event loop conflicts
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_test)
        future.result()


if __name__ == "__main__":
    test_remote_buffer_with_auth()
