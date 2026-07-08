#!/usr/bin/env python3
"""
Test 23A6: Built-in slash commands (Proactiveness Phase 3)

Verifies against a live formation (real Postgres, real scheduler) that
the built-in commands are deterministic -- every reply below comes back
without an LLM round-trip:

1. /help lists built-ins, formation SOP commands, and aliases
2. /channels lists the formation's declared channels; default <name>
   writes the user's preference and /preferences reads it back
3. /preferences timezone <tz> round-trips through the UserChannelStore
4. /jobs lists/pauses/resumes/cancels a real scheduled job (created via
   the scheduler service) scoped to the calling user
5. /status shows the user context overview
6. /setup runs its deterministic multi-step flow (plain replies are
   intercepted while the flow is active)
7. /identity links and unlinks an identifier for the calling user
8. /reset reports deterministically when there is no history to clear
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


def _content(response):
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


async def main():
    print("MUXI Runtime - Test 23A6: Built-in Slash Commands")
    print("=" * 60)

    formation_path = Path(__file__).parent / "formation-proactive"
    # Fresh user per run: channel/identity state persists in Postgres
    user_id = f"cmd3-{uuid.uuid4().hex[:8]}"
    transcript = []

    try:
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print(f"Formation loaded: {formation.formation_id}")
        print(f"Test user: {user_id}")

        async def send(message, session_id="cmd3-session-1"):
            response = await overlord.chat(
                message=message,
                user_id=user_id,
                session_id=session_id,
                use_async=False,
                stream=False,
            )
            reply = _content(response)
            transcript.append((message, reply))
            return reply

        # 1. /help
        print("\nSending: /help")
        reply = await send("/help")
        for expected in ("/setup", "/jobs", "/channels", "/preferences", "/status", "/reset"):
            assert expected in reply, f"/help missing {expected}: {reply}"
        assert "/ping" in reply, f"/help missing formation SOP command: {reply}"
        assert "/hb -> /heartbeat-e2e" in reply, f"/help missing alias: {reply}"
        print("/help lists built-ins, formation commands, and aliases")

        # 2. /channels list + default
        print("\nSending: /channels")
        reply = await send("/channels")
        assert "chan-a" in reply and "chan-b" in reply, f"channels not listed: {reply}"

        print("Sending: /channels default chan-b")
        reply = await send("/channels default chan-b")
        assert "set to chan-b" in reply, f"default not set: {reply}"

        reply = await send("/channels")
        assert "chan-b (default)" in reply, f"default not shown: {reply}"
        print("/channels set and read back the default channel")

        # 3. /preferences timezone round-trip
        print("\nSending: /preferences timezone Europe/London")
        reply = await send("/preferences timezone Europe/London")
        assert "Timezone set to Europe/London" in reply, reply

        reply = await send("/preferences")
        assert "Notification channel: chan-b" in reply, f"preference not read back: {reply}"
        assert "Timezone: Europe/London" in reply, f"timezone not read back: {reply}"
        print("/preferences wrote and read back channel + timezone")

        # 4. /jobs against the real scheduler
        print("\nSending: /jobs (empty)")
        reply = await send("/jobs")
        assert "no scheduled tasks" in reply, f"expected empty job list: {reply}"

        # Create via the job manager directly (deterministic cron, no LLM
        # schedule parsing) -- the command layer under test is the same.
        job_id = await overlord.scheduler_service.job_manager.create_job(
            user_id=user_id,
            title="E2E builtin-commands job",
            original_prompt="Say E2E-JOB-PING",
            execution_prompt="Say E2E-JOB-PING",
            cron_expression="0 5 * * *",
            scheduled_for=None,
            is_recurring=True,
            exclusion_rules=[],
        )
        print(f"Created scheduled job: {job_id}")

        reply = await send("/jobs")
        assert "E2E builtin-commands job" in reply, f"job not listed: {reply}"
        assert job_id in reply, f"job id not shown: {reply}"

        reply = await send("/jobs pause 1")
        assert "Paused" in reply, f"pause failed: {reply}"
        reply = await send("/jobs")
        assert "PAUSED" in reply, f"paused status not shown: {reply}"

        reply = await send(f"/jobs resume {job_id}")
        assert "Resumed" in reply, f"resume failed: {reply}"

        reply = await send("/jobs cancel 1")
        assert "Cancelled" in reply, f"cancel failed: {reply}"
        reply = await send("/jobs")
        assert "no scheduled tasks" in reply, f"job not cancelled: {reply}"
        print("/jobs listed, paused, resumed, and cancelled a real job")

        # 5. /status
        print("\nSending: /status")
        reply = await send("/status")
        assert "Formation: formation-proactive-test" in reply, reply
        assert "Preferred channel: chan-b" in reply, reply
        assert "Scheduled tasks: 0 active" in reply, reply
        print("/status shows the user context overview")

        # 6. /setup deterministic flow (plain replies intercepted)
        print("\nSending: /setup")
        reply = await send("/setup")
        assert "Available channels: chan-a, chan-b" in reply, reply

        reply = await send("chan-a")
        assert "Notifications will go to chan-a" in reply, reply
        assert "timezone" in reply.lower(), reply

        reply = await send("skip")
        assert "You're all set" in reply, reply
        assert "chan-a" in reply, reply

        reply = await send("/preferences")
        assert "Notification channel: chan-a" in reply, reply
        assert "Timezone: Europe/London" in reply, reply  # skip left it untouched
        print("/setup flow updated the channel and preserved the timezone")

        # 7. /identity link + unlink (formation is multi-user / Postgres)
        linked = f"tg-{uuid.uuid4().hex[:8]}"
        print(f"\nSending: /identity link {linked} telegram")
        reply = await send(f"/identity link {linked} telegram")
        assert f"Linked {linked} (telegram)" in reply, reply

        reply = await send("/identity")
        assert f"{user_id} (current)" in reply, reply
        assert f"{linked} (telegram)" in reply, reply

        reply = await send(f"/identity unlink {linked}")
        assert f"Unlinked {linked}" in reply, reply
        print("/identity linked and unlinked an identifier")

        # 8. /reset (command turns are not buffered, so deterministic reply)
        print("\nSending: /reset")
        reply = await send("/reset")
        assert "no conversation history" in reply.lower() or "cleared" in reply.lower(), reply
        print("/reset replied deterministically")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Built-in slash commands work end-to-end")
        print("  - /help listed built-ins, SOP commands, and aliases")
        print("  - /channels + /preferences set and read back user state")
        print("  - /jobs managed a real scheduled job (list/pause/resume/cancel)")
        print("  - /status, /setup flow, /identity, /reset all deterministic")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for message, reply in transcript:
            print(f"\nUser: {message}")
            print(f"System: {reply}")

        print("\nTest 23A6 PASSED")
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
