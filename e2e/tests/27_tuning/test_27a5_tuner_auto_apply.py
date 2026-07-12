#!/usr/bin/env python3
"""
Test 27A5: tuner auto-apply (Self-Improving Formation, Phase 2 step 2).

A planted flaky-tool pattern in the spool -> one tuning pass (real LLM)
distills learnings and applies a MUXI.md revision directly (auto_apply
default) -> the revision is provably injected into the next turn's
context -> a planted expired experiment whose watched metric did not
move is deterministically retired on a later pass.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from tuning_common import (
    build_formation,
    chat,
    experiments_path_for,
    load_formation,
    plant_tool_failures,
    run_tuning_pass,
    spool_dir_for,
    teardown,
    unique_formation_id,
    wait_for_segments,
)

USER = "tuner-e2e-user"


async def main():
    print("MUXI Runtime - Test 27A5: tuner auto-apply + watch-window retirement")
    print("=" * 60)

    formation = None
    formation_id = unique_formation_id("autoapply")
    tmp = Path(tempfile.mkdtemp(prefix="muxi-tuning-27a5-"))
    transcript = []
    try:
        formation_dir = build_formation(tmp, formation_id)
        formation, overlord = await load_formation(formation_dir)
        print(f"Formation loaded: {formation_id}")

        # 1. Real traffic plus the planted flaky-tool pattern.
        task = "What is 3 + 4? Digits only."
        reply = await chat(overlord, task, USER, "tuner-session")
        transcript.append((task, reply))
        print(f"User: {task}\nSystem: {reply}")
        plant_tool_failures(count=30, tool="acme-crm")
        wait_for_segments(spool_dir_for(formation_id))

        # 2. One pass: digest + tune. auto_apply is the default, so the
        #    revision lands in the live MUXI.md.
        result = await run_tuning_pass(overlord)
        print(f"Tuning pass: {result}")
        assert result["spool_committed"] is True
        assert result["muxi_md_applied"] is True, f"the tuner did not apply a revision: {result}"
        muxi_md = overlord.muxi_md.read()
        assert muxi_md, "MUXI.md is empty after an applied revision"
        print(f"Applied MUXI.md:\n{muxi_md}")

        # 3. Learnings recorded as active experiments with open windows,
        #    and the planted flaky tool surfaced in the distillation
        #    (in the applied guidance or in a recorded learning).
        experiments = json.loads(experiments_path_for(formation_id).read_text())["experiments"]
        active = [record for record in experiments if record["status"] == "active"]
        assert active, f"no active experiment was recorded: {experiments}"
        print(f"Recorded {len(active)} active learning(s):")
        for record in active:
            print(f"  - {record['learning']} (metric: {record['metric_key']})")
        distilled = (
            muxi_md.lower()
            + " ".join(
                (record.get("learning") or "") + (record.get("evidence") or "") for record in active
            ).lower()
        )
        assert "acme-crm" in distilled or "acme" in distilled, (
            "the planted flaky-tool pattern did not surface in the applied "
            f"guidance or recorded learnings: {muxi_md!r} / {active}"
        )
        assert any(
            record["metric_key"] == "problem:mcp.tool.failed" for record in active
        ), f"no learning watches the planted failure metric: {active}"

        # 4. The applied guidance is injected into the very next turn's
        #    context (agent-bound bundle seam; no restart).
        bundle = await overlord.chat_orchestrator._build_clean_chat_context(
            current_user_message="Anything to know?",
            user_id=USER,
            session_id="tuner-session",
        )
        assert muxi_md in bundle["user_profile_text"], (
            "the applied MUXI.md revision was not injected into the next " "turn's context"
        )
        print("Applied revision present in the next turn's context bundle")

        # 5. Watch-window retirement is deterministic: plant an expired
        #    experiment whose baseline is near zero, keep the failures
        #    flowing, and the next pass retires it (the rate can never
        #    improve on a near-zero baseline while failures persist).
        path = experiments_path_for(formation_id)
        payload = json.loads(path.read_text())
        payload["experiments"].append(
            {
                "content_hash": "planted-hash-for-retirement",
                "status": "active",
                "learning": "Planted learning that changed nothing.",
                "evidence": "planted",
                "metric_key": "problem:mcp.tool.failed",
                "baseline": 0.0001,
                "watch": {"opened_at": time.time() - 8 * 24 * 3600, "window_hours": 168},
                "created_at": time.time(),
                "updated_at": time.time(),
            }
        )
        path.write_text(json.dumps(payload))
        plant_tool_failures(count=30, tool="acme-crm")  # rate stays 1.0 -- no movement
        result = await run_tuning_pass(overlord)
        print(f"Retirement pass: {result}")
        assert result["learnings_retired"] >= 1, f"no learning was retired: {result}"

        experiments = json.loads(path.read_text())["experiments"]
        planted = next(
            record
            for record in experiments
            if record["content_hash"] == "planted-hash-for-retirement"
        )
        assert planted["status"] == "retired", f"planted learning was not retired: {planted}"
        assert planted["outcome"]["moved"] is False
        print("Planted no-movement learning retired on the later pass")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: tuner auto-apply works end-to-end")
        print("  - a planted flaky-tool pattern was distilled into MUXI.md (auto_apply)")
        print("  - learnings were recorded as active experiments with open windows")
        print("  - the applied revision steers the very next turn's context")
        print("  - a no-movement learning was deterministically retired on a later run")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        for task, reply in transcript:
            print(f"\nUser: {task}")
            print(f"System: {reply}")

        print("\nTest 27A5 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if formation is not None:
            await teardown(formation, formation_id)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
