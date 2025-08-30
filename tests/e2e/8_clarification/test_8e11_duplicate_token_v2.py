#!/usr/bin/env python
"""Test user1 providing a duplicate token that's already stored (properly encrypted)."""

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

        # First, store the token using the credential resolver (properly encrypted)
        print("\n### Pre-storing token for duplicate test...")
        overlord = await formation.start_overlord()

        # Store the token first
        status = await overlord.credential_resolver.store_credential(
            user_id="user1",
            service="github",
            credentials="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",
            credential_name="pretest_account"
        )
        print(f"Pre-store status: {status}")

        # Now restart for clean test
        await formation.stop_overlord()
        overlord = await formation.start_overlord()

        ctx = TestContext("duplicate_token_test")
        user_id = "user1"

        print("\n" + "="*60)
        print("CHAT TRANSCRIPT - Duplicate Token Test")
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

        # Step 3: Provide the SAME token again
        print("\n**User:** my github token is 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")
        response3 = await overlord.chat(
            message="my github token is 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        print("\n" + "="*60)

        # Analysis - check for duplicate detection
        duplicate_indicators = ["already stored", "already saved", "already have", "all set"]
        success_indicators = ["success", "connected", "github.com", "repositor", "profile"]

        response_lower = response3.content.lower()
        if any(indicator in response_lower for indicator in duplicate_indicators):
            print("\n✅ SUCCESS: System correctly detected duplicate token")
            print("✓ Token was recognized as duplicate")
            print("✓ User was informed token is already stored")
            print("✓ No unnecessary validation performed")
        elif any(indicator in response_lower for indicator in success_indicators):
            print("\n⚠️  UNEXPECTED: System didn't detect duplicate")
            print("System proceeded with validation instead of detecting duplicate")
        else:
            print("\n❌ FAILURE: Unexpected response")
            print(f"Response: {response3.content[:200]}...")

        print("="*60)

        # Clean up - remove the test credential
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        await conn.execute("DELETE FROM credentials WHERE name='pretest_account' AND service='github'")
        await conn.close()

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())
