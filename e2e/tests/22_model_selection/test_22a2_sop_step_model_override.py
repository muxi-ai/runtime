#!/usr/bin/env python3
"""Test 22a2: SOP step-level model override ([model:x] directive).

Verifies that an SOP step declaring [model:premium] (alias defined in
llm.aliases) routes that step's LLM call to the aliased model while other
steps stay on the agent's default model. Proven three ways:

1. Parsing: the decomposed workflow tasks carry the expected model refs.
2. Resolution: a MODEL_OVERRIDE_APPLIED event fires for the overridden step.
3. Behavior: MODEL_REQUEST_COMPLETED events include the override model.
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
OVERRIDE_ALIAS = "premium"
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


async def main():
    print("MUXI Runtime - Test 22a2: SOP Step-Level Model Override")
    print("=" * 60)

    formation = None
    checks = []
    transcript = []

    try:
        # 1. Load formation with the model-override SOP
        print("\n1. Loading formation with model-override SOP...")
        formation_path = Path(__file__).parent / "formation-sop-override"
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        checks.append("Formation loaded")

        # 2. Verify the SOP loaded with its step directive intact
        print("\n2. Verifying SOP loaded...")
        sop_system = getattr(overlord, "sop_system", None)
        assert sop_system is not None, "SOP system not available"
        sop_ids = list(sop_system.sops.keys())
        assert "model-override-test" in sop_ids, f"Expected 'model-override-test' in {sop_ids}"
        assert (
            "[model:premium]" in sop_system.sops["model-override-test"]["content"]
        ), "SOP content should retain the [model:premium] step directive"
        checks.append("SOP 'model-override-test' loaded with [model:premium] directive")

        # 3. Verify the deterministic parser assigns the step model
        print("\n3. Verifying decomposer assigns step-level model...")
        sop_content = sop_system.sops["model-override-test"]["content"]
        workflow = overlord.task_decomposer._parse_template_sop_deterministic(
            sop_content, "Execute the model-override-test SOP"
        )
        assert workflow is not None, "Deterministic SOP parsing failed"
        task_models = {tid: task.model for tid, task in sorted(workflow.tasks.items())}
        print(f"   Task models: {task_models}")
        assert task_models.get("task_1") is None, "Step 1 must not carry a model override"
        assert (
            task_models.get("task_2") == OVERRIDE_ALIAS
        ), f"Step 2 must carry the '{OVERRIDE_ALIAS}' override, got {task_models.get('task_2')}"
        checks.append("Step 2 carries [model:premium]; step 1 has no override")

        # 4. Execute the SOP end to end and capture events
        print("\n4. Executing SOP via overlord.chat()...")
        capturing = CapturingLogger()
        observability.set_runtime_event_logger(capturing)

        message = "Execute the model-override-test SOP"
        response = await asyncio.wait_for(
            overlord.chat(
                message,
                user_id="test_user",
                session_id="model_override_22a2",
                use_async=False,
                stream=False,
            ),
            timeout=240,
        )
        content = response.content if hasattr(response, "content") else str(response)
        print(f"   Response: {content[:300]}")
        transcript.append((message, content[:300]))
        assert content and len(content.strip()) > 0, "Empty response from SOP execution"
        checks.append("SOP executed with a real response")

        # Give the background observe() thread time to drain
        await asyncio.sleep(1.5)
        events = capturing.snapshot()

        # 5. Verify the override was resolved and applied
        print("\n5. Verifying MODEL_OVERRIDE_APPLIED event...")
        override_events = [e for e in events if e["event"] == "model.override.applied"]
        print(f"   Override events: {[e['data'] for e in override_events]}")
        assert override_events, "No MODEL_OVERRIDE_APPLIED event was emitted"
        matching = [
            e
            for e in override_events
            if e["data"].get("model_ref") == OVERRIDE_ALIAS
            and e["data"].get("resolved_model") == OVERRIDE_MODEL
        ]
        assert matching, (
            f"Expected override event for alias '{OVERRIDE_ALIAS}' -> {OVERRIDE_MODEL}; "
            f"got {[e['data'] for e in override_events]}"
        )
        checks.append(f"MODEL_OVERRIDE_APPLIED: {OVERRIDE_ALIAS} -> {OVERRIDE_MODEL}")

        # 6. Verify the override model actually served a request
        print("\n6. Verifying MODEL_REQUEST_COMPLETED events...")
        used_models = {
            e["data"].get("model")
            for e in events
            if e["event"] == "model.request.completed" and e["data"].get("model")
        }
        print(f"   Models seen in events: {sorted(used_models)}")
        assert (
            OVERRIDE_MODEL in used_models
        ), f"Expected a completed LLM call on {OVERRIDE_MODEL}; saw {used_models}"
        assert (
            DEFAULT_MODEL in used_models
        ), f"Expected the non-overridden step to run on {DEFAULT_MODEL}; saw {used_models}"
        checks.append(f"MODEL_REQUEST_COMPLETED observed for {OVERRIDE_MODEL}")
        checks.append(f"Non-overridden work stayed on {DEFAULT_MODEL}")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: SOP step-level [model:x] override routes to the aliased model")
        for check in checks:
            print(f"  - {check}")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:\n")
        for user_msg, system_msg in transcript:
            print(f"User: {user_msg}")
            print(f"System: {system_msg}")
        return True

    except Exception as e:
        print(f"\nFAILED: Test 22a2 failed: {e}")
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
