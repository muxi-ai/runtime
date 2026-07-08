"""
Workflow-level replanning for MUXI Runtime.

Task-level recovery (retries with backoff, alternate agents, fallbacks in
``ResilientWorkflowExecutor`` and the agent's own repair flow) handles
transient failures but keeps re-trying the *same approach*. The
``ReplanningCoordinator`` operates one level up: when a whole workflow fails,
it analyzes why, decides whether a fundamentally different plan could
succeed, and asks the ``TaskDecomposer`` for a replacement plan that avoids
the observed failure modes.

Guarantees:
- Bounded: at most ``ReplanningConfig.max_attempts`` replans per original
  workflow (attempts on replanned workflows count against the original).
- Loop-safe: a replacement plan too similar to the failed plan is rejected.
- Permission-safe: replanning re-enters ``TaskDecomposer.decompose_request``
  inside the same request context, so GBAC permission filtering (a
  request-scoped ContextVar) applies to the new plan exactly as it did to
  the original -- access is never widened.
"""

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ...datatypes.workflow import TaskStatus, Workflow
from .config import ReplanningConfig
from .executor import _is_success, _status_eq

# Maximum characters of a successful task's result carried into the replan
# context (keeps the decomposition prompt bounded).
_RESULT_EXCERPT_CHARS = 500

# Maximum replan chains retained in coordinator history. Chains are pruned
# oldest-first so a long-lived formation never grows unbounded state.
_MAX_HISTORY_CHAINS = 200


class ReplanningError(Exception):
    """Raised when a replacement plan cannot be generated."""


class ReplanAttempt(BaseModel):
    """Record of a single replanning attempt."""

    original_workflow_id: str = Field(..., description="Workflow the replan chain started from")
    failed_workflow_id: str = Field(..., description="Workflow whose failure triggered this replan")
    new_workflow_id: str = Field(..., description="Replacement workflow that was generated")
    attempt_number: int = Field(..., ge=1, description="1-based attempt number within the chain")
    failure_analysis: Dict[str, Any] = Field(
        default_factory=dict, description="Failure analysis passed to the decomposer"
    )
    constraints_applied: List[str] = Field(
        default_factory=list, description="Constraints the new plan was asked to honor"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the replan happened"
    )

    model_config = ConfigDict(extra="forbid")


