#!/usr/bin/env python3
"""
Test 7A8: Workflow-Level Replanning

Verifies the workflow replanning PRD end to end:
1. Formation config wires a ReplanningCoordinator into the workflow executor.
2. A workflow whose step fails in a replannable way (task timeout) recovers:
   the coordinator generates a genuinely different plan via the real
   TaskDecomposer + LLM and the replanned workflow completes.
3. Completed steps are carried into the replan context and are not
   re-executed.
4. A non-replannable failure (authentication error) is not replanned and the
   workflow still fails cleanly.
5. A formation without a replanning block keeps the executor untouched
   (disabled = passthrough).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.datatypes.workflow import (  # noqa: E402
    SubTask,
    TaskStatus,
    Workflow,
    WorkflowStatus,
)
from muxi.runtime.formation import Formation  # noqa: E402

FORMATIONS = Path(__file__).parent / "formations"

SUCCESS_STATES = {
    WorkflowStatus.COMPLETED,
    WorkflowStatus.COMPLETED.value,
    "completed",
}
FAILED_STATES = {WorkflowStatus.FAILED, WorkflowStatus.FAILED.value, "failed"}

HANG_MARKER = "fetch the commit list via the external api"


def make_workflow() -> Workflow:
    """Two-step workflow whose second step will hang (and time out)."""
    tasks = {
        "task_1": SubTask(
            id="task_1",
            description="List three well-known facts about the Python programming language",
            required_capabilities=["fact_checking"],
        ),
        "task_2": SubTask(
            id="task_2",
            description=f"Now {HANG_MARKER} and count the commits",
            required_capabilities=["web_research"],
            dependencies=["task_1"],
        ),
    }
    return Workflow(
        id="wrk_e2e_replanning",
        user_request=(
            "Research three notable facts about the Python programming language, "
            "then write a short summary paragraph about them."
        ),
        tasks=tasks,
    )


async def test_workflow_replanning():
    print("\n" + "=" * 80)
    print("Test 7A8: Workflow-Level Replanning")
    print("=" * 80)

    all_passed = True
    checks_passed = []

    formation = None
    try:
        # ------------------------------------------------------------------
        print("\n1. Loading formation with replanning enabled...")
        formation = Formation()
        await formation.load(str(FORMATIONS / "formation-replanning" / "formation.yaml"))
        overlord = await formation.start_overlord()
        executor = overlord.workflow_executor
        coordinator = executor.replanning_coordinator

        assert coordinator is not None, "ReplanningCoordinator was not wired"
        assert coordinator.enabled, "ReplanningCoordinator is not enabled"
        assert (
            coordinator.config.max_attempts == 2
        ), f"max_attempts not parsed from formation: {coordinator.config.max_attempts}"
        assert coordinator.config.replan_timeout_seconds == 60.0
        assert coordinator.decomposer is overlord.task_decomposer
        print("   OK ReplanningCoordinator wired from overlord.workflow.replanning")
        checks_passed.append("Coordinator wired from formation config")

        # ------------------------------------------------------------------
        print("\n2. Executing workflow with an injected replannable failure...")
        # The marked task hangs; task_timeout=5s + fail_fast makes it FAIL,
        # which fails the workflow and triggers replanning through the REAL
        # decomposer + LLM.
        patched_agents = {}
        call_log = []

        def patch_agent(agent):
            original = agent.process_message

            async def wrapper(message, *args, **kwargs):
                call_log.append((agent.agent_id, message))
                if HANG_MARKER in message:
                    await asyncio.sleep(3600)
                return await original(message, *args, **kwargs)

            agent.process_message = wrapper
            patched_agents[agent.agent_id] = original

        for agent in executor.agent_registry.values():
            patch_agent(agent)

        original_workflow = make_workflow()
        result = await executor.execute_workflow(
            original_workflow, context={"user_id": "e2e_replanning", "session_id": "7a8"}
        )

        print(f"   Result workflow: {result.id} status={result.status}")
        assert (
            result.status in SUCCESS_STATES
        ), f"Workflow did not complete via replan: status={result.status}"
        assert result.id != "wrk_e2e_replanning", "Result is not a replanned workflow"
        assert coordinator.attempts_for("wrk_e2e_replanning") == 1, (
            f"Expected exactly 1 replan attempt, got "
            f"{coordinator.attempts_for('wrk_e2e_replanning')}"
        )
        print(f"   OK Workflow completed via replan ({len(result.tasks)} replanned tasks)")
        checks_passed.append("Replannable failure recovered via replan")

        # ------------------------------------------------------------------
        print("\n3. Verifying completed steps carried over (not redone)...")
        attempt = coordinator.replan_history["wrk_e2e_replanning"][0]
        carried = attempt.failure_analysis["successful_tasks"]
        assert any(
            t["id"] == "task_1" for t in carried
        ), f"Successful task_1 missing from replan context: {carried}"
        assert any(t["id"] == "task_2" for t in attempt.failure_analysis["failed_tasks"])
        # The exact original task_1 prompt executed exactly once overall
        task_1_runs = sum(
            1
            for _, m in call_log
            if "List three well-known facts about the Python programming language" in m
        )
        assert task_1_runs == 1, f"Completed task re-executed: {task_1_runs} runs"
        # The failed approach was not blindly retried after the replan
        hang_runs = sum(1 for _, m in call_log if HANG_MARKER in m)
        assert hang_runs == 1, f"Failed task re-executed as-is: {hang_runs} runs"
        print("   OK Completed step executed once; results carried into replan context")
        checks_passed.append("Completed steps not re-executed")

        # ------------------------------------------------------------------
        print("\n4. Verifying a non-replannable failure fails cleanly...")
        auth_failed = make_workflow()
        auth_failed.id = "wrk_e2e_auth"
        auth_failed.status = WorkflowStatus.FAILED
        auth_failed.tasks["task_1"].status = TaskStatus.DONE
        auth_failed.tasks["task_2"].status = TaskStatus.FAILED
        auth_failed.tasks["task_2"].error_message = (
            "Authentication failed: invalid credentials for external api"
        )
        should, reason = coordinator.should_replan(auth_failed)
        assert should is False, f"Auth failure must not be replanned: {reason}"
        assert "non-replannable" in reason, reason
        assert "wrk_e2e_auth" not in coordinator.replan_history
        print(f"   OK Non-replannable failure skipped: {reason}")
        checks_passed.append("Non-replannable failure fails cleanly (no replan)")

        # Restore patched agents
        for agent in executor.agent_registry.values():
            if agent.agent_id in patched_agents:
                agent.process_message = patched_agents[agent.agent_id]

        print("\n5. Stopping replanning formation...")
        await formation.stop_overlord()
        formation.stop()
        formation = None
        print("   OK Formation stopped")

        # ------------------------------------------------------------------
        print("\n6. Verifying disabled formations keep the executor untouched...")
        formation = Formation()
        await formation.load(str(FORMATIONS / "formation-workflow-test" / "formation.yaml"))
        overlord2 = await formation.start_overlord()
        assert (
            overlord2.workflow_executor.replanning_coordinator is None
        ), "Executor must have no coordinator when replanning is not configured"
        assert overlord2.workflow_executor.config.replanning.enabled is False
        print("   OK No coordinator wired without a replanning block (passthrough)")
        checks_passed.append("Disabled/unconfigured = passthrough")

        await formation.stop_overlord()
        formation.stop()
        formation = None

    except Exception as e:
        print(f"\nX Test failed: {e}")
        import traceback

        traceback.print_exc()
        all_passed = False
        if formation is not None:
            try:
                await formation.stop_overlord()
                formation.stop()
            except Exception:
                pass

    print("\n" + "=" * 80)
    print(f"Test Result: {'PASSED' if all_passed else 'FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  - {check}")
    print("=" * 80)

    return 0 if all_passed else 1


if __name__ == "__main__":
    import os

    exit_code = asyncio.run(test_workflow_replanning())

    if exit_code == 0:
        print("SUCCESS", flush=True)

    os._exit(exit_code)
