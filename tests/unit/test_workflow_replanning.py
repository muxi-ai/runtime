"""Unit tests for workflow-level replanning (PRD: workflow-replanning).

Covers the ReplanningCoordinator decision logic and the WorkflowExecutor
replan loop:

1. Config -- disabled by default, knob parsing, formation validation.
2. Pins -- with replanning disabled/unconfigured the executor takes the
   exact pre-existing execution path (no coordinator involvement).
3. Triggers -- replannable vs non-replannable failures, no-failure and
   budget-exhausted short-circuits.
4. Ceilings -- max replan attempts and the workflow timeout ceiling.
5. GBAC -- replanned workflows re-apply the requesting user's permission
   filtering (never widen access).
6. Carry-over -- successful task results travel into the replan context so
   completed work is not redone; plan-similarity rejects duplicate plans.
7. Prompt -- decomposition prompt gains a replanning section only when a
   replan context is present (byte-identical otherwise).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import List, Optional

import pytest
from pydantic import ValidationError

from muxi.runtime.datatypes.exceptions import WorkflowTimeoutError
from muxi.runtime.datatypes.workflow import SubTask, TaskStatus, Workflow, WorkflowStatus
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.workflow.config import ReplanningConfig, WorkflowConfig
from muxi.runtime.formation.workflow.decomposer import TaskDecomposer
from muxi.runtime.formation.workflow.executor import WorkflowExecutor
from muxi.runtime.formation.workflow.replanning import (
    ReplanningCoordinator,
    ReplanningError,
)
from muxi.runtime.services.gbac import ResolvedPermissions, enforcement, load_groups

# ===================================================================
# Helpers
# ===================================================================


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeAgent:
    """Deterministic agent double.

    Tasks whose prompt contains ``hang_when`` never return, so the
    executor's task timeout fires and the task genuinely FAILS (agent
    exceptions raised inside process_message are swallowed into TaskResult
    payloads by the executor; a timeout is the canonical hard-failure path).
    """

    def __init__(self, agent_id: str, specialties: List[str], hang_when: Optional[str] = None):
        self.agent_id = agent_id
        self.id = agent_id
        self.name = agent_id
        self.specialties = specialties
        self.hang_when = hang_when
        self.calls: List[str] = []

    async def process_message(self, message, user_id=0, session_id=None, request_id=None, **_):
        self.calls.append(message)
        if self.hang_when and self.hang_when in message:
            await asyncio.sleep(3600)
        return FakeResponse(f"{self.agent_id} completed the task")


class StubDecomposer:
    """Decomposer double returning scripted workflows and capturing context."""

    def __init__(self, workflows: List[Workflow], on_call=None):
        self.workflows = list(workflows)
        self.contexts: List[dict] = []
        self.delay: float = 0.0
        self.on_call = on_call  # e.g. advance a fake clock

    async def decompose_request(
        self, request, context=None, analysis=None, requires_approval=False
    ):
        self.contexts.append(context or {})
        if self.on_call:
            self.on_call()
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.workflows:
            raise AssertionError("StubDecomposer exhausted")
        return self.workflows.pop(0)


def make_workflow(workflow_id: str, tasks: List[SubTask]) -> Workflow:
    return Workflow(
        id=workflow_id,
        user_request="summarize recent commits",
        tasks={t.id: t for t in tasks},
    )


def make_task(
    task_id: str,
    description: str,
    capabilities: List[str],
    status: TaskStatus = TaskStatus.PENDING,
    error: Optional[str] = None,
    dependencies: Optional[List[str]] = None,
    assigned_agent_id: Optional[str] = None,
) -> SubTask:
    return SubTask(
        id=task_id,
        description=description,
        required_capabilities=capabilities,
        status=status,
        error_message=error,
        dependencies=dependencies or [],
        assigned_agent_id=assigned_agent_id,
    )


def failed_workflow(
    workflow_id: str = "wrk_original", error: str = "request timed out"
) -> Workflow:
    wf = make_workflow(
        workflow_id,
        [
            make_task("task_1", "fetch commits via api", ["research"], status=TaskStatus.DONE),
            make_task(
                "task_2",
                "summarize the commits",
                ["writing"],
                status=TaskStatus.FAILED,
                error=error,
            ),
        ],
    )
    wf.tasks["task_1"].result = {"main": {"result": "42 commits fetched", "status": "success"}}
    wf.status = WorkflowStatus.FAILED
    return wf


def make_config(**overrides) -> ReplanningConfig:
    return ReplanningConfig(enabled=True, **overrides)


def make_executor(
    agents: dict, replanning: Optional[ReplanningCoordinator] = None, **config_overrides
) -> WorkflowExecutor:
    # fail_fast + 1s task timeout so a hanging FakeAgent fails its task
    # quickly and deterministically (no retries in unit tests).
    config_overrides.setdefault("error_recovery_strategy", "fail_fast")
    config_overrides.setdefault(
        "timeout",
        {
            "task_timeout": 1.0,
            "phase_timeout": 600.0,
            "workflow_timeout": 3600.0,
            "max_timeout_seconds": 7200.0,
        },
    )
    config = WorkflowConfig(**config_overrides)
    executor = WorkflowExecutor(agent_registry=agents, config=config)
    executor.overlord = None  # no skill manager in unit tests
    executor.replanning_coordinator = replanning
    return executor


# ===================================================================
# 1. Configuration
# ===================================================================


class TestReplanningConfig:
    def test_disabled_by_default(self):
        assert WorkflowConfig().replanning.enabled is False

    def test_defaults(self):
        cfg = ReplanningConfig()
        assert cfg.max_attempts == 3
        assert cfg.plan_similarity_threshold == 0.7
        assert cfg.preserve_successful_outputs is True
        assert cfg.replan_timeout_seconds == 30.0

    def test_bounds_enforced(self):
        with pytest.raises(ValidationError):
            ReplanningConfig(max_attempts=0)
        with pytest.raises(ValidationError):
            ReplanningConfig(max_attempts=11)
        with pytest.raises(ValidationError):
            ReplanningConfig(plan_similarity_threshold=1.5)
        with pytest.raises(ValidationError):
            ReplanningConfig(replan_timeout_seconds=0.1)

    def test_formation_validation_accepts_valid_block(self):
        validator = FormationValidator()
        validator._validate_overlord_workflow_config(
            {
                "replanning": {
                    "enabled": True,
                    "max_attempts": 2,
                    "plan_similarity_threshold": 0.5,
                    "preserve_successful_outputs": False,
                    "replan_timeout_seconds": 15,
                }
            }
        )
        assert not validator.result.errors

    def test_formation_validation_rejects_bad_values(self):
        validator = FormationValidator()
        validator._validate_overlord_workflow_config(
            {
                "replanning": {
                    "enabled": "yes",
                    "max_attempts": 99,
                    "plan_similarity_threshold": 2,
                    "replan_timeout_seconds": 0,
                }
            }
        )
        messages = " ".join(validator.result.errors)
        assert "replanning.enabled" in messages
        assert "replanning.max_attempts" in messages
        assert "replanning.plan_similarity_threshold" in messages
        assert "replanning.replan_timeout_seconds" in messages

    def test_formation_validation_rejects_non_dict(self):
        validator = FormationValidator()
        validator._validate_overlord_workflow_config({"replanning": "on"})
        assert any("must be a dictionary" in e for e in validator.result.errors)

    def test_from_formation_data_absent_uses_defaults(self):
        assert ReplanningConfig.from_formation_data(None) == ReplanningConfig()
        assert ReplanningConfig.from_formation_data({}) == ReplanningConfig()

    def test_from_formation_data_parses_all_knobs(self):
        cfg = ReplanningConfig.from_formation_data(
            {
                "enabled": True,
                "max_attempts": 5,
                "plan_similarity_threshold": 0.4,
                "preserve_successful_outputs": False,
                "replan_timeout_seconds": 12,
                "non_replannable_error_patterns": ["quota exceeded", "banned"],
            }
        )
        assert cfg.enabled is True
        assert cfg.max_attempts == 5
        assert cfg.plan_similarity_threshold == 0.4
        assert cfg.preserve_successful_outputs is False
        assert cfg.replan_timeout_seconds == 12
        assert cfg.non_replannable_error_patterns == ["quota exceeded", "banned"]

    def test_custom_patterns_used_by_should_replan(self):
        cfg = ReplanningConfig.from_formation_data(
            {"enabled": True, "non_replannable_error_patterns": ["timed out"]}
        )
        coordinator = ReplanningCoordinator(StubDecomposer([]), cfg)

        # The custom pattern makes the default-replannable timeout non-replannable
        should, reason = coordinator.should_replan(failed_workflow(error="request timed out"))
        assert should is False
        assert "non-replannable" in reason

        # ...and auth errors (no longer listed) become replannable
        should, _ = coordinator.should_replan(
            failed_workflow(error="Authentication failed: invalid credentials")
        )
        assert should is True

    @pytest.mark.parametrize("patterns", ["auth", [""], ["  "], [1, 2]])
    def test_from_formation_data_rejects_malformed_patterns(self, patterns):
        with pytest.raises(ValidationError):
            ReplanningConfig.from_formation_data({"non_replannable_error_patterns": patterns})

    def test_formation_validation_patterns(self):
        validator = FormationValidator()
        validator._validate_overlord_workflow_config(
            {"replanning": {"non_replannable_error_patterns": ["quota", "banned"]}}
        )
        assert not validator.result.errors

        for bad in ("auth", ["", "x"], [1]):
            validator = FormationValidator()
            validator._validate_overlord_workflow_config(
                {"replanning": {"non_replannable_error_patterns": bad}}
            )
            assert any("non_replannable_error_patterns" in e for e in validator.result.errors)


# ===================================================================
# 2. Disabled = passthrough pins
# ===================================================================


class TestDisabledPassthrough:
    async def test_no_coordinator_executes_directly(self):
        agent = FakeAgent("writer", ["writing", "research"])
        executor = make_executor({"writer": agent})
        assert executor.replanning_coordinator is None

        wf = make_workflow(
            "wrk_plain",
            [make_task("task_1", "write a haiku", ["writing"])],
        )
        result = await executor.execute_workflow(wf)
        assert result.status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPLETED.value)

    async def test_disabled_coordinator_never_consulted(self):
        agent = FakeAgent("writer", ["writing"], hang_when="haiku")
        decomposer = StubDecomposer([])
        coordinator = ReplanningCoordinator(decomposer, ReplanningConfig(enabled=False))
        executor = make_executor({"writer": agent}, replanning=coordinator)

        wf = make_workflow("wrk_disabled", [make_task("task_1", "write a haiku", ["writing"])])
        result = await executor.execute_workflow(wf)

        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)
        assert decomposer.contexts == []  # decomposer never invoked
        assert coordinator.replan_history == {}

    async def test_failed_workflow_without_coordinator_unchanged(self):
        agent = FakeAgent("writer", ["writing"], hang_when="haiku")
        executor = make_executor({"writer": agent})
        wf = make_workflow("wrk_fail", [make_task("task_1", "write a haiku", ["writing"])])
        result = await executor.execute_workflow(wf)
        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)


# ===================================================================
# 3. Trigger conditions
# ===================================================================


class TestShouldReplan:
    def test_replans_on_replannable_failure(self):
        coordinator = ReplanningCoordinator(StubDecomposer([]), make_config())
        should, reason = coordinator.should_replan(failed_workflow())
        assert should is True
        assert "replannable" in reason

    @pytest.mark.parametrize(
        "error",
        [
            "Authentication failed: invalid credentials",
            "HTTP 403 Forbidden",
            "permission denied for resource",
            "Configuration error: missing api key",
        ],
    )
    def test_skips_non_replannable_failures(self, error):
        coordinator = ReplanningCoordinator(StubDecomposer([]), make_config())
        should, reason = coordinator.should_replan(failed_workflow(error=error))
        assert should is False
        assert "non-replannable" in reason

    def test_skips_when_no_failed_tasks(self):
        coordinator = ReplanningCoordinator(StubDecomposer([]), make_config())
        wf = make_workflow(
            "wrk_ok", [make_task("task_1", "done task", ["writing"], status=TaskStatus.DONE)]
        )
        should, reason = coordinator.should_replan(wf)
        assert should is False
        assert reason == "No failed tasks"

    def test_skips_when_disabled(self):
        coordinator = ReplanningCoordinator(StubDecomposer([]), ReplanningConfig(enabled=False))
        should, reason = coordinator.should_replan(failed_workflow())
        assert should is False
        assert "disabled" in reason

    def test_skips_when_budget_exhausted(self):
        coordinator = ReplanningCoordinator(StubDecomposer([]), make_config(max_attempts=1))
        wf = failed_workflow()
        coordinator.replan_history[wf.id] = [SimpleNamespace()]
        should, reason = coordinator.should_replan(wf)
        assert should is False
        assert "budget exhausted" in reason

    def test_budget_spans_replan_chain(self):
        """Attempts on replanned workflows count against the original budget."""
        coordinator = ReplanningCoordinator(StubDecomposer([]), make_config(max_attempts=1))
        coordinator._root_ids["wrk_replanned"] = "wrk_original"
        coordinator.replan_history["wrk_original"] = [SimpleNamespace()]
        should, reason = coordinator.should_replan(failed_workflow("wrk_replanned"))
        assert should is False
        assert "budget exhausted" in reason


# ===================================================================
# 4. generate_replan: carry-over, similarity, timeout
# ===================================================================


class TestGenerateReplan:
    async def test_replan_context_carries_over_results(self):
        new_wf = make_workflow(
            "wrk_new", [make_task("task_1", "summarize via git cli", ["coding"])]
        )
        decomposer = StubDecomposer([new_wf])
        coordinator = ReplanningCoordinator(decomposer, make_config())

        result = await coordinator.generate_replan(failed_workflow(), {"user_id": "alice"})

        assert result.id == "wrk_new"
        replan = decomposer.contexts[0]["replan"]
        assert replan["is_replan"] is True
        assert replan["attempt"] == 1
        # Completed work carried over so it is not redone
        assert [t["id"] for t in replan["successful_tasks"]] == ["task_1"]
        assert "42 commits fetched" in replan["successful_tasks"][0]["result_excerpt"]
        # Failure context present
        assert [t["id"] for t in replan["failed_tasks"]] == ["task_2"]
        assert replan["blocked_capabilities"] == ["writing"]
        assert any("DIFFERENT" in c for c in replan["constraints"])
        # Original request context preserved
        assert decomposer.contexts[0]["user_id"] == "alice"
        # History recorded and chained
        assert coordinator.attempts_for("wrk_new") == 1
        assert coordinator.root_id("wrk_new") == "wrk_original"

    async def test_preserve_successful_outputs_disabled(self):
        new_wf = make_workflow("wrk_new", [make_task("task_1", "different plan", ["coding"])])
        decomposer = StubDecomposer([new_wf])
        coordinator = ReplanningCoordinator(
            decomposer, make_config(preserve_successful_outputs=False)
        )
        await coordinator.generate_replan(failed_workflow())
        assert decomposer.contexts[0]["replan"]["successful_tasks"] == []

    async def test_duplicate_plan_rejected(self):
        original = failed_workflow()
        duplicate = make_workflow(
            "wrk_dup",
            [
                make_task("task_1", "fetch commits via api", ["research"]),
                make_task("task_2", "summarize the commits", ["writing"]),
            ],
        )
        coordinator = ReplanningCoordinator(StubDecomposer([duplicate]), make_config())
        with pytest.raises(ReplanningError, match="too similar"):
            await coordinator.generate_replan(original)
        # Rejected plans do not consume budget history entries
        assert coordinator.replan_history == {}

    async def test_replan_generation_timeout(self):
        new_wf = make_workflow("wrk_new", [make_task("task_1", "other plan", ["coding"])])
        decomposer = StubDecomposer([new_wf])
        decomposer.delay = 0.2
        coordinator = ReplanningCoordinator(decomposer, make_config())
        coordinator.config = coordinator.config.model_copy(update={"replan_timeout_seconds": 0.05})
        with pytest.raises(ReplanningError, match="timed out"):
            await coordinator.generate_replan(failed_workflow())


# ===================================================================
# 5. Executor replan loop
# ===================================================================


class TestExecutorReplanLoop:
    async def test_workflow_completes_via_replan(self):
        """A replannable failure recovers through a different plan, and the
        successful task from the first plan is not re-executed."""
        api_agent = FakeAgent("api-agent", ["research"], hang_when="via api")
        cli_agent = FakeAgent("cli-agent", ["coding"])

        replanned = make_workflow(
            "wrk_replanned", [make_task("task_1", "summarize via git cli", ["coding"])]
        )
        decomposer = StubDecomposer([replanned])
        coordinator = ReplanningCoordinator(decomposer, make_config())
        executor = make_executor(
            {"api-agent": api_agent, "cli-agent": cli_agent}, replanning=coordinator
        )

        original = make_workflow(
            "wrk_original",
            [
                make_task("task_1", "gather repo facts", ["research"]),
                make_task("task_2", "fetch commits via api", ["research"], dependencies=["task_1"]),
            ],
        )
        result = await executor.execute_workflow(original, {"user_id": "alice"})

        assert result.id == "wrk_replanned"
        assert result.status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPLETED.value)
        assert coordinator.attempts_for("wrk_original") == 1
        # Completed step carried over in replan context, not redone:
        replan = decomposer.contexts[0]["replan"]
        assert [t["description"] for t in replan["successful_tasks"]] == ["gather repo facts"]
        assert sum("gather repo facts" in m for m in api_agent.calls) == 1
        assert len(cli_agent.calls) == 1

    async def test_non_replannable_failure_fails_cleanly(self, monkeypatch):
        """Auth-style failures return the failed workflow without replanning."""
        decomposer = StubDecomposer([])
        coordinator = ReplanningCoordinator(decomposer, make_config())
        executor = make_executor({}, replanning=coordinator)

        failed = failed_workflow(error="Authentication failed: invalid credentials")

        async def fake_execute(workflow, context=None, max_timeout_override=None):
            return failed

        monkeypatch.setattr(executor, "_execute_workflow_with_timeout", fake_execute)
        result = await executor.execute_workflow(failed, {})

        assert result is failed
        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)
        assert decomposer.contexts == []
        assert coordinator.replan_history == {}

    async def test_max_attempt_ceiling(self):
        """Replanning stops at max_attempts even if every plan keeps failing."""
        agent = FakeAgent("api-agent", ["research"], hang_when="doomed")
        plans = [
            make_workflow(
                f"wrk_plan_{i}", [make_task("task_1", f"doomed attempt {i}", ["research"])]
            )
            for i in range(2, 10)
        ]
        decomposer = StubDecomposer(plans)
        coordinator = ReplanningCoordinator(decomposer, make_config(max_attempts=2))
        executor = make_executor({"api-agent": agent}, replanning=coordinator)

        original = make_workflow(
            "wrk_plan_1", [make_task("task_1", "doomed attempt 1", ["research"])]
        )
        result = await executor.execute_workflow(original)

        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)
        # 2 replans generated (budget), then the loop stopped
        assert len(decomposer.contexts) == 2
        assert coordinator.attempts_for("wrk_plan_1") == 2
        # Original + 2 replanned executions
        assert len(agent.calls) == 3

    async def test_timeout_ceiling_blocks_replan(self):
        """No replan starts when the workflow's max timeout budget is spent."""
        agent = FakeAgent("api-agent", ["research"], hang_when="doomed")
        decomposer = StubDecomposer([])
        coordinator = ReplanningCoordinator(decomposer, make_config())
        # After the ~1s failed execution, the remaining budget of the 5s
        # ceiling is always <= replan_timeout_seconds (30s), so no replan
        # can be started.
        executor = make_executor(
            {"api-agent": agent},
            replanning=coordinator,
            timeout={
                "max_timeout_seconds": 5.0,
                "workflow_timeout": 5.0,
                "task_timeout": 1.0,
                "phase_timeout": 5.0,
            },
        )
        wf = make_workflow("wrk_slow", [make_task("task_1", "doomed task", ["research"])])
        result = await executor.execute_workflow(wf)

        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)
        assert decomposer.contexts == []  # replan skipped: not enough budget left

    async def test_replan_events_emitted(self, monkeypatch):
        from muxi.runtime.services import observability

        events = []
        original_observe = observability.observe

        def capture(event_type=None, **kwargs):
            events.append(event_type)
            return original_observe(event_type=event_type, **kwargs)

        monkeypatch.setattr(
            "muxi.runtime.formation.workflow.executor.observability.observe", capture
        )

        api_agent = FakeAgent("api-agent", ["research"], hang_when="via api")
        cli_agent = FakeAgent("cli-agent", ["coding"])
        replanned = make_workflow(
            "wrk_replanned", [make_task("task_1", "summarize via git cli", ["coding"])]
        )
        coordinator = ReplanningCoordinator(StubDecomposer([replanned]), make_config())
        executor = make_executor(
            {"api-agent": api_agent, "cli-agent": cli_agent}, replanning=coordinator
        )
        wf = make_workflow(
            "wrk_original", [make_task("task_1", "fetch commits via api", ["research"])]
        )
        await executor.execute_workflow(wf)

        assert observability.ConversationEvents.WORKFLOW_REPLANNING_STARTED in events
        assert observability.ConversationEvents.WORKFLOW_REPLANNING_COMPLETED in events


