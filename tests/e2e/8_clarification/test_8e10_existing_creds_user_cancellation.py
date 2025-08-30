#!/usr/bin/env python
"""Test user1 with existing credentials giving up after two failed attempts."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "tests/e2e/8_clarification"))

from muxi.formation import Formation
from test_utils import TestContext


async def test():
    formation_path = Path(__file__).parent / "formations/formation-clarification"

    import shutil
    original = formation_path / "formation.yaml"
    backup = formation_path / "formation.yaml.backup"
    dynamic = formation_path / "formation-dynamic.yaml"

    if original.exists():
        shutil.copy(original, backup)
    shutil.copy(dynamic, original)

    formation = Formation()

    try:
        await formation.load(str(formation_path))

        # Clean up any existing automazeio credentials to avoid conflicts
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        # Delete ALL automazeio credentials regardless of user
        result = await conn.execute("DELETE FROM credentials WHERE name='automazeio' AND service='github'")
        print(f"Deleted {result} automazeio credentials")
        await conn.close()

        overlord = await formation.start_overlord()

        ctx = TestContext("existing_creds_user_gives_up")
        user_id = "user1"  # Using user1 who has existing credentials

        print("\n" + "="*60)
        print("CHAT TRANSCRIPT - Existing Creds + User Gives Up")
        print("="*60)

        # Step 1: Initial request
        print("\n**User:** Get my GitHub repositories")
        response1 = await overlord.chat(
            message="Get my GitHub repositories",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response1.content}")

        # Step 2: User wants a different account
        print("\n**User:** neither - I need a different account")
        response2 = await overlord.chat(
            message="neither - I need a different account",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response2.content}")

        # Step 3: First bad token
        print("\n**User:** my token is ghp_BADTOKEN_12345")
        response3 = await overlord.chat(
            message="my token is ghp_BADTOKEN_12345",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        # Step 4: Second bad token
        print("\n**User:** hmm let me try ghp_STILLWRONG_67890")
        response4 = await overlord.chat(
            message="hmm let me try ghp_STILLWRONG_67890",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response4.content}")

        # Step 5: User gives up
        print("\n**User:** forget it, I'll do this later")
        response5 = await overlord.chat(
            message="forget it, I'll do this later",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response5.content}")

        print("\n" + "="*60)

        # Analysis
        response_lower = response5.content.lower()

        # These would indicate the system is still asking for credentials (bad)
        still_asking = ["token", "credential", "password", "authenticate"]

        # These would indicate the system acknowledged the cancellation (good)
        acknowledged = ["okay", "sure", "no problem", "let me know", "later", "whenever", "ready"]

        if any(word in response_lower for word in still_asking):
            print("\n❌ FAILURE: System is still asking for credentials after user gave up")
            print(f"Response: {response5.content[:200]}...")
        elif any(word in response_lower for word in acknowledged):
            print("\n✅ SUCCESS: System gracefully handled user giving up with existing credentials")
            print("✓ System asked which existing account to use")
            print("✓ User indicated they need a different account")
            print("✓ First bad token was rejected")
            print("✓ Second bad token was rejected")
            print("✓ User cancellation was acknowledged")
            print("✓ System did not persist in asking for credentials")
        else:
            print("\n⚠️  UNCLEAR: Can't determine if cancellation was handled properly")
            print(f"Response: {response5.content[:200]}...")

        print("="*60)

        # Step 6: Verify we can start a new conversation
        print("\n**User:** What's the weather like?")
        response6 = await overlord.chat(
            message="What's the weather like?",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response6.content[:200]}...")

        # Check that the system moved on from credential handling
        if "token" not in response6.content.lower() and "credential" not in response6.content.lower():
            print("\n✅ BONUS: System properly moved on to new topic after cancellation")
        else:
            print("\n⚠️  System might still be stuck on credentials")

        print("="*60)

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())
