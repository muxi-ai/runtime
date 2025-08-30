#!/usr/bin/env python
"""Test retry with transcript."""

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

        # Clean up any existing credentials
        import asyncpg
        conn = await asyncpg.connect('postgresql://ran@127.0.0.1/muxi_framework')
        await conn.execute("DELETE FROM credentials WHERE user_id=6 AND service='github'")
        await conn.close()

        overlord = await formation.start_overlord()

        ctx = TestContext("retry_transcript")
        user_id = "user3"

        print("\n" + "="*60)
        print("CHAT TRANSCRIPT - Retry Mechanism Test")
        print("="*60)

        print("\n**User:** Get my GitHub repositories")
        response1 = await overlord.chat(
            message="Get my GitHub repositories",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response1.content}")

        print("\n**User:** my token is ghp_BADTOKEN_12345")
        response2 = await overlord.chat(
            message="my token is ghp_BADTOKEN_12345",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response2.content}")

        print("\n**User:** oops wrong one, here's the real token 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")
        response3 = await overlord.chat(
            message="oops wrong one, here's the real token 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",
            user_id=user_id,
            session_id=ctx.session_id,
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        print("\n" + "="*60)

        # Analysis
        if "success" in response3.content.lower() or "connected" in response3.content.lower():
            print("\n✅ SUCCESS: Retry mechanism worked - good token accepted after bad token")
        else:
            print("\n❌ FAILURE: Good token was not accepted after bad token")

        await formation.stop_overlord()
        formation.shutdown()

    finally:
        if backup.exists():
            shutil.copy(backup, original)


if __name__ == "__main__":
    asyncio.run(test())
