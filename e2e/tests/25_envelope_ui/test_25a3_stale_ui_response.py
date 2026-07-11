#!/usr/bin/env python3
"""
Test 25A3: Response Envelope UI - stale/unknown ui_response id

Verifies the stateless reply-path contract: a ui_response whose id does
not match any clarification-produced widget in this conversation is
ignored — the message stands alone and is processed normally.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def main() -> int:
    print("MUXI Runtime - Test 25A3: stale/unknown ui_response id ignored")
    print("=" * 70)

    formation_path = Path(__file__).parent / "formations" / "formation-envelope"
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    await asyncio.sleep(2)

    try:
        print("\n[1] Sending a normal question with a stale ui_response hint...")
        response = await overlord.chat(
            message="What is 2+2? Reply with just the number.",
            user_id="stale-user",
            session_id="sess-25a3",
            stream=False,
            ui_response={"id": "ui_does_not_exist", "value": "acme-dev"},
        )
        content = response.content if hasattr(response, "content") else str(response)
        print(f"    Response: {content[:200]}")

        assert content and content.strip(), "Message must be processed normally"
        assert "4" in content, f"Expected the question answered normally, got: {content[:200]}"
        print("    Message processed normally; stale hint ignored")

        print("\n" + "=" * 70)
        print("SUCCESS: unknown ui_response id ignored, message stood alone")
        return 0

    finally:
        try:
            await formation.stop_overlord()
            formation.stop()
        except Exception:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
