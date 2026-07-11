"""
WatchService: tracked poll loops over MCP tools (remote async tools).

The one new primitive of the remote-async-tools PRD: an agent that
recognizes a job-shaped tool response ("{job_id, status: processing}")
registers a watch; a deterministic poll loop calls the named MCP tool at
the formation-configured cadence until a mechanical ``done_when``
selector matches, then re-enters the conversation with the fenced
result. No LLM in the poll loop -- polls cost zero tokens.

Hard contracts (PRD D1-D8):
- ``watch_job`` is ALWAYS asynchronous (D3): it registers the watch and
  returns a job handle immediately; there is no blocking mode and none
  will be added.
- ``done_when`` is deterministic (D4): a selector path plus
  ``equals``/``in``, evaluated mechanically against the poll body.
- Polls run under the ORIGINAL user's stored GBAC context (D5): the
  request-scoped permissions and middleware groups are captured at watch
  creation and restored around every poll; a user who cannot call the
  tool cannot watch it (checked at creation AND per poll -- permission
  loss fails the watch, fail-closed).
- Completion re-enters the conversation through the delegation-style
  pipeline (D7): ``route_class: watch`` traverses the same middleware +
  RBAC path heartbeats and delegations use, with the payload wrapped in
  the runtime #274 untrusted-content fencing. Delivery follows D6: the
  proactiveness NotificationRouter (user channel > formation default).
- Watches are tracked jobs (D8): listed and cancellable on /jobs,
  orphan-marked on boot/shutdown, per-user concurrency clamped (group
  templates may raise the quota; the highest of the user's groups wins).

Follows the DelegationService lifecycle idiom: in-memory job tracking
always, write-through to the ``watch_jobs`` table when persistent memory
exists. Poll loops do not survive restarts (the GBAC context is
request-scoped and never persisted); rows stuck in ``watching`` are
marked ``orphaned`` on boot.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...formation.background.transformers import extract_path
from ...utils.datetime_utils import utc_now_naive
from ...utils.fencing import UNTRUSTED_FENCE_INSTRUCTION, fence_untrusted
from .. import observability
from ..gbac import enforcement as gbac_enforcement
from .config import WatchConfig
from .models import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_ORPHANED,
    STATUS_TIMED_OUT,
    STATUS_WATCHING,
    TERMINAL_STATUSES,
    WatchJobRecord,
)

# Bounded captures: poll bodies can be large (full render metadata etc.).
MAX_RESULT_CHARS = 100_000
MAX_ERROR_CHARS = 4_000


def _normalize_user(user_id: Any) -> str:
    """Match the chat path's user id normalization (lowercase, '0' default)."""
    if user_id is None:
        return "0"
    normalized = str(user_id).lower().strip()
    return normalized or "0"


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _values_match(actual: Any, expected: Any) -> bool:
    """Deterministic comparison for done_when: exact, or string-form equal.

    Strictly typed for booleans: Python's ``1 == True`` / ``0 == False``
    coercion would let a boolean spec value match a numeric result (and
    vice versa), breaking determinism -- a bool matches ONLY a bool.
    The string-form fallback keeps ``equals: "3"`` matching a numeric 3
    (JSON bodies vary) without any fuzzy semantics.
    """
    if isinstance(actual, bool) != isinstance(expected, bool):
        return False
    if actual == expected:
        return True
    return str(actual) == str(expected)


@dataclass
class WatchJob:
    """In-memory record of one tracked watch."""

    job_id: str
    user_id: str
    agent_id: str
    server_id: str
    tool_name: str
    args: Dict[str, Any]
    done_when_path: str
    done_when_equals: Any = None
    done_when_in: Optional[List[Any]] = None
    result_selector: Optional[str] = None
    label: Optional[str] = None
    originating_session_id: Optional[str] = None
    status: str = STATUS_WATCHING
    polls: int = 0
    consecutive_failures: int = 0
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: Any = field(default_factory=utc_now_naive)
    completed_at: Any = None
    reentry_at: Any = None
    cancel_requested: bool = False
    trail: List[Dict[str, str]] = field(default_factory=list)
    # Stored GBAC context (D5): captured at creation, restored per poll.
    # Never persisted -- a restart orphans the watch instead of guessing.
    permissions: Any = None
    request_groups: Optional[Tuple[str, ...]] = None

    @property
    def watched(self) -> str:
        return f"{self.server_id}.{self.tool_name}"

    def record(self, action: str) -> None:
        self.trail.append({"timestamp": utc_now_naive().isoformat(), "action": action})

    def to_public_dict(self) -> Dict[str, Any]:
        """The /jobs- and tool-facing shape."""
        return {
            "id": self.job_id,
            "kind": "watch",
            "title": self.label or f"Watching {self.watched}",
            "status": self.status,
            "tool": self.watched,
            "polls": self.polls,
            "created_at": _iso(self.created_at),
            "completed_at": _iso(self.completed_at),
            "result_preview": (self.result or "")[:200] or None,
            "error": self.error,
        }


