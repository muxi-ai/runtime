#!/usr/bin/env python3
"""Test 9d2: Async retry escalation -- budget exhausts, honest give-up report.

Flow under test (PRD: async-retry-escalation):
1. A sync chat turn fails terminally (stalled tool -> task timeout; the
   control file is never created, so every attempt fails
   deterministically) and escalates: the caller gets the fixed
   escalation message.
2. The bounded background chain (retry_async.max_attempts: 1) spends its
   budget and gives up honestly: the tracker entry ends FAILED with a
   structured report (per-attempt plan summary + failure reason +
   what-would-unblock).
3. The report is retrievable via the real HTTP API: GET
   /v1/requests/{id} returns ``escalated: true`` and the ``report`` for
   the escalated-FAILED entry.
4. The give-up entry lands in the Captain's Log (sqlite-backed).

All assertions are structural/deterministic -- no LLM-judged checks.
"""

import asyncio
import os
import sys
import time
from datetime import date
from pathlib import Path

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from common.base import BaseE2ETest  # noqa: E402

CONTROL_FLAG = Path("/tmp/muxi_e2e_retry_escalation.flag")
BASE_URL = "http://127.0.0.1:8281"
CLIENT_KEY = "test-client-key-9d2"
DB_FILE = Path("retry_escalation_giveup_test.db")

# Give-up states an honest chain may land in here: budget_exhausted when
# the replanned attempt executed and failed; stuck when replanning could
# not produce a meaningfully different plan for the unchanged failure.
GIVE_UP_STATES = {"budget_exhausted", "stuck"}


async def run_test(test: BaseE2ETest) -> bool:
    checks = []

    def check(name: str, passed: bool, detail: str = ""):
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {name}" + (f" -- {detail}" if detail else ""), flush=True)
        checks.append(passed)
        return passed

    CONTROL_FLAG.unlink(missing_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{DB_FILE}{suffix}").unlink(missing_ok=True)

    try:
        # Point at the yaml FILE: with an explicit formation_path the
        # yaml_name parameter is ignored and directory loading picks
        # formation.yaml, which is the 9d1 (recovery) variant.
        formation_path = (
            Path(__file__).parent
            / "formations"
            / "formation-retry-escalation"
            / "formation-give-up.yaml"
        )
        await test.setup_formation(formation_path=str(formation_path))
        await test.formation.start_server(block=False)
        await asyncio.sleep(2)
        overlord = test.overlord

        # --- 1. Sync attempt fails terminally and escalates -------------
        print("Step 1: sync turn (tool stalled, never recovers)", flush=True)
        response = await overlord.chat(
            message=(
                "Please fetch the current system status report with your status "
                "report tool, then write a two-line summary of its contents "
                "and note whether all services are operational."
            ),
            user_id="e2e",
            session_id="sess_9d2",
            stream=False,
        )

        content = getattr(response, "content", str(response))
        metadata = getattr(response, "metadata", None) or {}
        request_id = metadata.get("request_id")

        check(
            "escalation message delivered to waiting caller",
            isinstance(content, str) and content.startswith("This has failed."),
            content[:120],
        )
        check("envelope carries request_id", bool(request_id), str(request_id))
        if not request_id:
            return False

        # --- 2. Chain exhausts its budget and gives up -------------------
        print("Step 2: wait for the chain to give up (bounded budget)", flush=True)
        headers = {"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-ID": "e2e"}
        data = None
        deadline = time.time() + 240
        async with httpx.AsyncClient(timeout=15.0) as client:
            while time.time() < deadline:
                resp = await client.get(f"{BASE_URL}/v1/requests/{request_id}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data") or {}
                    if data.get("status") in ("completed", "failed", "cancelled"):
                        break
                await asyncio.sleep(3)

        check("chain reached a terminal state via the API", bool(data), str(data)[:160])
        if not data:
            return False
        check("terminal status is FAILED (honest give-up)", data.get("status") == "failed")
        check("API surfaces escalated: true", data.get("escalated") is True)

        # --- 3. Structured give-up report via GET /v1/requests/{id} ------
        report = data.get("report")
        if not check("give-up report rides the API response", isinstance(report, dict)):
            return all(checks)
        check(
            "report state is an honest give-up",
            report.get("state") in GIVE_UP_STATES,
            str(report.get("state")),
        )
        attempts = report.get("attempts") or []
        check(
            "report counts the failed sync attempt first",
            bool(attempts) and attempts[0].get("kind") == "sync",
        )
        check("report records the async attempt(s)", len(attempts) >= 2, str(len(attempts)))
        check(
            "every attempt carries plan summary + failure reason",
            all("plan_summary" in a and "failure_reason" in a for a in attempts),
        )
        check("report names what would unblock", bool(report.get("what_would_unblock")))

        # --- 4. Captain's Log contains the give-up entry ------------------
        print("Step 3: verify the Captain's Log entry", flush=True)
        captains_log = getattr(overlord, "captains_log", None)
        if not check("captain's log service is configured", captains_log is not None):
            return all(checks)
        entry = await captains_log.storage.get_entry("0", date.today())
        decisions = (entry or {}).get("decisions") or []
        check(
            "give-up entry landed in the captain's log",
            any("Async retry gave up" in d for d in decisions),
            str(decisions)[:200],
        )

        return all(checks)
    finally:
        CONTROL_FLAG.unlink(missing_ok=True)
        await test.cleanup_formation()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{DB_FILE}{suffix}").unlink(missing_ok=True)


def main():
    test = BaseE2ETest(
        "9d2_retry_escalation_give_up",
        "Escalated retries exhaust the budget; honest report via API + captain's log",
        "9_async",
    )
    success = asyncio.run(run_test(test))
    print("=" * 70, flush=True)
    if success:
        print("Test 9d2 PASSED", flush=True)
        print("SUCCESS", flush=True)
        os._exit(0)
    print("Test 9d2 FAILED", flush=True)
    os._exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Test 9d2 crashed: {e}", flush=True)
        import traceback

        traceback.print_exc()
        os._exit(1)