# ===================================================================
# 5b. Budget anchoring across the replan chain (simulated clock)
# ===================================================================


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TestReplanBudgetAnchoring:
    """The replan chain's time budget is anchored to the original workflow's
    wall-clock start and recomputed AFTER replan generation, so generation
    time is deducted and chained replans can never exceed the original
    max_timeout_seconds ceiling."""

    MAX_TIMEOUT = 100.0

    def _executor(self, monkeypatch, clock, coordinator, exec_cost):
        executor = make_executor(
            {},
            replanning=coordinator,
            timeout={
                "task_timeout": 1.0,
                "phase_timeout": 600.0,
                "workflow_timeout": self.MAX_TIMEOUT,
                "max_timeout_seconds": self.MAX_TIMEOUT,
            },
        )
        monkeypatch.setattr(
            "muxi.runtime.formation.workflow.executor.time",
            SimpleNamespace(monotonic=clock.monotonic),
        )

        dispatches = []
        max_timeout = self.MAX_TIMEOUT

        async def fake_execute(workflow, context=None, max_timeout_override=None):
            # Every override must equal ceiling minus elapsed at dispatch time
            if max_timeout_override is not None:
                assert max_timeout_override == pytest.approx(max_timeout - clock.now)
            dispatches.append(max_timeout_override)
            clock.advance(exec_cost)
            for task in workflow.tasks.values():
                task.status = TaskStatus.FAILED
                task.error_message = "request timed out"
            workflow.status = WorkflowStatus.FAILED
            return workflow

        monkeypatch.setattr(executor, "_execute_workflow_with_timeout", fake_execute)
        return executor, dispatches

    @staticmethod
    def _plans(count):
        return [
            make_workflow(f"wrk_plan_{i}", [make_task("task_1", f"attempt {i}", ["research"])])
            for i in range(2, 2 + count)
        ]

    async def test_generation_time_reduces_executing_budget(self, monkeypatch):
        clock = FakeClock()
        decomposer = StubDecomposer(self._plans(1), on_call=lambda: clock.advance(10))
        coordinator = ReplanningCoordinator(
            decomposer, make_config(max_attempts=1, replan_timeout_seconds=5)
        )
        executor, dispatches = self._executor(monkeypatch, clock, coordinator, exec_cost=20)

        original = make_workflow("wrk_plan_1", [make_task("task_1", "attempt 1", ["research"])])
        await executor.execute_workflow(original)

        # exec (20s) + replan generation (10s) leave 70s of the 100s ceiling
        assert dispatches == [None, pytest.approx(70.0)]

    async def test_exhausted_after_generation_aborts_instead_of_dispatching(self, monkeypatch):
        clock = FakeClock()
        decomposer = StubDecomposer(self._plans(1), on_call=lambda: clock.advance(50))
        coordinator = ReplanningCoordinator(decomposer, make_config(replan_timeout_seconds=40))
        executor, dispatches = self._executor(monkeypatch, clock, coordinator, exec_cost=50)

        original = make_workflow("wrk_plan_1", [make_task("task_1", "attempt 1", ["research"])])
        # The pre-generation budget (50s) passes the gate (> 40s), but
        # generation consumes the rest -> abort with the timeout outcome
        with pytest.raises(WorkflowTimeoutError):
            await executor.execute_workflow(original)

        assert dispatches == [None]  # replanned workflow never executed
        assert len(decomposer.contexts) == 1  # generation itself did run

    async def test_chained_replans_never_exceed_original_ceiling(self, monkeypatch):
        clock = FakeClock()
        decomposer = StubDecomposer(self._plans(5), on_call=lambda: clock.advance(10))
        coordinator = ReplanningCoordinator(
            decomposer, make_config(max_attempts=5, replan_timeout_seconds=5)
        )
        executor, dispatches = self._executor(monkeypatch, clock, coordinator, exec_cost=30)

        original = make_workflow("wrk_plan_1", [make_task("task_1", "attempt 1", ["research"])])
        result = await executor.execute_workflow(original)

        # exec1 30s; gen1 +10s -> dispatch with 60s; exec2 30s; gen2 +10s ->
        # dispatch with 20s; exec3 30s; next replan blocked by the ceiling.
        assert dispatches == [None, pytest.approx(60.0), pytest.approx(20.0)]
        budgets = [d for d in dispatches if d is not None]
        assert budgets == sorted(budgets, reverse=True)  # strictly shrinking
        assert all(0 < b <= self.MAX_TIMEOUT for b in budgets)
        assert result.status in (WorkflowStatus.FAILED, WorkflowStatus.FAILED.value)
        assert len(decomposer.contexts) == 2  # third replan never generated


