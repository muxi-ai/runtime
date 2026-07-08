#!/usr/bin/env python3
"""Test 22a1: Agent-level model override (llm_models).

Verifies that an agent with ``llm_models: [{text: openai/gpt-4.1-mini}]``
actually routes its LLM calls to that model while a sibling agent keeps the
formation default (openai/gpt-4o-mini). Routing is proven two ways:

1. Wiring: the agents' LLM instances carry the expected model names.
2. Behavior: a real chat through the overriding agent emits a
   MODEL_REQUEST_COMPLETED event for the override model.
"""

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402
from muxi.runtime.services import observability  # noqa: E402

DEFAULT_MODEL = "openai/gpt-4o-mini"
OVERRIDE_MODEL = "openai/gpt-4.1-mini"


class CapturingLogger:
    """Drop-in event sink that records the events observe() emits."""

    def __init__(self):
        self._events = []
        self._lock = threading.Lock()

    def should_emit(self, event_type, level):
        """Capture everything (observe() consults this before emitting)."""
        return True

    def emit_event(
        self,
        event_type=None,
        level=None,
        data=None,
        description=None,
        request_context=None,
        **kwargs,
    ):
        with self._lock:
            self._events.append(
                {
                    "event": getattr(event_type, "value", str(event_type)),
                    "data": data or {},
                }
            )
        return ""

    def snapshot(self):
        with self._lock:
            return list(self._events)


def models_from_events(events):
    """Extract model names from MODEL_REQUEST_COMPLETED events."""
    return {
        e["data"].get("model")
        for e in events
        if e["event"] == "model.request.completed" and e["data"].get("model")
    }


async def main():
    print("MUXI Runtime - Test 22a1: Agent-Level Model Override")
    print("=" * 60)

    formation = None
    checks = []
    transcript = []

    try:
        # 1. Load formation with a default agent and an overriding agent
        print("\n1. Loading formation with agent-level llm_models override...")
        formation_path = Path(__file__).parent / "formation-agent-override"
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        checks.append("Formation loaded")

        # 2. Verify wiring: each agent carries the expected model
        print("\n2. Verifying agent model wiring...")
        default_agent = overlord.agents.get("default-agent")
        specialist_agent = overlord.agents.get("specialist-agent")
        assert default_agent is not None, "default-agent not loaded"
        assert specialist_agent is not None, "specialist-agent not loaded"

        default_model = getattr(default_agent.model, "model_name", None)
        specialist_model = getattr(specialist_agent.model, "model_name", None)
        print(f"   default-agent model: {default_model}")
        print(f"   specialist-agent model: {specialist_model}")
        assert (
            default_model == DEFAULT_MODEL
        ), f"default-agent should use {DEFAULT_MODEL}, got {default_model}"
        assert (
            specialist_model == OVERRIDE_MODEL
        ), f"specialist-agent should use {OVERRIDE_MODEL}, got {specialist_model}"
        checks.append(f"specialist-agent wired to {OVERRIDE_MODEL}")
        checks.append(f"default-agent keeps formation default {DEFAULT_MODEL}")

        # 3. Send a message through the overriding agent and capture model
        # events. process_message is the exact call the overlord makes when a
        # request reaches an agent; driving it directly keeps the test
        # deterministic (overlord.chat may answer trivial greetings via a
        # pre-agent conversational fast path that never reaches the agent).
        print("\n3. Chatting via specialist-agent (real LLM call)...")
        capturing = CapturingLogger()
        observability.set_runtime_event_logger(capturing)

        message = "Say hello in one short sentence."
        response = await asyncio.wait_for(
            specialist_agent.process_message(
                message,
                user_id="test_user",
                session_id="model_override_22a1",
            ),
            timeout=120,
        )
        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:200]}")
        transcript.append((message, content[:200]))
        assert content and len(content.strip()) > 0, "Empty response from specialist-agent"
        checks.append("Got real response through the override model")

        # Give the background observe() thread time to drain
        await asyncio.sleep(1.5)

        # 4. Verify the override model actually served the request
        print("\n4. Verifying MODEL_REQUEST_COMPLETED events...")
        used_models = models_from_events(capturing.snapshot())
        print(f"   Models seen in events: {sorted(m for m in used_models if m)}")
        assert (
            OVERRIDE_MODEL in used_models
        ), f"Expected a completed LLM call on {OVERRIDE_MODEL}; saw {used_models}"
        checks.append(f"MODEL_REQUEST_COMPLETED observed for {OVERRIDE_MODEL}")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: Agent-level model override routes to the configured model")
        for check in checks:
            print(f"  - {check}")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:\n")
        for user_msg, system_msg in transcript:
            print(f"User: {user_msg}")
            print(f"System: {system_msg}")
        return True

    except Exception as e:
        print(f"\nFAILED: Test 22a1 failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        if formation is not None:
            try:
                await asyncio.wait_for(formation.stop_overlord(), timeout=5.0)
            except Exception:
                pass
            try:
                formation.stop()
            except Exception:
                pass
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    start = time.time()
    success = asyncio.run(main())
    print(f"\nDuration: {time.time() - start:.1f}s")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
