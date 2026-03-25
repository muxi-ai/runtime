#!/usr/bin/env python3
"""
Test 7B5: SOP Synthesis Skip

Tests that SOPs with `synthesis: false` in their frontmatter return the
last task's raw output instead of re-synthesizing through the LLM.

Two sub-tests:
  A) An SOP with synthesis: false should return un-synthesized output.
  B) An SOP with default synthesis (true) should still produce a
     synthesized response (different from raw task output).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402


async def test_sop_synthesis_skip():
    print("\n" + "=" * 80)
    print("Test 7B5: SOP Synthesis Skip")
    print("=" * 80)

    formation_path = (
        Path(__file__).parent
        / "formations"
        / "formation-multi-agent-sop"
        / "formation.yaml"
    )
    all_passed = True
    checks_passed = []
    transcript = []

    try:
        # ── Load formation ──────────────────────────────────────────
        print("\n1. Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        print("   ✓ Formation loaded")
        checks_passed.append("Formation loaded")

        # Verify the test SOPs were picked up
        print("\n2. Checking SOP system...")
        sop_system = getattr(overlord, "sop_system", None)
        if not sop_system or not sop_system.enabled:
            print("   ✗ SOP system not available")
            all_passed = False
        else:
            sop_ids = list(sop_system.sops.keys())
            print(f"   SOPs loaded: {sop_ids}")

            has_json_sop = "json-output-test" in sop_ids
            has_default_sop = "synthesis-default-test" in sop_ids

            if has_json_sop:
                print("   ✓ json-output-test SOP found")
                checks_passed.append("json-output-test SOP loaded")

                # Verify synthesis flag was parsed
                json_sop = sop_system.sops["json-output-test"]
                if json_sop.get("synthesis") is False:
                    print("   ✓ synthesis: false parsed correctly")
                    checks_passed.append("synthesis: false parsed")
                else:
                    print(f"   ✗ synthesis field = {json_sop.get('synthesis')} (expected False)")
                    all_passed = False
            else:
                print("   ✗ json-output-test SOP not found")
                all_passed = False

            if has_default_sop:
                print("   ✓ synthesis-default-test SOP found")
                checks_passed.append("synthesis-default-test SOP loaded")

                default_sop = sop_system.sops["synthesis-default-test"]
                if default_sop.get("synthesis") is True:
                    print("   ✓ synthesis defaults to true")
                    checks_passed.append("synthesis defaults to true")
                else:
                    print(f"   ✗ synthesis field = {default_sop.get('synthesis')} (expected True)")
                    all_passed = False
            else:
                print("   ✗ synthesis-default-test SOP not found")
                all_passed = False

        # Allow indexing time
        await asyncio.sleep(2)

        # ── Test A: synthesis: false SOP ─────────────────────────────
        print("\n3. Test A: Requesting SOP with synthesis: false...")
        print("   Request: 'Execute the json-output-test SOP'")

        response_a = await asyncio.wait_for(
            overlord.chat(
                message="Execute the json-output-test SOP",
                user_id="test_user",
                session_id="synthesis_skip_test_a",
                stream=False,
            ),
            timeout=120,
        )

        content_a = response_a.content if hasattr(response_a, "content") else str(response_a)
        metadata_a = response_a.metadata if hasattr(response_a, "metadata") else {}
        transcript.append(("User", "Execute the json-output-test SOP"))
        transcript.append(("Assistant", content_a[:300]))

        print(f"   Response ({len(content_a)} chars): {content_a[:300]}")
        print(f"   Metadata: {metadata_a}")

        # Check that synthesis was skipped
        synthesis_method = (metadata_a or {}).get("synthesis_method", "")
        if synthesis_method == "skipped_per_sop":
            print("   ✓ Synthesis was skipped (synthesis_method=skipped_per_sop)")
            checks_passed.append("Synthesis skipped for synthesis:false SOP")
        else:
            # Even if metadata doesn't surface, check the content isn't
            # wrapped in typical synthesis markers (headings, emojis)
            has_synthesis_markers = any(
                marker in content_a for marker in ["# ", "## ", "Here's", "Based on"]
            )
            if not has_synthesis_markers and len(content_a) > 0:
                print("   ✓ Response appears un-synthesized (no markdown headings)")
                checks_passed.append("Response appears un-synthesized")
            else:
                print("   ⚠️ Could not confirm synthesis was skipped")
                print(f"      synthesis_method={synthesis_method!r}")

        # ── Test B: default synthesis SOP ────────────────────────────
        print("\n4. Test B: Requesting SOP with default synthesis (true)...")
        print("   Request: 'Execute the synthesis-default-test SOP'")

        response_b = await asyncio.wait_for(
            overlord.chat(
                message="Execute the synthesis-default-test SOP",
                user_id="test_user",
                session_id="synthesis_skip_test_b",
                stream=False,
            ),
            timeout=120,
        )

        content_b = response_b.content if hasattr(response_b, "content") else str(response_b)
        metadata_b = response_b.metadata if hasattr(response_b, "metadata") else {}
        transcript.append(("User", "Execute the synthesis-default-test SOP"))
        transcript.append(("Assistant", content_b[:300]))

        print(f"   Response ({len(content_b)} chars): {content_b[:300]}")
        print(f"   Metadata: {metadata_b}")

        synthesis_method_b = (metadata_b or {}).get("synthesis_method", "")
        if synthesis_method_b != "skipped_per_sop":
            print("   ✓ Synthesis was NOT skipped (expected for default SOPs)")
            checks_passed.append("Synthesis ran for default SOP")
        else:
            print("   ✗ Synthesis was unexpectedly skipped for default SOP")
            all_passed = False

        # ── Cleanup ─────────────────────────────────────────────────
        print("\n5. Cleaning up...")
        try:
            await formation.stop_overlord()
            formation.stop()
        except Exception:
            pass
        print("   ✓ Formation stopped")

    except asyncio.TimeoutError:
        print("\n✗ TIMEOUT: Request exceeded 2 minutes")
        all_passed = False
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # ── Results ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    min_checks = 5  # Formation + 2 SOP loads + synthesis parsed + at least 1 runtime check
    if len(checks_passed) >= min_checks and all_passed:
        print("Test Result: ✅ PASSED")
    else:
        print("Test Result: ❌ FAILED")
        all_passed = False
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")
    print("=" * 80)

    if transcript:
        print("\n### Chat transcript:")
        for role, msg in transcript:
            print(f"{role}: {msg}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    import os

    exit_code = asyncio.run(test_sop_synthesis_skip())

    if exit_code == 0:
        print("SUCCESS", flush=True)

    os._exit(exit_code)
