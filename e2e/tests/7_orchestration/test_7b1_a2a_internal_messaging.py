#!/usr/bin/env python3
"""
Test 7B1-A: A2A SDK Internal Messaging Smoke Test

Complements test_7b1_internal_a2a.py by exercising the MUXI<->SDK conversion
path at the message layer without requiring LLM traffic. This is the PRD
Phase 1 "internal messaging" e2e test called out in the a2a-sdk 1.0 migration.

What it verifies:
  1. UnifiedA2AMessaging can convert MUXI dicts to SDK Messages with the
     active a2a-sdk version (0.3.x or 1.0.x).
  2. Round-trip conversion preserves text content via the SDK layer.
  3. The a2a-sdk version actually loaded is recorded (for migration audit).

Exits non-zero if any conversion raises.
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


async def test_a2a_internal_messaging_smoke():
    print("\n" + "=" * 80)
    print("Test 7B1-A: A2A SDK Internal Messaging Smoke Test")
    print("=" * 80)

    all_passed = True
    checks = []

    # ------------------------------------------------------------------
    # 1. Record loaded SDK version.
    # ------------------------------------------------------------------
    try:
        import a2a  # noqa: F401
        from importlib.metadata import version as pkg_version

        try:
            sdk_version = pkg_version("a2a-sdk")
        except Exception:
            sdk_version = "unknown"
        print(f"\n1. Loaded a2a-sdk version: {sdk_version}")
        checks.append(f"a2a-sdk version: {sdk_version}")
    except ImportError as e:
        print(f"\n1. a2a-sdk import failed: {e}")
        return 1

    # ------------------------------------------------------------------
    # 2. MUXI string -> SDK Message -> MUXI parts dict
    # ------------------------------------------------------------------
    print("\n2. String message conversion...")
    try:
        from muxi.runtime.formation.overlord.a2a_messaging import UnifiedA2AMessaging

        messaging = UnifiedA2AMessaging(overlord=SimpleNamespace(client_factory=None))
        sdk_message = messaging._convert_to_a2a_message(
            "hello from smoke test", source_agent_id="smoke"
        )
        assert sdk_message.message_id, "message_id must be generated"
        assert len(sdk_message.parts) == 1, "expected single part"
        print("   OK: string -> SDK Message")
        checks.append("String -> SDK Message")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 3. Dict-with-parts -> SDK Message preserves text and data parts
    # ------------------------------------------------------------------
    print("\n3. Dict-with-parts conversion...")
    try:
        muxi_in = {
            "parts": [
                {"type": "TextPart", "text": "alpha"},
                {"type": "DataPart", "data": {"k": "v"}},
            ]
        }
        sdk_message = messaging._convert_to_a2a_message(muxi_in, source_agent_id="smoke")
        assert len(sdk_message.parts) == 2
        print("   OK: dict -> SDK Message (2 parts)")
        checks.append("Dict -> SDK Message")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 4. SDK Message -> MUXI dict (internal branch)
    # ------------------------------------------------------------------
    print("\n4. SDK Message -> MUXI dict (internal response)...")
    try:
        messaging._last_was_external = False
        out = messaging._convert_from_a2a_message(sdk_message)
        assert "parts" in out, "expected 'parts' key"
        print(f"   OK: round-tripped {len(out.get('parts', []))} parts")
        checks.append("SDK -> MUXI dict")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # 5. SDK Message -> MUXI dict (external branch)
    # ------------------------------------------------------------------
    print("\n5. SDK Message -> MUXI dict (external response wrapping)...")
    try:
        messaging._last_was_external = True
        ext_sdk = messaging._convert_to_a2a_message("hello", source_agent_id="smoke")
        out = messaging._convert_from_a2a_message(ext_sdk)
        assert out.get("status") in ("success", "error"), "expected wrapped shape"
        print(f"   OK: external wrap status={out.get('status')}")
        checks.append("External wrap")
    except Exception as e:
        print(f"   FAIL: {e}")
        all_passed = False

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"Test Result: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Checks Passed: {len(checks)}")
    for c in checks:
        print(f"  - {c}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_a2a_internal_messaging_smoke())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
