#!/usr/bin/env python
"""Simple test for user3 credential storage."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent / "tests/e2e/8_clarification"))

from muxi.formation import Formation
from test_utils import TestContext


async def test_user3_simple():
    """Simple test: user3 provides token and it gets stored."""
    print("\n" + "="*50)
    print("TEST: User3 Simple Token Storage")
    print("="*50)

    # Load formation-dynamic.yaml
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

        # Clean up any existing credentials for user3
        print("Cleaning up existing credentials for user3...")
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        try:
            result = await conn.execute("DELETE FROM credentials WHERE user_id=6 AND service='github'")
            print(f"Deleted {result} credential records for user3")
        finally:
            await conn.close()
        print("Cleanup complete.")

        print("Starting overlord...")
        overlord = await formation.start_overlord()

        ctx = TestContext("user3_simple")
        user_id = "user3"
        print(f"Using User: {user_id}, Session: {ctx.session_id}")

        # Step 1: Ask to list repos
        print("\n1. User: Get my GitHub repositories")
        response1 = await overlord.chat(
            message="Get my GitHub repositories",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"   System: {response1.content}")

        # Step 2: Provide the token
        print("\n2. User: my github token is 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")
        response2 = await overlord.chat(
            message="my github token is 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"   System: {response2.content}")

        # Check if it says stored/validated AND lists repos
        response_lower = response2.content.lower()
        has_success = "success" in response_lower or "connected" in response_lower
        has_repos = "repositor" in response_lower or "profile" in response_lower or "github.com" in response_lower

        if has_success:
            print("\n✅ Token validated and stored!")

            if has_repos:
                print("✅ AND it continued with the original request (listing repos)!")
                print("\nFull response shows continuation working:")
                # Print first few lines to show it worked
                lines = response2.content.split('\n')
                for i, line in enumerate(lines[:5]):
                    print(f"   {line}")
                if len(lines) > 5:
                    print(f"   ... ({len(lines) - 5} more lines)")
            else:
                print("⚠️  But it didn't continue with the original request...")
                print("   The system should have listed the repositories after storing credentials.")
        else:
            print("\n❌ Token not stored - got unexpected response")
            print(f"   Response: {response2.content[:200]}...")

        print("="*50)

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        # Restore original
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test_user3_simple())