# ===================================================================
# 6. GBAC: replans never widen access
# ===================================================================


class TestReplanRespectsPermissions:
    @pytest.fixture(autouse=True)
    def clean_permission_context(self):
        token = enforcement.set_current_permissions(None)
        yield
        enforcement.reset_current_permissions(token)

    @staticmethod
    def _perms(tmp_path, *allowed_agents: str) -> ResolvedPermissions:
        groups_dir = tmp_path / "groups"
        groups_dir.mkdir(exist_ok=True)
        agents_yaml = "\n".join(f"  - {a}" for a in allowed_agents)
        (groups_dir / "g.yaml").write_text(f"agents:\n{agents_yaml}\n")
        groups = load_groups(str(groups_dir))
        return ResolvedPermissions(group_ids=("g",), groups=(groups["g"],))

    async def test_replanned_workflow_cannot_reach_denied_agent(self, tmp_path):
        """Even a replanned plan that explicitly names a denied agent is
        constrained to the requesting user's permitted agents."""
        enforcement.set_current_permissions(self._perms(tmp_path, "cli-agent"))

        api_agent = FakeAgent("api-agent", ["research"])
        cli_agent = FakeAgent("cli-agent", ["coding", "research"], hang_when="fetch commits")

        # The replanned plan explicitly (and wrongly) names the denied agent
        replanned = make_workflow(
            "wrk_replanned",
            [
                make_task(
                    "task_1", "summarize via git cli", ["research"], assigned_agent_id="api-agent"
                )
            ],
        )
        coordinator = ReplanningCoordinator(StubDecomposer([replanned]), make_config())
        executor = make_executor(
            {"api-agent": api_agent, "cli-agent": cli_agent}, replanning=coordinator
        )

        original = make_workflow(
            "wrk_original", [make_task("task_1", "fetch commits from repo", ["coding"])]
        )
        result = await executor.execute_workflow(original, {})

        assert result.id == "wrk_replanned"
        assert result.status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPLETED.value)
        # GBAC forced the permitted agent despite the explicit assignment
        assert result.tasks["task_1"].assigned_agent_id == "cli-agent"
        assert api_agent.calls == []

    def test_decomposer_capabilities_filtered_during_replan(self, tmp_path):
        """The decomposer's capability view (used for replan generation)
        excludes denied agents under the same request context."""
        enforcement.set_current_permissions(self._perms(tmp_path, "cli-agent"))
        decomposer = TaskDecomposer(
            agent_registry={
                "api-agent": SimpleNamespace(
                    agent_id="api-agent",
                    name="api",
                    description="",
                    role="x",
                    specialties=["research"],
                ),
                "cli-agent": SimpleNamespace(
                    agent_id="cli-agent",
                    name="cli",
                    description="",
                    role="x",
                    specialties=["coding"],
                ),
            }
        )
        info = decomposer._get_available_capabilities_info()
        assert "cli-agent" in info
        assert "api-agent" not in info


