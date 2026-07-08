#!/usr/bin/env python3
"""
Test 23A4: Slash commands (SOPs as commands) and overlord soul loading

Verifies against a live formation:
1. /ping resolves to the sops/ping.md SOP and the agent executes its
   content (deterministic PONG-E2E reply)
2. /hb (alias) resolves to the heartbeat-e2e SOP via commands.aliases
3. An unknown command returns immediately with a helpful message and
   the available command list (no LLM round-trip)
4. The SOUL.md next to formation.yaml is auto-discovered and becomes
   the overlord's default persona (SOUL.md > soul.md > inline
   overlord.soul > built-in default)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


def _content(response):
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


async def main():
    print("MUXI Runtime - Test 23A4: Slash Commands and Overlord Soul")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-proactive"

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print(f"Formation loaded: {formation.formation_id}")

        # 1. SOP as a slash command
        print("\nSending: /ping")
        response = await overlord.chat(
            message="/ping",
            user_id="command-user",
            session_id="cmd-session-1",
            use_async=False,
            stream=False,
        )
        ping_reply = _content(response)
        print(f"Reply: {ping_reply[:80]}")
        assert "PONG-E2E" in ping_reply, f"SOP command not executed: {ping_reply}"
        print("Slash command executed the ping SOP")

        # 2. Alias resolution
        print("\nSending: /hb (alias for heartbeat-e2e)")
        response = await overlord.chat(
            message="/hb",
            user_id="command-user",
            session_id="cmd-session-2",
            use_async=False,
            stream=False,
        )
        hb_reply = _content(response)
        print(f"Reply: {hb_reply[:80]}")
        assert "E2E-HEARTBEAT-PING" in hb_reply, f"Alias not resolved: {hb_reply}"
        print("Alias resolved to the heartbeat SOP")

        # 3. Unknown command short-circuits without an LLM call
        print("\nSending: /does-not-exist")
        response = await overlord.chat(
            message="/does-not-exist",
            user_id="command-user",
            session_id="cmd-session-3",
            use_async=False,
            stream=False,
        )
        unknown_reply = _content(response)
        print(f"Reply: {unknown_reply[:120]}")
        assert "Unknown command: /does-not-exist" in unknown_reply, unknown_reply
        assert "/ping" in unknown_reply, f"Available commands not listed: {unknown_reply}"
        print("Unknown command returned the available command list")

        # 4. Overlord soul auto-discovery (SOUL.md next to formation.yaml)
        persona = overlord._default_persona
        assert persona, "Overlord default persona not loaded"
        assert persona.startswith(
            "# Soul"
        ), f"SOUL.md not auto-discovered as the overlord persona: {persona[:80]}"
        assert "Determinism over creativity" in persona
        # SOUL.md wins over the built-in default, and agents stay
        # single-file contained: no soul content in the agent's system message
        agent = overlord.agents.get("assistant") or next(iter(overlord.agents.values()))
        assert "Determinism over creativity" not in agent.system_message
        print("\nSOUL.md auto-discovered as the overlord default persona")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Slash commands and overlord soul work end-to-end")
        print("  - /ping executed its SOP content")
        print("  - commands.aliases mapped /hb to the heartbeat SOP")
        print("  - Unknown commands short-circuit with available commands")
        print("  - SOUL.md next to formation.yaml feeds the overlord persona")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\nUser: /ping")
        print(f"System: {ping_reply}")
        print("\nUser: /does-not-exist")
        print(f"System: {unknown_reply}")

        print("\nTest 23A4 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if "formation" in locals():
            try:
                await formation.stop_overlord()
            except Exception:
                pass
        await asyncio.sleep(1)


if __name__ == "__main__":
    success = asyncio.run(main())
    import os

    os._exit(0 if success else 1)
