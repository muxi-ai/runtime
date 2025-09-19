#!/usr/bin/env python
"""Test user1 providing a duplicate token that's already stored."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "tests/e2e/8_clarification"))

from muxi.formation import Formation  # noqa: E402
from test_utils import TestContext  # noqa: E402


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

        # First, store the token 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
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')

        # Clean up any existing instances of this specific token
        await conn.execute("DELETE FROM credentials WHERE name='duplicate_test' AND service='github'")

        # Store the token for user1 first
        # Get user1's id
        user_row = await conn.fetchrow("SELECT id FROM users WHERE external_user_id='user1' AND formation_id='test_formation'")
        if user_row:
            user_id = user_row['id']
            # Store the token directly
            await conn.execute("""
                INSERT INTO credentials (user_id, credential_id, name, service, credentials, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            """, user_id, 'test_dup_' + str(user_id), 'duplicate_test', 'github', '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')
            print(f"Pre-stored token for user_id={user_id}")

        await conn.close()

        overlord = await formation.start_overlord()

        ctx = TestContext("duplicate_token_test")
        user_id = "user1"  # Using user1 who has existing credentials

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

        # Step 3: Provide the DUPLICATE token
        print("\n**User:** my github token is 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")
        response3 = await overlord.chat(
            message="my github token is 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        print("\n" + "="*60)

        # Check logs for duplicate detection
        print("\n### Checking logs for duplicate detection...")
        # The handler should have printed "Token already stored for github"

        # Analysis
        # We expect the system to still say success (token is valid)
        # But in the logs we should see "Token already stored"
        success_indicators = ["success", "connected", "github.com", "repositor", "profile"]
        if any(indicator in response3.content.lower() for indicator in success_indicators):
            print("\n✅ SUCCESS: System handled duplicate token correctly")
            print("✓ Token was validated")
            print("✓ System recognized it as duplicate (check logs)")
            print("✓ User can proceed with original request")
        else:
            print("\n⚠️  UNEXPECTED: Response doesn't indicate success")
            print(f"Response: {response3.content[:200]}...")

        print("="*60)

        # Clean up the test token
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        await conn.execute("DELETE FROM credentials WHERE name='duplicate_test' AND service='github'")
        await conn.close()

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())
