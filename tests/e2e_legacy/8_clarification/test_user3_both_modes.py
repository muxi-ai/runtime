#!/usr/bin/env python
"""Test user3 (no credentials) with both redirect and dynamic modes."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


async def test_user3_redirect():
    """Test user3 with redirect mode."""
    print("\n" + "="*50)
    print("TEST 1: User3 with REDIRECT mode")
    print("="*50)

    formation_path = Path(__file__).parent / "formations" / "formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))

    overlord = await formation.start_overlord()
    ctx = TestContext("user3_redirect")
    user_id = "user3"

    print("\nUser: Get my GitHub repositories")
    response1 = await asyncio.wait_for(
        overlord.chat(
            message="Get my GitHub repositories",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        ),
        timeout=30.0
    )
    print(f"System: {response1.content}")

    await formation.stop_overlord()
    formation.shutdown()

    return response1.content


async def test_user3_dynamic():
    """Test user3 with dynamic mode."""
    print("\n" + "="*50)
    print("TEST 2: User3 with DYNAMIC mode")
    print("="*50)

    # Use formation-dynamic.yaml by loading it directly
    formation_path = Path(__file__).parent / "formations" / "formation-clarification"

    # Create new formation with dynamic config
    formation = Formation()

    # Load with dynamic config
    import shutil
    original = formation_path / "formation.yaml"
    backup = formation_path / "formation.yaml.backup"
    dynamic = formation_path / "formation-dynamic.yaml"

    # Backup and replace
    shutil.copy(original, backup)
    shutil.copy(dynamic, original)

    try:
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        ctx = TestContext("user3_dynamic")
        user_id = "user3"

        print("\nUser: Get my GitHub repositories")
        response1 = await asyncio.wait_for(
            overlord.chat(
                message="Get my GitHub repositories",
                user_id=user_id,
                session_id=ctx.session_id,
                stream=False
            ),
            timeout=30.0
        )
        print(f"System: {response1.content}")

        # If it prompts for token, provide one
        if "provide" in response1.content.lower() or "bearer" in response1.content.lower():
            print("\nUser: ghp_test_token_12345")
            response2 = await asyncio.wait_for(
                overlord.chat(
                    message="ghp_test_token_12345",
                    user_id=user_id,
                    session_id=ctx.session_id,
                    stream=False
                ),
                timeout=30.0
            )
            print(f"System: {response2.content}")

        await formation.stop_overlord()
        formation.shutdown()

        return response1.content

    finally:
        # Restore original
        shutil.copy(backup, original)


async def main():
    """Run both tests."""
    # Test redirect mode
    redirect_response = await test_user3_redirect()

    # Test dynamic mode
    dynamic_response = await test_user3_dynamic()

    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)

    # Check redirect mode
    if "configure" in redirect_response.lower() and "credential" in redirect_response.lower():
        print("✅ Redirect mode: Shows redirect message for user3")
    else:
        print("❌ Redirect mode: Did not show redirect message")

    # Check dynamic mode
    if "provide" in dynamic_response.lower() or "bearer" in dynamic_response.lower():
        print("✅ Dynamic mode: Prompts for inline credential entry for user3")
    elif "configure" in dynamic_response.lower():
        print("⚠️ Dynamic mode: Fell back to redirect (check accept_inline)")
    else:
        print("❌ Dynamic mode: Unexpected response")

    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