# ===================================================================
# 7. Decomposition prompt replanning section
# ===================================================================


class TestReplanPromptInjection:
    @pytest.fixture(autouse=True)
    def prompt_loader(self):
        from muxi.runtime.formation.prompts.loader import PromptLoader

        PromptLoader.initialize()
        yield

    def _decomposer(self):
        return TaskDecomposer(agent_registry={})

    def test_prompt_unchanged_without_replan_context(self):
        decomposer = self._decomposer()
        baseline, _ = decomposer._create_decomposition_messages("do a thing", context=None)
        with_ctx, _ = decomposer._create_decomposition_messages(
            "do a thing", context={"user_id": "alice"}
        )
        assert "REPLANNING CONTEXT" not in baseline
        assert "REPLANNING CONTEXT" not in with_ctx
        assert "<replanning>" not in baseline

    def test_prompt_contains_replan_section(self):
        decomposer = self._decomposer()
        replan = {
            "is_replan": True,
            "attempt": 2,
            "max_attempts": 3,
            "failed_tasks": [
                {
                    "id": "task_2",
                    "description": "summarize the commits",
                    "error_message": "request timed out",
                }
            ],
            "successful_tasks": [
                {
                    "id": "task_1",
                    "description": "fetch commits via api",
                    "result_excerpt": "42 commits fetched",
                }
            ],
            "blocked_capabilities": ["writing"],
            "constraints": ["Generate a meaningfully DIFFERENT approach"],
        }
        prompt, user_content = decomposer._create_decomposition_messages(
            "summarize recent commits", context={"replan": replan}
        )
        assert "<replanning>" in prompt
        assert "REPLANNING CONTEXT" in prompt
        assert "attempt 2 of 3" in prompt
        assert "request timed out" in prompt
        assert "do NOT redo" in prompt
        assert "42 commits fetched" in prompt
        assert "writing" in prompt
        # The raw replan dict is not leaked into the generic context blob
        assert "'replan'" not in prompt
        assert user_content == "summarize recent commits"