class ReplanningCoordinator:
    """Orchestrates workflow-level replanning decisions.

    The coordinator is deliberately stateless about execution: the
    ``WorkflowExecutor`` owns the execute/replan loop and calls
    :meth:`should_replan` / :meth:`generate_replan` between attempts.
    """

    def __init__(self, decomposer, config: Optional[ReplanningConfig] = None):
        """
        Args:
            decomposer: TaskDecomposer used to generate replacement plans.
            config: Replanning configuration (disabled by default).
        """
        self.decomposer = decomposer
        self.config = config or ReplanningConfig()
        # Replan attempts keyed by the ORIGINAL workflow id so budgets span
        # the whole replan chain, not each intermediate workflow.
        self.replan_history: Dict[str, List[ReplanAttempt]] = {}
        # Maps replanned workflow ids back to the original workflow id.
        self._root_ids: Dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        """Whether replanning is switched on in configuration."""
        return bool(self.config.enabled)

    def root_id(self, workflow_id: str) -> str:
        """Resolve a workflow id to the original workflow of its replan chain."""
        return self._root_ids.get(workflow_id, workflow_id)

    def attempts_for(self, workflow_id: str) -> int:
        """Number of replan attempts already spent on this workflow's chain."""
        return len(self.replan_history.get(self.root_id(workflow_id), []))

    def should_replan(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """Determine whether replanning is warranted for a failed workflow.

        Returns:
            (should_replan, reason) -- reason explains the decision either way.
        """
        if not self.enabled:
            return False, "Replanning is disabled"

        attempts = self.attempts_for(workflow.id)
        if attempts >= self.config.max_attempts:
            return False, f"Replan budget exhausted ({attempts}/{self.config.max_attempts})"

        failed_tasks = [
            task for task in workflow.tasks.values() if _status_eq(task.status, TaskStatus.FAILED)
        ]
        if not failed_tasks:
            return False, "No failed tasks"

        replannable = [t for t in failed_tasks if self._is_replannable_error(t.error_message)]
        if not replannable:
            return False, (
                "All failures are non-replannable (authentication, permission, or "
                "configuration errors that a different plan cannot avoid)"
            )

        return True, (
            f"{len(replannable)}/{len(failed_tasks)} failed task(s) have replannable errors"
        )

    def analyze_failures(self, workflow: Workflow) -> Dict[str, Any]:
        """Summarize what failed and what worked in a failed workflow."""
        failed_tasks: List[Dict[str, Any]] = []
        successful_tasks: List[Dict[str, Any]] = []
        blocked_capabilities: set = set()

        for task in workflow.tasks.values():
            if _status_eq(task.status, TaskStatus.FAILED):
                failed_tasks.append(
                    {
                        "id": task.id,
                        "description": task.description,
                        "error_message": task.error_message or "unknown error",
                        "required_capabilities": list(task.required_capabilities),
                    }
                )
                blocked_capabilities.update(task.required_capabilities)
            elif _is_success(task.status):
                successful_tasks.append(
                    {
                        "id": task.id,
                        "description": task.description,
                        "result_excerpt": self._result_excerpt(task.result),
                    }
                )

        return {
            "failed_tasks": failed_tasks,
            "successful_tasks": successful_tasks,
            "blocked_capabilities": sorted(blocked_capabilities),
        }

    async def generate_replan(
        self, workflow: Workflow, context: Optional[Dict[str, Any]] = None
    ) -> Workflow:
        """Generate a replacement workflow that avoids previous failure modes.

        Raises:
            ReplanningError: If plan generation times out, fails, or produces
                a plan too similar to the failed one.
        """
        root = self.root_id(workflow.id)
        attempt_number = len(self.replan_history.get(root, [])) + 1

        failure_analysis = self.analyze_failures(workflow)
        if not self.config.preserve_successful_outputs:
            failure_analysis = {**failure_analysis, "successful_tasks": []}
        constraints = self._build_replan_constraints(failure_analysis)

        replan_context = {
            **(context or {}),
            "replan": {
                "is_replan": True,
                "attempt": attempt_number,
                "max_attempts": self.config.max_attempts,
                "previous_workflow_id": workflow.id,
                "failed_tasks": failure_analysis["failed_tasks"],
                "successful_tasks": failure_analysis["successful_tasks"],
                "blocked_capabilities": failure_analysis["blocked_capabilities"],
                "constraints": constraints,
            },
        }

        try:
            new_workflow = await asyncio.wait_for(
                self.decomposer.decompose_request(
                    request=workflow.user_request,
                    context=replan_context,
                    requires_approval=False,  # replans auto-execute
                ),
                timeout=self.config.replan_timeout_seconds,
            )
        except asyncio.TimeoutError:
            raise ReplanningError(
                f"Replanning timed out after {self.config.replan_timeout_seconds}s"
            ) from None
        except Exception as e:
            raise ReplanningError(f"Replanning failed: {e}") from e

        similarity = self._plan_similarity(workflow, new_workflow)
        if similarity >= self.config.plan_similarity_threshold:
            raise ReplanningError(
                f"Generated plan is too similar to the failed plan "
                f"(similarity {similarity:.2f} >= {self.config.plan_similarity_threshold})"
            )

        self._root_ids[new_workflow.id] = root
        self.replan_history.setdefault(root, []).append(
            ReplanAttempt(
                original_workflow_id=root,
                failed_workflow_id=workflow.id,
                new_workflow_id=new_workflow.id,
                attempt_number=attempt_number,
                failure_analysis=failure_analysis,
                constraints_applied=constraints,
            )
        )
        self._prune_history()

        return new_workflow

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prune_history(self) -> None:
        """Drop the oldest replan chains beyond the retention cap."""
        while len(self.replan_history) > _MAX_HISTORY_CHAINS:
            oldest_root = next(iter(self.replan_history))
            attempts = self.replan_history.pop(oldest_root)
            for attempt in attempts:
                self._root_ids.pop(attempt.new_workflow_id, None)

    def _is_replannable_error(self, error_message: Optional[str]) -> bool:
        """Errors that a different plan cannot avoid should not trigger replans."""
        message = (error_message or "").lower()
        return not any(
            pattern.lower() in message for pattern in self.config.non_replannable_error_patterns
        )

    @staticmethod
    def _result_excerpt(result: Any) -> str:
        """Extract a short text excerpt from a task result for replan context."""
        content: Any = result
        if isinstance(result, dict):
            main = result.get("main")
            if isinstance(main, dict) and isinstance(main.get("result"), str):
                content = main["result"]
        text = str(content) if content is not None else ""
        return text[:_RESULT_EXCERPT_CHARS]

    def _build_replan_constraints(self, failure_analysis: Dict[str, Any]) -> List[str]:
        """Turn failure analysis into explicit constraints for the new plan."""
        constraints = [
            "Generate a meaningfully DIFFERENT approach from the failed plan",
        ]
        blocked = failure_analysis.get("blocked_capabilities") or []
        if blocked:
            constraints.append(
                "Avoid approaches that depend on these capabilities, which just "
                f"failed: {', '.join(blocked)}"
            )
        if failure_analysis.get("successful_tasks"):
            constraints.append(
                "Do NOT redo work that already completed successfully; build on "
                "those results instead"
            )
        return constraints

    @staticmethod
    def _plan_signature(workflow: Workflow) -> set:
        """Normalized task signatures used for plan-similarity comparison."""
        signature = set()
        for task in workflow.tasks.values():
            description = re.sub(r"\s+", " ", task.description.strip().lower())
            capabilities = tuple(sorted(c.lower() for c in task.required_capabilities))
            signature.add((description, capabilities))
        return signature

    def _plan_similarity(self, old: Workflow, new: Workflow) -> float:
        """Jaccard similarity between two plans' task signatures (0.0-1.0)."""
        old_sig = self._plan_signature(old)
        new_sig = self._plan_signature(new)
        union = old_sig | new_sig
        if not union:
            return 1.0
        return len(old_sig & new_sig) / len(union)
