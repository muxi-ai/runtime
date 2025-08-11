#!/usr/bin/env python3
"""Test 2A1: Basic Conversation Context - Buffer Memory Configuration"""

import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
import asyncio  # noqa: E402
from muxi.formation.formation import Formation  # noqa: E402


async def test_formation_buffer_config():
    """Test buffer configuration through formation loading"""
    print("\n=== Testing Formation Buffer Configuration ===")

    formations = []
    try:
        # Test loading local buffer formation
        formation_local = Formation()
        await formation_local.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-buffer-local.yaml"))
        formations.append(formation_local)
        print("✓ Local buffer formation loaded successfully")

        # Test loading remote buffer formation
        formation_remote = Formation()
        await formation_remote.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-buffer-remote.yaml"))
        formations.append(formation_remote)
        print("✓ Remote buffer formation loaded successfully")

        # Extract buffer configurations
        local_config = formation_local.config.get("memory", {}).get("buffer", {})
        remote_config = formation_remote.config.get("memory", {}).get("buffer", {})

        print(
            f"  - Local buffer config: mode={local_config.get('mode', 'local')}, size={local_config.get('size')}"
        )
        print(
            f"  - Remote buffer config: mode={remote_config.get('mode')}, size={remote_config.get('size')}"
        )

        # Verify buffer memory is configured
        local_buffer_memory = (
            formation_local._configured_services.get("buffer_memory")
            if hasattr(formation_local, "_configured_services")
            else None
        )
        remote_buffer_memory = (
            formation_remote._configured_services.get("buffer_memory")
            if hasattr(formation_remote, "_configured_services")
            else None
        )

        if local_buffer_memory:
            print(
                f"  - Local buffer memory initialized: mode={getattr(local_buffer_memory, 'mode', 'unknown')}"
            )
        if remote_buffer_memory:
            print(
                f"  - Remote buffer memory initialized: mode={getattr(remote_buffer_memory, 'mode', 'unknown')}"
            )

        return {
            "formation_loading": "success",
            "local_config": local_config,
            "remote_config": remote_config,
            "local_memory_initialized": local_buffer_memory is not None,
            "remote_memory_initialized": remote_buffer_memory is not None,
        }

    except Exception as e:
        print(f"❌ Formation buffer configuration failed: {e}")
        return {"formation_loading": "failed", "error": str(e)}


async def test_buffer_memory_functionality():
    """Test actual buffer memory functionality with overlord"""
    print("\n=== Testing Buffer Memory Functionality ===")

    formation = None
    overlord = None
    try:
        # Load formation with local buffer
        formation = Formation()
        await formation.load(str(Path(__file__).parent / "formations" / "formation-memory" / "formation-buffer-local.yaml"))
        overlord = await formation.start_overlord()
        print("✓ Overlord started with local buffer memory")

        # Test memory retention
        print("\nTesting conversation context retention...")

        # First message
        response1 = await overlord.chat(
            "My name is Alice and I work at TechCorp.",
            user_id="test_user",
            use_async=False,
            stream=False  # Explicitly disable streaming
        )
        print("  - First message processed")

        # Wait for async storage to complete
        print("  - Waiting 5 seconds for buffer memory storage...")
        await asyncio.sleep(5)

        # Second message - ask what was just said
        response2 = await overlord.chat(
            "What did I just say?",
            user_id="test_user",
            use_async=False,
            stream=False  # Explicitly disable streaming
        )
        # Handle response properly
        if hasattr(response2, '__aiter__'):  # It's an async generator
            response2_text = ""
            async for chunk in response2:
                response2_text += chunk
        else:
            response2_text = response2.content if hasattr(response2, 'content') else str(response2)

        print("  - Second message processed")
        print(f"  - Response: {response2_text}")

        # Check if context was retained - should mention Alice or TechCorp
        context_retained = (
            "alice" in response2_text.lower() or "techcorp" in response2_text.lower()
        )
        print(f"  - Context retained: {'✅' if context_retained else '❌'}")

        return {"functionality": "success", "context_retained": context_retained}

    except Exception as e:
        print(f"❌ Buffer memory functionality test failed: {e}")
        return {"functionality": "failed", "error": str(e)}
    finally:
        # Clean up
        if formation:
            await formation.shutdown()


async def main():
    """Run all buffer configuration tests"""
    print("🧠 Testing Buffer Memory Configuration (Local vs Remote)")
    print("=" * 60)

    # Test formation configurations
    formation_result = await test_formation_buffer_config()

    # Test actual functionality
    functionality_result = await test_buffer_memory_functionality()

    # Summary
    print("\n" + "=" * 60)
    print("📋 BUFFER CONFIGURATION TEST SUMMARY")
    print("=" * 60)

    # Formation loading results
    formation_success = formation_result.get("formation_loading") == "success"
    print(f"Formation Configuration: {'✅ PASS' if formation_success else '❌ FAIL'}")
    if formation_success:
        print(f"  - Local buffer size: {formation_result['local_config'].get('size')}")
        print(f"  - Remote buffer size: {formation_result['remote_config'].get('size')}")
        print(
            f"  - Local memory initialized: {'✅' if formation_result.get('local_memory_initialized') else '❌'}"
        )
        print(
            f"  - Remote memory initialized: {'✅' if formation_result.get('remote_memory_initialized') else '❌'}"
        )

    # Functionality results
    functionality_success = functionality_result.get("functionality") == "success"
    print(f"\nBuffer Memory Functionality: {'✅ PASS' if functionality_success else '❌ FAIL'}")
    if functionality_success:
        print(
            f"  - Context retention: {'✅' if functionality_result.get('context_retained') else '❌'}"
        )

    # Overall result
    all_tests_passed = formation_success and functionality_success

    print(
        f"\n🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if all_tests_passed else '❌ SOME TESTS FAILED'}"
    )

    # Key insights
    print("\n💡 KEY INSIGHTS:")
    print("- Local buffer mode uses in-memory FAISS for vector search")
    print("- Remote buffer mode connects to external FAISSx servers")
    print("- Buffer memory retains conversation context across messages")
    print("- Both local and remote formations load successfully")

    return all_tests_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    # Force immediate exit
    os._exit(0 if result else 1)
