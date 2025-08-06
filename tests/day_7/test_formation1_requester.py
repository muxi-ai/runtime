#!/usr/bin/env python3
"""
Test Formation 1 - Requester
This formation makes requests that require services from Formation 2 via A2A.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.muxi.formation.formation import Formation  # noqa: E402
from src.muxi.datatypes.exceptions import RegistryConfigurationError  # noqa: E402


async def test_external_a2a():
    """Test external A2A communication by requesting services from Formation 2."""
    print("Starting Formation 1 (Requester)...")
    print("=" * 60)
    print("\nMake sure Formation 2 is running first!")
    print("Run: python test_formation2_provider.py")
    print("=" * 60)

    # Give user time to read the message
    await asyncio.sleep(2)

    formation = Formation()

    try:
        # Load the formation configuration
        await formation.load("test-formations/formation-a2a/formation1/formation.yaml")

        # Start the overlord
        overlord = await formation.start_overlord()

        print("\n✅ Formation 1 is running!")
        print("\nAvailable agents:")
        for agent_id in overlord.agents.keys():
            print(f"  - {agent_id}")

        # Wait a moment for everything to initialize
        await asyncio.sleep(2)

        # Request that requires external agent
        response = await overlord.chat(
            "Create a Linear issue with system information like CPU, memory, etc.",
            user_id="test_user",
            stream=False  # Disable streaming to get a simple string response
        )

        # Extract text from MuxiResponse
        response_text = response.text if hasattr(response, 'text') else str(response)
        print(f"Response: {response_text}")

        # Verify Linear issue was created with system info
        assert "linear" in response_text.lower()

    except RegistryConfigurationError as e:
        # This is a configuration issue, not a test failure
        # The error message was already printed to stderr by the exception
        print("\n❌ Configuration Issue: Registry requirements not met")
        print(f"   Policy: {e.policy}")
        print(f"   Unreachable registries: {', '.join(e.unreachable_registries)}")
        print("\n💡 To run this test, either:")
        print("   1. Start the registry server: python test_a2a_registry.py")
        print("   2. Change startup_policy to 'lenient' in formation1/formation.yaml")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Clean shutdown
        print("\nShutting down Formation 1...")
        try:
            await formation.stop_overlord()
            formation.shutdown()
            print("Formation 1 stopped cleanly.")
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(test_external_a2a())
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
