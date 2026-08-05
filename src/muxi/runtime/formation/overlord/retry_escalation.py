"""
Async retry escalation ("the honest loop") for failed synchronous chat turns.

When a synchronous turn fails terminally (its in-request retry layers --
task retries, alternate agents, fallbacks -- are exhausted), the runtime
does not simply return the failure. It tells the waiting caller that the
attempt failed and that it will retry asynchronously, keeps the request
tracker entry in ``PROCESSING`` with an ``escalated`` marker, and runs a
bounded chain of background attempts under the same ``request_id``. Each
attempt generates a FRESH plan through the :class:`ReplanningCoordinator`
(similarity-rejected, GBAC-safe) and executes it. The chain ends in either
a real result or an honest, structured give-up report.

This is deliberately NOT a goal-verification loop: "done" is the
workflow's existing success signal. Bounds are liveness- and
attempt-based, not duration-based -- a long attempt is fine, an idle one
is hung (PRD: async-retry-escalation).
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from ...datatypes.response import MuxiResponse
from ...datatypes.workflow import Workflow, WorkflowStatus
from ...services import observability
from ...utils.id_generator import generate_nanoid
from ..background.request_tracker import RequestStatus
from ..workflow.config import ReplanningConfig
from ..workflow.replanning import ReplanningCoordinator, ReplanningError

# Terminal states of an escalation chain (PRD section 6).
TERMINAL_ACHIEVED = "achieved"
TERMINAL_IMPOSSIBLE = "impossible"
TERMINAL_STUCK = "stuck"
TERMINAL_BUDGET_EXHAUSTED = "budget_exhausted"
TERMINAL_ABANDONED = "abandoned"

# Duration strings accepted by retry_async config values ("500ms", "90s",
# "15m", "2h"). Bare numbers are treated as seconds.
_DURATION_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)\s*$")
_DURATION_FACTORS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

# How often the idle watchdog samples the request's last observability
# activity while an attempt runs. Kept well below any realistic
# attempt_idle_timeout; floored so tests with tiny timeouts still poll.
_WATCHDOG_MIN_INTERVAL = 0.05
_WATCHDOG_MAX_INTERVAL = 5.0


class RetryAsyncConfigError(ValueError):
    """Raised for invalid ``overlord.response.retry_async`` configuration."""


def _parse_duration(value: Union[str, int, float], *, key: str) -> float:
    """Parse a duration (``"15m"``, ``"90s"``, ``900``) into seconds."""
    if isinstance(value, bool):
        raise RetryAsyncConfigError(
            f"overlord.response.retry_async.{key} must be a duration, got: {value!r}"
        )
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        match = _DURATION_PATTERN.match(value)
        if not match:
            raise RetryAsyncConfigError(
                f"overlord.response.retry_async.{key} must be a duration like "
                f"'15m', '90s' or '2h', got: {value!r}"
            )
        seconds = float(match.group(1)) * _DURATION_FACTORS[match.group(2)]
    else:
        raise RetryAsyncConfigError(
            f"overlord.response.retry_async.{key} must be a duration, got: {value!r}"
        )
    if seconds <= 0:
        raise RetryAsyncConfigError(
            f"overlord.response.retry_async.{key} must be positive, got: {value!r}"
        )
    return seconds


class RetryAsyncConfig(BaseModel):
    """Configuration for async retry escalation (PRD section 8).

    Defaults are ON with a small budget: escalation is mechanism, and the
    ``max_attempts: 2`` budget bounds spend coarsely until per-request
    cost accounting lands (explicit fast-follow).
    """

    enabled: bool = Field(default=True, description="Enable async retry escalation")
    max_attempts: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Async attempts allowed AFTER the failed sync attempt",
    )
    attempt_idle_timeout_seconds: float = Field(
        default=900.0,
        gt=0,
        description=(
            "Per-attempt liveness bound: an attempt emitting no observability "
            "events for this long is declared hung and counted as failed"
        ),
    )
    deadline_seconds: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Optional hard ceiling for the chain tail. The clock starts when "
            "the SECOND async attempt begins -- the first async retry always "
            "gets an unhurried run"
        ),
    )

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_formation_data(cls, data: Optional[Dict[str, Any]]) -> "RetryAsyncConfig":
        """Build from the ``overlord.response.retry_async`` block.

        Malformed values raise loudly at load time, consistent with the
        rest of the overlord config parsing.
        """
        data = data or {}
        if not isinstance(data, dict):
            raise RetryAsyncConfigError(
                f"overlord.response.retry_async must be a mapping, got: {data!r}"
            )
        unknown = set(data) - {"enabled", "max_attempts", "attempt_idle_timeout", "deadline"}
        if unknown:
            raise RetryAsyncConfigError(
                "overlord.response.retry_async has unknown key(s): " f"{', '.join(sorted(unknown))}"
            )
        kwargs: Dict[str, Any] = {
            "enabled": data.get("enabled", True),
            "max_attempts": data.get("max_attempts", 2),
        }
        if not isinstance(kwargs["enabled"], bool):
            raise RetryAsyncConfigError(
                "overlord.response.retry_async.enabled must be a boolean, "
                f"got: {kwargs['enabled']!r}"
            )
        idle = data.get("attempt_idle_timeout", "15m")
        kwargs["attempt_idle_timeout_seconds"] = _parse_duration(idle, key="attempt_idle_timeout")
        deadline = data.get("deadline")
        if deadline is not None:
            kwargs["deadline_seconds"] = _parse_duration(deadline, key="deadline")
        return cls(**kwargs)


@dataclass
class AttemptRecord:
    """One attempt in an escalation chain (the failed sync attempt is #1)."""

    number: int  # 1-based overall attempt number (1 = the failed sync attempt)
    kind: str  # "sync" | "async"
    plan_summary: str
    failure_reason: str
    failure_signature: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    def to_report_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.number,
            "kind": self.kind,
            "plan_summary": self.plan_summary,
            "failure_reason": self.failure_reason,
        }