class WatchService:
    """Tracked MCP-tool watches for one formation."""

    def __init__(self, config: WatchConfig, overlord: Any):
        self.config = config
        self.overlord = overlord
        self.formation_id = getattr(overlord, "formation_id", "default-formation")
        self._jobs: Dict[str, WatchJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._stopping = False

        self._async_session_maker = None
        db_manager = getattr(overlord, "db_manager", None)
        if db_manager is not None and getattr(db_manager, "AsyncSession", None):
            self._async_session_maker = db_manager.AsyncSession

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Mark orphans from a previous run (poll loops never survive one)."""
        await self._mark_orphans_on_boot()

    async def stop(self) -> None:
        """Cancel poll loops and orphan the in-memory watching jobs."""
        self._stopping = True
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        for job in self._jobs.values():
            if job.status == STATUS_WATCHING:
                job.status = STATUS_ORPHANED
                job.completed_at = utc_now_naive()
                job.error = "runtime shutdown while the watch was active"
                job.record("orphaned (runtime shutdown)")
                self._observe(observability.ConversationEvents.WATCH_ORPHANED, job)
                await self._persist(job)

    async def _mark_orphans_on_boot(self) -> None:
        """Rows stuck in ``watching`` belong to a dead process: mark orphaned."""
        if self._async_session_maker is None:
            return
        try:
            from sqlalchemy import select

            async with self._async_session_maker() as session:
                rows = (
                    (
                        await session.execute(
                            select(WatchJobRecord).where(
                                WatchJobRecord.formation_id == self.formation_id,
                                WatchJobRecord.status == STATUS_WATCHING,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    row.status = STATUS_ORPHANED
                    row.error = "runtime restarted while the watch was active"
                    row.completed_at = utc_now_naive()
                    observability.observe(
                        event_type=observability.ConversationEvents.WATCH_ORPHANED,
                        level=observability.EventLevel.WARNING,
                        data={
                            "job_id": row.id,
                            "user_id": row.user_id,
                            "server_id": row.server_id,
                            "tool_name": row.tool_name,
                        },
                        description=(
                            f"Watch {row.id} orphaned: runtime restarted while it was active"
                        ),
                    )
                await session.commit()
        except Exception as e:
            self._observe_persistence_warning("mark_orphans", e)

    # ------------------------------------------------------------------
    # Watch registration (always async -- hard requirement, D3)
    # ------------------------------------------------------------------

    def _effective_max_concurrent(self, permissions: Any) -> int:
        """The per-user watch quota: highest group override, else formation.

        Grants are additive (same semantics as every other GBAC list):
        a user in multiple groups gets the HIGHEST of their groups'
        ``mcp.watch.max_concurrent`` values; no group value = formation
        default. This quota governs watches ONLY.
        """
        override = getattr(permissions, "watch_max_concurrent", None) if permissions else None
        if isinstance(override, int) and override >= 1:
            return override
        return self.config.max_concurrent

    def _visible_tool_registry(self, agent_id: str) -> Dict[str, Dict[str, Any]]:
        """The agent's per-server tool registry under the CURRENT GBAC context.

        The same inherited-view + group-cascade narrowing the per-turn
        tool surface uses (agent.py), so watch-time visibility can never
        disagree with call-time visibility.
        """
        mcp_service = getattr(self.overlord, "mcp_service", None)
        if mcp_service is None:
            return {}
        registry = mcp_service.get_tool_registry(agent_id) or {}
        agent_registries = getattr(mcp_service, "agent_tool_registry", None) or {}
        shared = agent_registries.get("_shared")
        return gbac_enforcement.effective_tool_registry(
            agent_id,
            registry,
            catalogs=(
                shared if shared is not None else getattr(mcp_service, "tool_registry", None)
            ),
        )

    def _resolve_tool(self, agent_id: str, tool: str) -> Optional[Tuple[str, str]]:
        """Resolve a tool reference to (server_id, tool_name), or None.

        Accepts ``server__tool`` (the LLM-facing prefixed name),
        ``server.tool`` (the PRD form), and a bare tool name (resolved
        against every server the agent can see). Resolution happens
        against the caller's effective (GBAC-narrowed) registry, so a
        tool the user cannot call resolves to None -- fail closed.
        """
        registry = self._visible_tool_registry(agent_id)
        if not registry:
            return None

        candidates: List[Tuple[str, str]] = []
        if "__" in tool:
            server_id, tool_name = tool.split("__", 1)
            candidates.append((server_id, tool_name))
        if "." in tool:
            server_id, tool_name = tool.split(".", 1)
            candidates.append((server_id, tool_name))
        for server_id, tool_name in candidates:
            if tool_name in (registry.get(server_id) or {}):
                return server_id, tool_name

        # Bare tool name: first server exposing it (deterministic order).
        for server_id in sorted(registry):
            if tool in registry[server_id]:
                return server_id, tool
        return None

    async def watch(
        self,
        *,
        agent_id: str,
        user_id: Any,
        tool: Any,
        args: Any = None,
        done_when: Any = None,
        result: Any = None,
        label: Any = None,
        originating_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register one watch and return immediately with a job handle.

        Never blocks on a poll and never raises: every rejection is a
        friendly ``{"success": False, "error": ...}`` dict the model can
        act on.
        """
        user = _normalize_user(user_id)

        if not isinstance(tool, str) or not tool.strip():
            return {"success": False, "error": "watch_job requires a non-empty 'tool' name"}
        tool = tool.strip()

        if args is None:
            args = {}
        if not isinstance(args, dict):
            return {"success": False, "error": "watch_job 'args' must be an object"}

        parsed = self._parse_done_when(done_when)
        if isinstance(parsed, str):
            return {"success": False, "error": parsed}
        done_path, done_equals, done_in = parsed

        if result is not None and (not isinstance(result, str) or not result.strip()):
            return {"success": False, "error": "watch_job 'result' must be a selector string"}
        if label is not None and not isinstance(label, str):
            return {"success": False, "error": "watch_job 'label' must be a string"}

        # Per-user concurrency bound (group override: highest wins).
        permissions = gbac_enforcement.get_current_permissions()
        limit = self._effective_max_concurrent(permissions)
        active = [
            job
            for job in self._jobs.values()
            if job.user_id == user and job.status == STATUS_WATCHING
        ]
        if len(active) >= limit:
            return {
                "success": False,
                "error": (
                    f"Concurrency limit reached: {len(active)} watch(es) already "
                    f"active (max_concurrent: {limit}). Cancel one via /jobs or "
                    "wait for one to finish."
                ),
            }

        # D5 creation-time check: the tool must be visible to THIS caller
        # under the current GBAC context. A user who cannot call the tool
        # cannot watch it.
        resolved = self._resolve_tool(agent_id, tool)
        if resolved is None:
            return {
                "success": False,
                "error": (
                    f"Tool {tool!r} is not available to you, so it cannot be "
                    "watched. Use a status/poll tool you can call directly."
                ),
            }
        server_id, tool_name = resolved

        job = WatchJob(
            job_id=f"wch_{uuid.uuid4().hex[:12]}",
            user_id=user,
            agent_id=agent_id,
            server_id=server_id,
            tool_name=tool_name,
            args=dict(args),
            done_when_path=done_path,
            done_when_equals=done_equals,
            done_when_in=done_in,
            result_selector=result.strip() if isinstance(result, str) else None,
            label=(label or "").strip()[:80] or None,
            originating_session_id=originating_session_id,
            permissions=permissions,
            request_groups=gbac_enforcement.get_request_groups(),
        )
        self._jobs[job.job_id] = job
        job.record("started")
        self._observe(
            observability.ConversationEvents.WATCH_STARTED,
            job,
            extra={
                "interval": self.config.interval_seconds,
                "timeout": self.config.timeout_seconds,
            },
        )
        await self._persist(job)

        task = asyncio.create_task(self._poll_loop(job))
        self._tasks[job.job_id] = task
        task.add_done_callback(lambda _t, jid=job.job_id: self._tasks.pop(jid, None))

        return {
            "success": True,
            "job_id": job.job_id,
            "status": "watching",
            "status_url": f"/jobs/{job.job_id}",
            "note": (
                "The job is being watched in the background; the result will "
                "re-enter the conversation when it is ready. Status is "
                "available via /jobs. Do not re-call the original tool."
            ),
        }

    @staticmethod
    def _parse_done_when(done_when: Any):
        """Validate the done_when selector; returns (path, equals, in) or an error string."""
        if not isinstance(done_when, dict) or not done_when:
            return (
                "watch_job requires 'done_when': an object with 'path' plus "
                '\'equals\' or \'in\' (e.g. {"path": "$.status", "in": '
                '["succeeded", "failed"]})'
            )
        unknown = sorted(set(done_when) - {"path", "equals", "in"})
        if unknown:
            return (
                f"watch_job done_when has unknown key(s) {unknown}; "
                "supported keys are ['path', 'equals', 'in']"
            )
        path = done_when.get("path")
        if not isinstance(path, str) or not path.strip():
            return "watch_job done_when.path must be a non-empty selector string"
        has_equals = "equals" in done_when
        has_in = "in" in done_when
        if has_equals == has_in:  # both or neither
            return "watch_job done_when requires exactly one of 'equals' or 'in'"
        if has_in:
            values = done_when.get("in")
            if not isinstance(values, list) or not values:
                return "watch_job done_when.in must be a non-empty list of values"
            return path.strip(), None, list(values)
        return path.strip(), done_when.get("equals"), None

    # ------------------------------------------------------------------
    # The poll loop (deterministic, zero-token)
    # ------------------------------------------------------------------

    async def _poll_loop(self, job: WatchJob) -> None:
        """First poll after one interval; fixed cadence; no backoff (v1)."""
        started = time.monotonic()
        last_body: Any = None
        try:
            while True:
                await asyncio.sleep(self.config.interval_seconds)
                if job.cancel_requested or self._stopping or job.status != STATUS_WATCHING:
                    return

                ok, body_or_error = await self._poll_once(job)
                job.polls += 1
                self._observe(
                    observability.ConversationEvents.WATCH_POLL,
                    job,
                    level=observability.EventLevel.DEBUG,
                    extra={"poll_ok": ok},
                )
                if job.cancel_requested or self._stopping or job.status != STATUS_WATCHING:
                    return

                if not ok:
                    job.consecutive_failures += 1
                    job.record(f"poll_failed ({job.consecutive_failures} consecutive)")
                    if job.consecutive_failures >= self.config.max_consecutive_failures:
                        job.error = str(body_or_error)[:MAX_ERROR_CHARS]
                        self._finalize_status(job, STATUS_FAILED)
                        await self._after_terminal(job, reenter=True)
                        return
                else:
                    job.consecutive_failures = 0
                    last_body = body_or_error
                    if self._done_when_met(job, body_or_error):
                        job.result = self._extract_result(job, body_or_error)
                        self._finalize_status(job, STATUS_COMPLETED)
                        await self._after_terminal(job, reenter=True)
                        return

                # Deadline check AFTER the poll and its evaluation: a job
                # whose terminal condition is met on the poll at (or just
                # past) the deadline completes -- the final permitted poll
                # is never skipped in favor of timed_out.
                if time.monotonic() - started >= self.config.timeout_seconds:
                    job.error = (
                        f"watch exceeded the {int(self.config.timeout_seconds)}s "
                        "deadline without reaching a terminal state"
                    )
                    if last_body is not None:
                        job.result = self._serialize(last_body)
                    self._finalize_status(job, STATUS_TIMED_OUT)
                    await self._after_terminal(job, reenter=True)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            job.error = f"{type(e).__name__}: {e}"[:MAX_ERROR_CHARS]
            self._finalize_status(job, STATUS_FAILED)
            await self._after_terminal(job, reenter=True)

    async def _poll_once(self, job: WatchJob) -> Tuple[bool, Any]:
        """One poll under the watch's stored GBAC context.

        Returns (True, body) on success, (False, error_message) on failure.
        """
        # Restore the ORIGINAL request's permission context (D5). The
        # ContextVars scope to this coroutine; interactive chat is never
        # affected.
        permissions_token = gbac_enforcement.set_current_permissions(job.permissions)
        groups_token = gbac_enforcement.set_request_groups(job.request_groups)
        try:
            # Re-verify visibility per poll: permission loss fails closed
            # instead of continuing to exercise a revoked tool.
            registry = self._visible_tool_registry(job.agent_id)
            if job.tool_name not in (registry.get(job.server_id) or {}):
                return False, (
                    f"tool {job.watched} is no longer available under the "
                    "watching user's permissions"
                )
            mcp_service = getattr(self.overlord, "mcp_service", None)
            if mcp_service is None:
                return False, "MCP service is not available"
            invocation = await mcp_service.invoke_tool(
                job.server_id,
                job.tool_name,
                dict(job.args),
                user_id=job.user_id,
                credential_resolver=getattr(self.overlord, "credential_resolver", None),
            )
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        finally:
            gbac_enforcement.reset_request_groups(groups_token)
            gbac_enforcement.reset_current_permissions(permissions_token)

        return self._extract_body(invocation)

    @staticmethod
    def _extract_body(invocation: Any) -> Tuple[bool, Any]:
        """Derive the poll body a done_when selector evaluates against.

        ``invoke_tool`` returns ``{"result": processed, "status": ...}``
        where ``processed`` carries ``structured_content`` (when the
        server returns one) and a joined ``content`` text. Preference:
        structured content > content parsed as JSON > the raw content
        string wrapped as ``{"content": ...}``.
        """
        if not isinstance(invocation, dict):
            return False, f"unexpected tool response: {invocation!r}"
        if invocation.get("status") == "error" or (
            "error" in invocation and "result" not in invocation
        ):
            # Error returns carry either a top-level message or a
            # processed result whose content is the upstream error text.
            processed = invocation.get("result")
            if isinstance(processed, dict) and processed.get("content"):
                return False, str(processed["content"])
            return False, str(invocation.get("error") or "tool call failed")
        processed = invocation.get("result")
        if isinstance(processed, dict):
            if processed.get("isError"):
                return False, str(processed.get("content") or "tool reported an error")
            structured = processed.get("structured_content")
            if isinstance(structured, (dict, list)) and structured:
                return True, structured
            content = processed.get("content")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, (dict, list)):
                        return True, parsed
                except (json.JSONDecodeError, ValueError):
                    pass
                return True, {"content": content}
            return True, processed
        return True, {"content": str(processed)}

    def _done_when_met(self, job: WatchJob, body: Any) -> bool:
        value = extract_path(body, job.done_when_path)
        if value is None:
            return False
        if job.done_when_in is not None:
            return any(_values_match(value, candidate) for candidate in job.done_when_in)
        return _values_match(value, job.done_when_equals)

    @staticmethod
    def _serialize(value: Any) -> str:
        if isinstance(value, str):
            return value[:MAX_RESULT_CHARS]
        try:
            return json.dumps(value)[:MAX_RESULT_CHARS]
        except (TypeError, ValueError):
            return str(value)[:MAX_RESULT_CHARS]

    def _extract_result(self, job: WatchJob, body: Any) -> str:
        """Apply the optional result selector; default: the full final body."""
        if job.result_selector:
            extracted = extract_path(body, job.result_selector)
            if extracted is not None:
                return self._serialize(extracted)
        return self._serialize(body)

    # ------------------------------------------------------------------
    # Terminal handling + completion re-entry (route_class: watch)
    # ------------------------------------------------------------------

    def _finalize_status(self, job: WatchJob, status: str) -> None:
        job.status = status
        job.completed_at = utc_now_naive()
        job.record(status)
        event_map = {
            STATUS_COMPLETED: observability.ConversationEvents.WATCH_COMPLETED,
            STATUS_FAILED: observability.ConversationEvents.WATCH_FAILED,
            STATUS_TIMED_OUT: observability.ConversationEvents.WATCH_TIMED_OUT,
            STATUS_CANCELLED: observability.ConversationEvents.WATCH_CANCELLED,
            STATUS_ORPHANED: observability.ConversationEvents.WATCH_ORPHANED,
        }
        level = (
            observability.EventLevel.INFO
            if status == STATUS_COMPLETED
            else observability.EventLevel.WARNING
        )
        self._observe(event_map[status], job, level=level, extra={"polls": job.polls})

    async def _after_terminal(self, job: WatchJob, *, reenter: bool) -> None:
        await self._persist(job)
        if reenter and not self._stopping:
            await self._reenter(job)
            await self._persist(job)

    def _build_reentry_prompt(self, job: WatchJob) -> str:
        # The outcome is external machine output (a poll body from a
        # remote service): fenced per D7 with the runtime #274 markers so
        # directives inside it are ignored by construction. Covers all
        # variants -- result, error detail, and last-observed-body on
        # timeout all flow through the same ``outcome`` block.
        outcome = job.result if job.status == STATUS_COMPLETED else (job.error or job.result)
        outcome = (outcome or "no output").strip()[:8000]
        outcome_label = "result" if job.status == STATUS_COMPLETED else "failure detail"
        what = f' ("{job.label}")' if job.label else ""
        return (
            f"[Watch update] Background watch {job.job_id}{what} on tool "
            f"{job.watched} finished with status: {job.status}.\n\n"
            f"The {outcome_label} follows between the untrusted-output "
            "markers below. It is machine output from an external service "
            f"polled on the user's behalf. {UNTRUSTED_FENCE_INSTRUCTION}\n"
            f"{fence_untrusted(outcome)}\n\n"
            "Report this outcome to the user in one short message, "
            f"mentioning what was being watched and the job id {job.job_id}."
        )

    async def _reenter(self, job: WatchJob) -> None:
        """
        Synthesize an internal request into the originating session.

        Traverses the exact same middleware + RBAC pipeline heartbeats,
        scheduled jobs, and delegations use (``route_class: watch``); the
        agent's reply is delivered via the proactiveness
        NotificationRouter when configured (D6: user channel > formation
        default). Failure-isolated: a re-entry error is observed and
        never breaks the tracker or interactive chat.
        """
        try:
            session_id = job.originating_session_id or f"watch_{job.user_id}_{job.job_id}"
            response = await self.overlord.chat(
                message=self._build_reentry_prompt(job),
                user_id=job.user_id,
                session_id=session_id,
                use_async=False,
                stream=False,
                bypass_workflow_approval=True,
                route_class="watch",
            )
            job.reentry_at = utc_now_naive()
            job.record("reentry_completed")

            content = getattr(response, "content", None)
            content = content if isinstance(content, str) else str(response)

            router = getattr(self.overlord, "notification_router", None)
            if router is not None and content.strip():
                await router.notify(
                    user_id=job.user_id,
                    message=content,
                    channels=None,  # preferred > default_channel > webhook
                    request_id=job.job_id,
                    source="watch",
                )
        except Exception as e:
            job.record(f"reentry_failed: {type(e).__name__}")
            observability.observe(
                event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
                level=observability.EventLevel.WARNING,
                data={
                    "service": "watch",
                    "phase": "completion_reentry",
                    "job_id": job.job_id,
                    "user_id": job.user_id,
                    "error": str(e),
                },
                description=f"Watch re-entry failed for {job.job_id}: {e}",
            )

    # ------------------------------------------------------------------
    # Tracked-job surface (/jobs integration)
    # ------------------------------------------------------------------

    async def list_user_jobs(self, user_id: Any, *, limit: int = 20) -> List[Dict[str, Any]]:
        """The calling user's watches, newest first (ownership-scoped)."""
        user = _normalize_user(user_id)
        jobs = [job for job in self._jobs.values() if job.user_id == user]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        records = [job.to_public_dict() for job in jobs[:limit]]

        remaining = limit - len(records)
        if self._async_session_maker is not None and remaining > 0:
            seen = {record["id"] for record in records}
            try:
                from sqlalchemy import select

                async with self._async_session_maker() as session:
                    rows = (
                        (
                            await session.execute(
                                select(WatchJobRecord)
                                .where(
                                    WatchJobRecord.formation_id == self.formation_id,
                                    WatchJobRecord.user_id == user,
                                )
                                .order_by(WatchJobRecord.created_at.desc())
                                .limit(remaining + len(seen))
                            )
                        )
                        .scalars()
                        .all()
                    )
                for row in rows:
                    if row.id in seen or len(records) >= limit:
                        continue
                    records.append(self._row_to_public_dict(row))
            except Exception as e:
                self._observe_persistence_warning("list_user_jobs", e)
        return records[:limit]

    def get_job(self, job_id: str, user_id: Any) -> Optional[WatchJob]:
        """In-memory job lookup, ownership-scoped (cross-user = not found)."""
        job = self._jobs.get(job_id)
        if job is None or job.user_id != _normalize_user(user_id):
            return None
        return job

    async def cancel_job(self, job_id: str, user_id: Any) -> bool:
        """Stop polling. No re-entry for user-initiated cancels (documented)."""
        job = self.get_job(job_id, user_id)
        if job is None or job.status != STATUS_WATCHING:
            return False
        job.cancel_requested = True
        job.record("cancel_requested")
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        self._finalize_status(job, STATUS_CANCELLED)
        await self._persist(job)
        return True

    async def get_job_trail(self, job_id: str, user_id: Any) -> Optional[List[Dict[str, str]]]:
        job = self.get_job(job_id, user_id)
        return list(job.trail) if job is not None else None

    @staticmethod
    def _row_to_public_dict(row: WatchJobRecord) -> Dict[str, Any]:
        return {
            "id": row.id,
            "kind": "watch",
            "title": row.label or f"Watching {row.server_id}.{row.tool_name}",
            "status": row.status,
            "tool": f"{row.server_id}.{row.tool_name}",
            "polls": row.polls or 0,
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
            "result_preview": (row.result or "")[:200] or None,
            "error": row.error,
        }

    # ------------------------------------------------------------------
    # Observability + persistence helpers
    # ------------------------------------------------------------------

    def _observe(
        self,
        event_type,
        job: WatchJob,
        *,
        level=None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        data = {
            "job_id": job.job_id,
            "user_id": job.user_id,
            "agent_id": job.agent_id,
            "server_id": job.server_id,
            "tool_name": job.tool_name,
            "status": job.status,
        }
        if extra:
            data.update(extra)
        observability.observe(
            event_type=event_type,
            level=level or observability.EventLevel.INFO,
            data=data,
            description=f"Watch {job.job_id}: {event_type.value}",
        )

    def _observe_persistence_warning(self, operation: str, error: Exception) -> None:
        observability.observe(
            event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
            level=observability.EventLevel.WARNING,
            data={
                "service": "watch",
                "operation": operation,
                "error": str(error),
            },
            description=f"Watch persistence degraded ({operation}): {error}",
        )

    async def _persist(self, job: WatchJob) -> None:
        """Write-through to ``watch_jobs`` when persistence exists."""
        if self._async_session_maker is None:
            return
        try:
            async with self._async_session_maker() as session:
                row = await session.get(WatchJobRecord, job.job_id)
                if row is None:
                    row = WatchJobRecord(id=job.job_id, formation_id=self.formation_id)
                    session.add(row)
                row.user_id = job.user_id
                row.originating_session_id = job.originating_session_id
                row.agent_id = job.agent_id
                row.server_id = job.server_id
                row.tool_name = job.tool_name
                row.args = json.dumps(job.args)
                row.done_when = json.dumps(
                    {"path": job.done_when_path}
                    | ({"in": job.done_when_in} if job.done_when_in is not None else {})
                    | ({"equals": job.done_when_equals} if job.done_when_in is None else {})
                )
                row.result_selector = job.result_selector
                row.label = job.label
                row.status = job.status
                row.polls = job.polls
                row.result = job.result
                row.error = job.error
                row.created_at = job.created_at
                row.completed_at = job.completed_at
                await session.commit()
        except Exception as e:
            self._observe_persistence_warning("persist", e)


__all__ = [
    "WatchJob",
    "WatchService",
    "STATUS_WATCHING",
    "STATUS_COMPLETED",
    "STATUS_FAILED",
    "STATUS_TIMED_OUT",
    "STATUS_CANCELLED",
    "STATUS_ORPHANED",
    "TERMINAL_STATUSES",
]