@dataclass
class EscalationChain:
    """In-process state of one escalation chain (v1: not restart-durable)."""

    request_id: str
    original_message: str
    user_id: Optional[str]
    session_id: Optional[str]
    webhook_url: Optional[str]
    failed_workflow: Workflow
    attempts: List[AttemptRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    deadline_started_at: Optional[float] = None
    task: Optional[asyncio.Task] = None


def _failure_signature(error_texts: List[str]) -> str:
    """Normalized signature of a failure, for the stuck short-circuit."""
    normalized = sorted(re.sub(r"\s+", " ", (text or "").strip().lower()) for text in error_texts)
    return " | ".join(t for t in normalized if t) or "unknown failure"


def _plan_summary(workflow: Workflow) -> str:
    """One-line deterministic summary of a plan for the give-up report."""
    descriptions = [task.description for task in workflow.tasks.values()]
    summary = "; ".join(d.strip() for d in descriptions if d and d.strip())
    return summary[:500] if summary else "(no plan available)"


def _workflow_error_texts(workflow: Workflow) -> List[str]:
    """Collect failed-task error messages from a workflow."""
    texts = []
    for task in workflow.tasks.values():
        status = task.status.value if hasattr(task.status, "value") else str(task.status)
        if status == "failed":
            texts.append(task.error_message or "unknown error")
    return texts


class RetryEscalationCoordinator:
    """Owns the escalation seam: gate, chain execution, and delivery.

    One instance per overlord. The coordinator reuses the existing
    machinery end-to-end: :class:`ReplanningCoordinator` for
    fundamentally-different plans between attempts,
    ``overlord._execute_workflow`` for attempt execution, the
    ``RequestTracker`` for honest state, and the ``WebhookManager`` /
    ``NotificationRouter`` for terminal delivery.
    """

    def __init__(self, overlord, config: Optional[RetryAsyncConfig] = None):
        self.overlord = overlord
        self.config = config or RetryAsyncConfig()
        self._chains: Dict[str, EscalationChain] = {}

    # ------------------------------------------------------------------
    # Escalation gate (PRD section 5)
    # ------------------------------------------------------------------

    def _non_replannable_patterns(self) -> List[str]:
        """Formation-configured non-replannable patterns (or defaults)."""
        workflow_config = getattr(self.overlord, "workflow_config", None)
        replanning = getattr(workflow_config, "replanning", None)
        if replanning is not None:
            return list(replanning.non_replannable_error_patterns)
        return list(ReplanningConfig().non_replannable_error_patterns)

    def _is_replannable_error(self, error_text: str) -> bool:
        message = (error_text or "").lower()
        return not any(pattern.lower() in message for pattern in self._non_replannable_patterns())

    async def should_escalate(
        self,
        request_id: Optional[str],
        *,
        error_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Decide whether a terminal sync failure escalates (PRD section 5).

        Returns ``(should_escalate, reason)`` -- the reason explains the
        decision either way and is emitted with the gate's event.
        """
        if not self.config.enabled:
            return False, "retry_async.enabled is false"

        if not request_id:
            return False, "no request_id to escalate under"

        tracker = getattr(self.overlord, "active_agent_tracker", None)
        if tracker is not None and getattr(tracker, "overlord_shutting_down", False):
            return False, "formation is shutting down"

        if request_id in self._chains:
            return False, "request is already an escalated retry"

        metadata = metadata or {}
        if metadata.get("cancelled"):
            return False, "request was cancelled by the user"

        # Pending interactions (clarification, approval, credential prompts)
        # are conversations, not failures.
        from .chat_orchestrator import PENDING_INTERACTION_KEYS

        if any(metadata.get(key) for key in PENDING_INTERACTION_KEYS):
            return False, "turn ended as a pending interaction"

        request_tracker = getattr(self.overlord, "request_tracker", None)
        if request_tracker is None:
            return False, "no request tracker available"
        if request_tracker.is_cancelled(request_id):
            return False, "request was cancelled by the user"
        state = await request_tracker.get_request(request_id)
        if state is not None and state.status == RequestStatus.CANCELLED:
            return False, "request was cancelled by the user"

        if not self._is_replannable_error(error_text):
            return False, (
                "failure matches non_replannable_error_patterns "
                "(a different plan hits the same wall)"
            )

        if getattr(self.overlord, "task_decomposer", None) is None:
            return False, "no task decomposer available for replanning"

        return True, "terminal sync failure is retryable with a different plan"

    # ------------------------------------------------------------------
    # Escalation entry point
    # ------------------------------------------------------------------

    async def maybe_escalate(
        self,
        request_id: Optional[str],
        *,
        user_id: Optional[str],
        session_id: Optional[str],
        original_message: Optional[str],
        error_text: str,
        failed_workflow: Optional[Workflow] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[MuxiResponse]:
        """Gate a terminal sync failure and, if it passes, escalate it.

        Returns the escalation response the caller should deliver to the
        waiting client (fixed protocol text -- never persona/LLM-styled),
        or ``None`` when the failure must be returned exactly as today.
        """
        should, reason = await self.should_escalate(
            request_id, error_text=error_text, metadata=metadata
        )
        if not should:
            return None

        state = await self.overlord.request_tracker.get_request(request_id)
        webhook_url = getattr(state, "webhook_url", None) if state else None
        message = original_message or (getattr(state, "original_message", None) if state else None)
        if not message:
            message = "(original request unavailable)"

        workflow = failed_workflow or self._synthetic_failed_workflow(message, error_text)

        chain = EscalationChain(
            request_id=request_id,
            original_message=message,
            user_id=user_id,
            session_id=session_id,
            webhook_url=webhook_url,
            failed_workflow=workflow,
        )
        chain.attempts.append(
            AttemptRecord(
                number=1,
                kind="sync",
                plan_summary=_plan_summary(workflow),
                failure_reason=error_text,
                failure_signature=_failure_signature(
                    _workflow_error_texts(workflow) or [error_text]
                ),
                ended_at=time.time(),
            )
        )
        self._chains[request_id] = chain

        # Keep the tracker entry PROCESSING with the escalated marker so
        # pollers see the chain in flight and the stale reaper leaves the
        # entry alone while the chain task is alive.
        if state is not None:
            state.escalated = True
        else:
            # The failure site may run after the tracker entry was never
            # created (defensive) -- track one so polling works.
            from ..background.request_tracker import RequestState

            new_state = RequestState(
                id=request_id,
                status=RequestStatus.PROCESSING,
                start_time=time.time(),
                original_message=message,
                user_id=user_id,
                session_id=session_id,
                webhook_url=webhook_url,
            )
            new_state.escalated = True
            await self.overlord.request_tracker.track_request(request_id, new_state)
            state = new_state

        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_RETRY_ESCALATED,
            level=observability.EventLevel.INFO,
            data={
                "request_id": request_id,
                "sync_failure_reason": error_text,
                "gate_reason": reason,
                "max_attempts": self.config.max_attempts,
                "delivery": self._delivery_mode(chain),
            },
            description=(
                f"Sync failure escalated to async retry for request {request_id}: {error_text}"
            ),
        )

        chain.task = self.overlord._create_tracked_task(
            self._run_chain(chain), name=f"retry_escalation_{request_id}"
        )
        state.task_ref = chain.task

        return MuxiResponse(
            role="assistant",
            content=self.escalation_message(chain),
            metadata={
                "escalated": True,
                "request_id": request_id,
                "session_id": session_id,
                "delivery": self._delivery_mode(chain),
            },
        )

    def _delivery_mode(self, chain: EscalationChain) -> str:
        """Which terminal delivery applies to this chain (PRD section 7)."""
        if getattr(self.overlord, "notification_router", None) is not None:
            return "channel"
        if chain.webhook_url:
            return "webhook"
        return "polling"

    def escalation_message(self, chain: EscalationChain) -> str:
        """The fixed protocol message delivered to the waiting caller.

        Deterministic text by design: it is a protocol statement, not a
        conversational reply, so it is never routed through the persona
        or any LLM.
        """
        delivery = self._delivery_mode(chain)
        if delivery == "channel":
            how = "I'll notify you on your channel when it resolves."
        elif delivery == "webhook":
            how = "You'll receive a webhook notification when it resolves."
        else:
            how = f"Poll GET /v1/requests/{chain.request_id} for the outcome."
        return (
            "This has failed. I'm going to retry with a different approach and "
            f"let you know asynchronously. Your request ID is {chain.request_id}. {how}"
        )

    def _synthetic_failed_workflow(self, message: str, error_text: str) -> Workflow:
        """Build a minimal failed Workflow when the sync failure produced none.

        Non-workflow failures (an exception before/without decomposition)
        still escalate: the replan coordinator only needs a failed plan to
        anchor the re-decomposition, and this one-task stand-in carries
        the user request and the observed failure.
        """
        from ...datatypes.task_status import TaskStatus
        from ...datatypes.workflow import SubTask

        task = SubTask(
            id="task_1",
            description=(message or "user request")[:500],
            required_capabilities=["general"],
            status=TaskStatus.FAILED,
            error_message=(error_text or "unknown error")[:500],
        )
        return Workflow(
            id=f"wrk_{generate_nanoid()}",
            user_request=message or "user request",
            tasks={"task_1": task},
            status=WorkflowStatus.FAILED,
        )

    # ------------------------------------------------------------------
    # Chain execution
    # ------------------------------------------------------------------

    def _make_replanner(self) -> ReplanningCoordinator:
        """A chain-local replanning coordinator, always enabled.

        Independent from the executor's coordinator (which stays governed
        by ``overlord.workflow.replanning``): escalation replans are the
        feature, not an option. Non-replannable patterns and the
        similarity threshold follow the formation's replanning config
        when present.
        """
        workflow_config = getattr(self.overlord, "workflow_config", None)
        base = getattr(workflow_config, "replanning", None) or ReplanningConfig()
        config = base.model_copy(
            update={"enabled": True, "max_attempts": max(self.config.max_attempts, 1)}
        )
        return ReplanningCoordinator(decomposer=self.overlord.task_decomposer, config=config)

    async def _run_chain(self, chain: EscalationChain) -> None:
        """Run the bounded background attempt chain to a terminal state."""
        request_id = chain.request_id

        # Attempts run outside the original request's context; re-establish
        # it so observability events (and the idle watchdog fed by them)
        # correlate under the same request_id.
        from ...services.observability.context import RequestContext, set_request_context

        set_request_context(
            RequestContext(
                id=request_id,
                user_id=chain.user_id,
                session_id=chain.session_id,
                formation_id=getattr(self.overlord, "formation_id", "unknown"),
            )
        )

        replanner = self._make_replanner()
        previous_workflow = chain.failed_workflow

        try:
            for async_attempt in range(1, self.config.max_attempts + 1):
                overall_attempt = async_attempt + 1  # the failed sync attempt is #1

                if await self._is_abandoned(request_id):
                    await self._finish_abandoned(chain)
                    return

                # Deadline (PRD section 4): the clock starts when the second
                # async attempt begins -- the first async retry runs unhurried.
                if async_attempt == 2 and self.config.deadline_seconds is not None:
                    chain.deadline_started_at = time.time()
                if self._deadline_exceeded(chain):
                    await self._finish_failed(
                        chain, TERMINAL_BUDGET_EXHAUSTED, detail="deadline exceeded"
                    )
                    return

                # Replan: a fundamentally different approach, or a stuck
                # short-circuit when no different approach exists and the
                # failure is not changing.
                #
                # The planning step is bounded by the chain itself, not just
                # by the replanner's internal decompose timeout: planning is
                # one LLM interaction, so attempt_idle_timeout (generous
                # enough for silent execution gaps) bounds it too, capped by
                # whatever remains of the deadline once its clock is
                # running. Without this, a stalled decomposer would hang the
                # chain PROCESSING forever with a live task_ref -- which the
                # stale reaper deliberately exempts.
                planning_timeout = self.config.attempt_idle_timeout_seconds
                deadline_remaining = self._deadline_remaining(chain)
                if deadline_remaining is not None:
                    planning_timeout = min(planning_timeout, max(deadline_remaining, 0.001))
                try:
                    new_workflow = await asyncio.wait_for(
                        replanner.generate_replan(
                            previous_workflow,
                            context={
                                "user_id": chain.user_id,
                                "session_id": chain.session_id,
                                "request_id": request_id,
                                "escalated_retry": True,
                            },
                        ),
                        timeout=planning_timeout,
                    )
                except asyncio.TimeoutError:
                    if self._deadline_exceeded(chain):
                        await self._finish_failed(
                            chain,
                            TERMINAL_BUDGET_EXHAUSTED,
                            detail="deadline exceeded during replanning",
                        )
                        return
                    # A hung planner consumes an attempt like any other
                    # failure; the signature carries over so a subsequent
                    # similarity rejection still feeds the stuck logic.
                    chain.attempts.append(
                        AttemptRecord(
                            number=overall_attempt,
                            kind="async",
                            plan_summary="(replanning timed out)",
                            failure_reason=(f"replanning timed out after {planning_timeout:.0f}s"),
                            failure_signature=chain.attempts[-1].failure_signature,
                            ended_at=time.time(),
                        )
                    )
                    continue
                except ReplanningError as exc:
                    similarity_rejected = "too similar" in str(exc).lower()
                    if similarity_rejected and self._same_signature_as_previous(chain):
                        await self._finish_failed(
                            chain,
                            TERMINAL_STUCK,
                            detail=(
                                "replanning could not produce a meaningfully different "
                                "plan and the failure is not changing; further attempts "
                                "were judged futile"
                            ),
                        )
                        return
                    # Replan failure consumes an attempt: the plan produced
                    # nothing new, so its failure signature carries over.
                    chain.attempts.append(
                        AttemptRecord(
                            number=overall_attempt,
                            kind="async",
                            plan_summary="(replanning produced no executable plan)",
                            failure_reason=f"replanning failed: {exc}",
                            failure_signature=chain.attempts[-1].failure_signature,
                            ended_at=time.time(),
                        )
                    )
                    continue

                record = AttemptRecord(
                    number=overall_attempt,
                    kind="async",
                    plan_summary=_plan_summary(new_workflow),
                    failure_reason="",
                    failure_signature="",
                )
                chain.attempts.append(record)

                observability.observe(
                    event_type=observability.ConversationEvents.RESPONSE_RETRY_ATTEMPT,
                    level=observability.EventLevel.INFO,
                    data={
                        "request_id": request_id,
                        "attempt": overall_attempt,
                        "async_attempt": async_attempt,
                        "max_attempts": self.config.max_attempts,
                        "plan_id": new_workflow.id,
                        "plan_summary": record.plan_summary,
                    },
                    description=(
                        f"Async retry attempt {async_attempt}/{self.config.max_attempts} "
                        f"for request {request_id} (plan {new_workflow.id})"
                    ),
                )

                result, hung = await self._execute_attempt(chain, new_workflow)
                record.ended_at = time.time()

                if await self._is_abandoned(request_id):
                    await self._finish_abandoned(chain)
                    return

                if hung:
                    record.failure_reason = (
                        "attempt declared hung: no observability activity for "
                        f"{self.config.attempt_idle_timeout_seconds:.0f}s"
                    )
                    record.failure_signature = "attempt hung (idle timeout)"
                    previous_workflow = new_workflow
                    continue

                success, error_texts = self._evaluate_attempt(result, new_workflow)
                if success:
                    await self._finish_achieved(chain, result, overall_attempt)
                    return

                record.failure_reason = "; ".join(error_texts)[:1000] or "attempt failed"
                record.failure_signature = _failure_signature(error_texts)

                # Hard blocker: a failure a different plan cannot avoid names
                # the terminal state (PRD: impossible, with the blocker).
                blocker = self._named_blocker(error_texts)
                if blocker:
                    await self._finish_failed(chain, TERMINAL_IMPOSSIBLE, detail=blocker)
                    return

                previous_workflow = self._latest_workflow(new_workflow)

            await self._finish_failed(
                chain,
                TERMINAL_BUDGET_EXHAUSTED,
                detail=f"all {self.config.max_attempts} async attempt(s) failed",
            )
        except asyncio.CancelledError:
            # DELETE /v1/requests/{id} mid-chain (or shutdown) cancelled the
            # chain task: end honestly as abandoned, then re-raise so the
            # cancellation completes cooperatively (#314 semantics).
            await self._finish_abandoned(chain)
            raise
        except Exception as exc:  # never let the chain die silently
            await self._finish_failed(
                chain,
                TERMINAL_BUDGET_EXHAUSTED,
                detail=f"escalation chain crashed: {exc}",
            )
        finally:
            # Belt-and-braces terminal guarantee: NO exit path -- including
            # a failure inside the terminal handlers themselves -- may
            # leave the tracker entry PROCESSING+escalated, because the
            # stale reaper exempts escalated entries while the chain task
            # is alive and this task is about to end.
            await self._ensure_terminal_state(chain)

    async def _ensure_terminal_state(self, chain: EscalationChain) -> None:
        """Last-resort guard: force a terminal state if none was recorded.

        Runs in the chain task's outermost ``finally``. Normal exits have
        already recorded COMPLETED/FAILED/CANCELLED and this is a no-op;
        if the chain (or one of its terminal handlers) died without doing
        so, the entry is failed honestly with a report naming the internal
        error. Never raises.
        """
        try:
            tracker = self.overlord.request_tracker
            state = await tracker.get_request(chain.request_id)
            if state is not None and state.status in (
                RequestStatus.PENDING,
                RequestStatus.PROCESSING,
                RequestStatus.RUNNING,
            ):
                report = self.build_report(
                    chain,
                    TERMINAL_BUDGET_EXHAUSTED,
                    detail=(
                        "escalation chain exited without recording a terminal "
                        "state (internal error)"
                    ),
                )
                await tracker.update_request(
                    chain.request_id,
                    RequestStatus.FAILED,
                    result=report,
                    error="async retry gave up (internal error in escalation chain)",
                )
                self._emit_terminal(chain, TERMINAL_BUDGET_EXHAUSTED)
        except Exception:
            # The guard itself must never mask the original exit path.
            pass
        finally:
            self._chains.pop(chain.request_id, None)

    async def _execute_attempt(
        self, chain: EscalationChain, workflow: Workflow
    ) -> Tuple[Optional[MuxiResponse], bool]:
        """Execute one attempt with liveness (idle) and deadline supervision.

        Returns ``(result, hung)``. ``result`` is None when the attempt was
        cancelled by the watchdog (hung or past the deadline).
        """
        request_id = chain.request_id
        observability.watch_request_activity(request_id)
        attempt_task = asyncio.ensure_future(
            self.overlord._execute_workflow(
                workflow=workflow,
                message=chain.original_message,
                user_id=chain.user_id or "0",
                session_id=chain.session_id,
                request_id=request_id,
                stream=False,
            )
        )

        idle_timeout = self.config.attempt_idle_timeout_seconds
        poll = min(max(idle_timeout / 4.0, _WATCHDOG_MIN_INTERVAL), _WATCHDOG_MAX_INTERVAL)
        hung = False
        try:
            while True:
                done, _ = await asyncio.wait({attempt_task}, timeout=poll)
                if done:
                    return attempt_task.result(), False

                if await self._is_abandoned(request_id):
                    break  # caller handles the abandoned terminal

                last_activity = observability.get_last_request_activity(request_id)
                if last_activity is not None and (time.time() - last_activity) > idle_timeout:
                    hung = True
                    break

                if self._deadline_exceeded(chain):
                    break
            attempt_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(attempt_task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            return None, hung
        finally:
            observability.unwatch_request_activity(request_id)

    def _evaluate_attempt(
        self, result: Optional[MuxiResponse], workflow: Workflow
    ) -> Tuple[bool, List[str]]:
        """Judge an attempt by the workflow's existing success signal."""
        if result is None:
            return False, ["attempt was cancelled before completing"]

        metadata = getattr(result, "metadata", None) or {}
        workflow_status = str(metadata.get("workflow_status", "")).lower()
        if workflow_status == "failed" or metadata.get("error"):
            texts = _workflow_error_texts(self._latest_workflow(workflow))
            if not texts and metadata.get("error"):
                texts = [str(metadata["error"])]
            return False, texts or ["workflow failed"]
        return True, []

    def _latest_workflow(self, workflow: Workflow) -> Workflow:
        """Fetch the executed (task-status-bearing) workflow when tracked."""
        tracked = self.overlord.get_workflow_status(workflow.id)
        return tracked or workflow

    def _named_blocker(self, error_texts: List[str]) -> Optional[str]:
        """A non-replannable failure surfaced mid-chain names the blocker."""
        for text in error_texts:
            lowered = (text or "").lower()
            for pattern in self._non_replannable_patterns():
                if pattern.lower() in lowered:
                    return text
        return None

    def _same_signature_as_previous(self, chain: EscalationChain) -> bool:
        """Does the latest failure signature match the attempt before it?

        With a single recorded failure (the sync attempt) there is no
        previous pair to compare, so the first similarity rejection
        consumes an attempt instead of short-circuiting; the next
        rejection with an unchanged signature ends the chain as stuck.
        """
        if len(chain.attempts) < 2:
            return False
        return chain.attempts[-1].failure_signature == chain.attempts[-2].failure_signature

    def _deadline_exceeded(self, chain: EscalationChain) -> bool:
        if self.config.deadline_seconds is None or chain.deadline_started_at is None:
            return False
        return (time.time() - chain.deadline_started_at) > self.config.deadline_seconds

    def _deadline_remaining(self, chain: EscalationChain) -> Optional[float]:
        """Seconds left on the deadline, or None while its clock is off.

        Used to cap the planning step between attempts: once the deadline
        clock is running (second async attempt onward), replanning may not
        outlive it.
        """
        if self.config.deadline_seconds is None or chain.deadline_started_at is None:
            return None
        return self.config.deadline_seconds - (time.time() - chain.deadline_started_at)

    async def _is_abandoned(self, request_id: str) -> bool:
        tracker = self.overlord.request_tracker
        if tracker.is_cancelled(request_id):
            return True
        state = await tracker.get_request(request_id)
        return state is not None and state.status == RequestStatus.CANCELLED

    # ------------------------------------------------------------------
    # Terminals (PRD section 6)
    # ------------------------------------------------------------------

    def build_report(self, chain: EscalationChain, state: str, detail: str) -> Dict[str, Any]:
        """The structured give-up report -- a first-class artifact.

        Per-attempt plan summaries and failure reasons plus a
        deterministic what-would-unblock section. Never LLM-generated.
        """
        distinct_failures = sorted({a.failure_reason for a in chain.attempts if a.failure_reason})
        if state == TERMINAL_IMPOSSIBLE:
            unblock = f"Resolve the blocker: {detail}"
        elif state == TERMINAL_STUCK:
            unblock = (
                "Provide a different way to accomplish this (the available "
                "capabilities keep producing the same failure): " + "; ".join(distinct_failures)
            )
        else:
            unblock = (
                "Address the underlying failure(s) and resubmit: " + "; ".join(distinct_failures)
                if distinct_failures
                else "Resubmit the request"
            )
        return {
            "state": state,
            "detail": detail,
            "request_id": chain.request_id,
            "original_message": chain.original_message,
            "attempts": [a.to_report_dict() for a in chain.attempts],
            "what_would_unblock": unblock,
            "wall_time_seconds": round(time.time() - chain.started_at, 3),
        }

    async def _finish_achieved(
        self, chain: EscalationChain, result: MuxiResponse, attempt_number: int
    ) -> None:
        content = getattr(result, "content", None) or str(result)
        await self.overlord.request_tracker.update_request(
            chain.request_id, RequestStatus.COMPLETED, result=content
        )
        message = (
            f"Your earlier request succeeded on retry (attempt {attempt_number}).\n\n{content}"
        )
        await self._deliver_terminal(
            chain, TERMINAL_ACHIEVED, message=message, result=content, attempt=attempt_number
        )
        self._emit_terminal(chain, TERMINAL_ACHIEVED)
        self._chains.pop(chain.request_id, None)

    async def _finish_failed(self, chain: EscalationChain, state: str, detail: str) -> None:
        report = self.build_report(chain, state, detail)
        # The report rides the tracker entry's result so GET
        # /v1/requests/{id} answers with it for escalated FAILED entries.
        await self.overlord.request_tracker.update_request(
            chain.request_id,
            RequestStatus.FAILED,
            result=report,
            error=f"async retry gave up ({state}): {detail}",
        )
        message = self._render_report_text(report)
        await self._write_captains_log(chain, report)
        await self._deliver_terminal(chain, state, message=message, report=report)
        self._emit_terminal(chain, state)
        self._chains.pop(chain.request_id, None)

    async def _finish_abandoned(self, chain: EscalationChain) -> None:
        report = self.build_report(
            chain, TERMINAL_ABANDONED, detail="request was cancelled mid-chain"
        )
        await self.overlord.request_tracker.update_request(
            chain.request_id, RequestStatus.CANCELLED, result=report
        )
        # No push delivery: the DELETE response was the acknowledgement
        # (cooperative-cancel semantics, #314).
        self._emit_terminal(chain, TERMINAL_ABANDONED)
        self._chains.pop(chain.request_id, None)

    def _render_report_text(self, report: Dict[str, Any]) -> str:
        """Deterministic plain-text rendering of the give-up report."""
        lines = [
            f"I could not complete your request ({report['state']}): {report['detail']}",
            "",
            "What was tried:",
        ]
        for attempt in report["attempts"]:
            lines.append(
                f"- Attempt {attempt['attempt']} ({attempt['kind']}): "
                f"{attempt['plan_summary']} -> {attempt['failure_reason'] or 'failed'}"
            )
        lines.append("")
        lines.append(f"What would unblock this: {report['what_would_unblock']}")
        return "\n".join(lines)

    def _emit_terminal(self, chain: EscalationChain, state: str) -> None:
        observability.observe(
            event_type=observability.ConversationEvents.RESPONSE_RETRY_TERMINAL,
            level=(
                observability.EventLevel.INFO
                if state == TERMINAL_ACHIEVED
                else observability.EventLevel.WARNING
            ),
            data={
                "request_id": chain.request_id,
                "state": state,
                "attempts": len(chain.attempts),
                "wall_time_seconds": round(time.time() - chain.started_at, 3),
            },
            description=(
                f"Async retry chain for request {chain.request_id} ended: {state} "
                f"after {len(chain.attempts)} attempt(s)"
            ),
        )

    # ------------------------------------------------------------------
    # Delivery (PRD section 7)
    # ------------------------------------------------------------------

    async def _deliver_terminal(
        self,
        chain: EscalationChain,
        state: str,
        *,
        message: str,
        result: Optional[str] = None,
        report: Optional[Dict[str, Any]] = None,
        attempt: Optional[int] = None,
    ) -> None:
        """Terminal delivery precedence: channel -> webhook -> polling.

        Delivery failures never change chain state: the tracker entry is
        already terminal and GET /v1/requests/{id} always answers.
        """
        router = getattr(self.overlord, "notification_router", None)
        if router is not None and chain.user_id:
            try:
                outcome = await router.notify(
                    user_id=chain.user_id,
                    message=message,
                    channels=None,  # preferred channel = where the request arrived
                    request_id=chain.request_id,
                    source="retry_escalation",
                )
                if outcome.get("delivered"):
                    return
            except Exception as exc:
                observability.observe(
                    event_type=observability.ConversationEvents.NOTIFICATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    data={"request_id": chain.request_id, "error": str(exc)},
                    description="Retry-escalation channel notification failed",
                )

        if chain.webhook_url:
            await self._send_webhook(chain, state, result=result, report=report)

    async def _send_webhook(
        self,
        chain: EscalationChain,
        state: str,
        *,
        result: Optional[str],
        report: Optional[Dict[str, Any]],
    ) -> None:
        """POST the terminal payload, HMAC-signed with the client key.

        Payload (PRD section 7.1): ``{request_id, state, result | report,
        attempts, timestamp}``. Signed over the canonical body with the
        formation's client key so receivers can verify origin. Bounded
        retries live in the WebhookManager; permanent failure emits a
        warning event and never touches chain state.
        """
        payload: Dict[str, Any] = {
            "request_id": chain.request_id,
            "state": state,
            "attempts": len(chain.attempts),
            "timestamp": time.time(),
        }
        if state == TERMINAL_ACHIEVED:
            payload["result"] = result
        else:
            payload["report"] = report

        try:
            delivered = await self.overlord.webhook_manager.deliver_signed_payload(
                webhook_url=chain.webhook_url,
                payload=payload,
                request_id=chain.request_id,
                signing_secret=getattr(self.overlord, "client_api_key", None) or "",
                delivery_type="retry_escalation",
            )
        except Exception as exc:
            delivered = False
            observability.observe(
                event_type=observability.ConversationEvents.WEBHOOK_FAILED,
                level=observability.EventLevel.WARNING,
                data={"request_id": chain.request_id, "error": str(exc)},
                description="Retry-escalation webhook delivery raised",
            )
        if not delivered:
            observability.observe(
                event_type=observability.ConversationEvents.WEBHOOK_FAILED,
                level=observability.EventLevel.WARNING,
                data={"request_id": chain.request_id, "state": state},
                description=(
                    "Retry-escalation webhook could not be delivered; result "
                    f"remains available via GET /v1/requests/{chain.request_id}"
                ),
            )

    async def _write_captains_log(self, chain: EscalationChain, report: Dict[str, Any]) -> None:
        """Append the give-up report to the Captain's Log (best-effort).

        Deterministic write through the event-apply path: today's entry
        for the user gains a decision line; existing sections are
        preserved. Formations without a captain's log skip silently.
        """
        captains_log = getattr(self.overlord, "captains_log", None)
        if captains_log is None or chain.user_id is None:
            return
        try:
            today = date_type.today()
            existing = await captains_log.storage.get_entry(str(chain.user_id), today) or {}
            failures = "; ".join(
                a["failure_reason"] for a in report["attempts"] if a["failure_reason"]
            )
            line = (
                f"Async retry gave up ({report['state']}) on request "
                f"{chain.request_id}: {report['detail']}. "
                f"Tried {len(report['attempts'])} attempt(s): {failures}. "
                f"Unblock: {report['what_would_unblock']}"
            )
            decisions = list(existing.get("decisions") or []) + [line]
            await captains_log.apply_log_entry_event(
                str(chain.user_id),
                {
                    "date": today.isoformat(),
                    "summary": existing.get("summary"),
                    "decisions": decisions,
                    "projects": existing.get("projects"),
                    "context": existing.get("context"),
                },
            )
        except Exception as exc:
            observability.observe(
                event_type=observability.ErrorEvents.MEMORY_OPERATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={"request_id": chain.request_id, "error": str(exc)},
                description="Failed to write retry give-up report to captain's log",
            )
