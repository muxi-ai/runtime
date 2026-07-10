"""
Built-in slash commands (Proactiveness Phase 3).

Eight runtime commands that ship with every formation where the
``commands:`` block is enabled: /setup, /help, /jobs, /identity,
/channels, /preferences, /status, /reset. All of them are deterministic
-- they read and write existing services (scheduler jobs, user channel
state, user identifiers, buffer memory) and format plain-text replies
without an LLM round-trip, matching the unknown-command short-circuit
from Phase 1.

Mechanisms, not policies:

- Every command operates on the calling user's own state only (/jobs
  verifies job ownership by membership in the caller's job list before
  acting; /identity and /channels only touch the caller's rows).
- /setup walks the user through what THIS formation actually declares
  (its ``proactive.channels``) instead of hardcoding platforms. It is a
  deterministic multi-step flow: state is held in memory per user
  (``overlord._setup_flows``) and plain replies are intercepted by the
  chat path while a flow is active. No LLM is involved; the PRD's
  conversational profile questions (name/role/style) are deferred until
  the runtime has a mechanism that consumes them.
- Commands the formation cannot back (no scheduler, no ``proactive:``
  block, no database) reply with a friendly explanation instead of
  failing.

Failure isolation: ``execute_builtin`` wraps every handler; an exception
becomes a friendly error reply plus a COMMAND_FAILED event, never a
crashed turn. Text-only output (v1).
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytz

from ..datatypes.response import MuxiResponse
from ..services import observability
from .commands import (
    BUILTIN_COMMANDS,
    BuiltinCommand,
    CommandsConfig,
    ParsedCommand,
    available_commands,
    builtin_enabled,
    register_builtin,
)

# How long an unanswered /setup flow stays active before expiring.
SETUP_FLOW_TIMEOUT_SECONDS = 600

_CANCEL_WORDS = {"cancel", "stop", "quit", "exit"}
_SKIP_WORDS = {"skip", "none"}

_MAX_IDENTIFIER_LENGTH = 255
_MAX_IDENTIFIER_TYPE_LENGTH = 50


@dataclass
class BuiltinCommandContext:
    """Everything a built-in command handler may need for one invocation."""

    overlord: Any
    user_id: Any  # User id exactly as the chat path holds it ("0" single-user)
    session_id: Optional[str]
    args: str
    config: CommandsConfig
    sops: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class SetupFlowState:
    """In-memory progress of one user's /setup flow."""

    steps: List[str]
    index: int = 0
    updated_at: float = field(default_factory=time.time)


# ===================================================================
# Shared helpers
# ===================================================================


def _channel_user(ctx: BuiltinCommandContext) -> str:
    """The user id under which channel/preference state is tracked."""
    if not getattr(ctx.overlord, "is_multi_user", False) or ctx.user_id is None:
        return "0"
    return str(ctx.user_id).lower().strip()


def _channel_store(ctx: BuiltinCommandContext) -> Any:
    return getattr(ctx.overlord, "user_channel_store", None)


def _proactive_config(ctx: BuiltinCommandContext) -> Any:
    return getattr(ctx.overlord, "_proactive_config", None)


def _declared_channels(ctx: BuiltinCommandContext) -> List[str]:
    config = _proactive_config(ctx)
    if config is None:
        return []
    return sorted(config.channels)


def _scheduler(ctx: BuiltinCommandContext) -> Any:
    return getattr(ctx.overlord, "scheduler_service", None)


def _delegation(ctx: BuiltinCommandContext) -> Any:
    return getattr(ctx.overlord, "delegation_service", None)


def _db_manager(ctx: BuiltinCommandContext) -> Any:
    """The formation database manager (orchestrator's fallback chain)."""
    db = getattr(ctx.overlord, "db_manager", None)
    if db is not None:
        return db
    long_term = getattr(ctx.overlord, "long_term_memory", None)
    return getattr(long_term, "db_manager", None) if long_term is not None else None


_NO_CHANNELS_MESSAGE = (
    "This formation has no notification channels configured, " "so there is nothing to manage here."
)


def _job_schedule_line(job: Dict[str, Any]) -> str:
    """One-line schedule description for a job dict."""
    if job.get("is_recurring"):
        return f"Schedule: {job.get('cron_expression') or 'unknown'}"
    return f"Runs once at: {job.get('scheduled_for') or 'unknown'}"


def _format_job(index: int, job: Dict[str, Any]) -> str:
    lines = [f"{index}. {job.get('title') or 'Untitled task'} [{job.get('id')}]"]
    detail = f"   {_job_schedule_line(job)} | Status: {job.get('status')}"
    if job.get("last_run_at"):
        detail += f" | Last run: {job.get('last_run_at')} ({job.get('last_run_status')})"
    lines.append(detail)
    return "\n".join(lines)


def _format_coding_job(index: int, job: Dict[str, Any]) -> str:
    """One /jobs listing entry for a coding delegation."""
    lines = [f"{index}. {job.get('title') or 'Coding task'} [{job.get('id')}]"]
    detail = f"   Coding task ({job.get('adapter') or 'inline'}) | Status: {job.get('status')}"
    if job.get("completed_at"):
        detail += f" | Finished: {job.get('completed_at')}"
    lines.append(detail)
    return "\n".join(lines)


def _find_job(jobs: List[Dict[str, Any]], token: str) -> Optional[Dict[str, Any]]:
    """Resolve a job by exact id or 1-based position in the user's listing."""
    for job in jobs:
        if job.get("id") == token:
            return job
    if token.isdigit():
        position = int(token)
        if 1 <= position <= len(jobs):
            return jobs[position - 1]
    return None


# ===================================================================
# /help
# ===================================================================


async def _cmd_help(ctx: BuiltinCommandContext) -> str:
    lines = ["Available commands:", ""]
    for name in sorted(BUILTIN_COMMANDS):
        if not builtin_enabled(ctx.config, name):
            continue
        if name in (ctx.sops or {}):
            continue  # Shadowed by a formation SOP; listed below instead
        builtin = BUILTIN_COMMANDS[name]
        lines.append(f"{builtin.usage} - {builtin.description}")

    if ctx.sops:
        lines.extend(["", "Formation commands:"])
        for sop_id in sorted(ctx.sops):
            description = ctx.sops[sop_id].get("description") or ""
            lines.append(f"/{sop_id}" + (f" - {description}" if description else ""))

    known = available_commands(ctx.config, ctx.sops)
    alias_lines = [
        f"/{alias} -> /{target}"
        for alias, target in sorted(ctx.config.aliases.items())
        if target in known
    ]
    if alias_lines:
        lines.extend(["", "Aliases:"])
        lines.extend(alias_lines)

    return "\n".join(lines)


# ===================================================================
# /status
# ===================================================================


async def _cmd_status(ctx: BuiltinCommandContext) -> str:
    lines = [
        f"Formation: {getattr(ctx.overlord, 'formation_id', 'unknown')}",
        f"User: {_channel_user(ctx)}",
    ]

    store = _channel_store(ctx)
    if store is not None:
        state = await store.get_state(_channel_user(ctx))
        lines.append("Notifications:")
        lines.append(f"  Preferred channel: {state.get('preferred_channel') or 'not set'}")
        lines.append(f"  Last channel: {state.get('last_channel') or 'none recorded'}")
        lines.append(f"  Timezone: {state.get('timezone') or 'not set'}")
        declared = _declared_channels(ctx)
        lines.append(f"  Declared channels: {', '.join(declared) if declared else 'none'}")
        heartbeat = getattr(ctx.overlord, "heartbeat_service", None)
        lines.append(f"  Heartbeat: {'on' if heartbeat else 'off'}")
    else:
        lines.append("Notifications: not configured (no 'proactive' block)")

    scheduler = _scheduler(ctx)
    if scheduler is not None:
        jobs = await scheduler.list_user_jobs(_channel_user(ctx))
        active = sum(1 for job in jobs if job.get("status") == "ACTIVE")
        paused = sum(1 for job in jobs if job.get("status") == "PAUSED")
        lines.append(f"Scheduled tasks: {active} active, {paused} paused (see /jobs)")
    else:
        lines.append("Scheduled tasks: scheduler not enabled")

    return "\n".join(lines)


# ===================================================================
# /jobs
# ===================================================================

_JOBS_USAGE = (
    "Usage: /jobs [list | pause <id> | resume <id> | cancel <id> | logs <id>]\n"
    "<id> is a task id or its number from the /jobs listing."
)


async def _cmd_jobs(ctx: BuiltinCommandContext) -> str:
    scheduler = _scheduler(ctx)
    delegation = _delegation(ctx)
    if scheduler is None and delegation is None:
        return (
            "Scheduled tasks are not available: the scheduler is not enabled "
            "in this formation ('scheduler.enabled: true' requires persistent memory)."
        )

    user = _channel_user(ctx)
    tokens = ctx.args.split()
    action = tokens[0].lower() if tokens else "list"

    scheduled_jobs = await scheduler.list_user_jobs(user) if scheduler is not None else []
    coding_jobs = await delegation.list_user_jobs(user) if delegation is not None else []
    # One continuous 1-based index across both listings so <id> resolution
    # stays unambiguous.
    jobs = list(scheduled_jobs) + list(coding_jobs)

    if action == "list" and len(tokens) <= 1:
        if not jobs:
            if scheduler is None:
                return "You have no coding tasks running."
            return (
                "You have no scheduled tasks. Ask me to schedule something "
                "(e.g. 'remind me every Friday at 4pm') to create one."
            )
        lines: List[str] = []
        if scheduled_jobs:
            lines.extend([f"You have {len(scheduled_jobs)} scheduled task(s):", ""])
            lines.extend(_format_job(i, job) for i, job in enumerate(scheduled_jobs, start=1))
        if coding_jobs:
            if lines:
                lines.append("")
            lines.extend([f"You have {len(coding_jobs)} coding task(s):", ""])
            lines.extend(
                _format_coding_job(i, job)
                for i, job in enumerate(coding_jobs, start=len(scheduled_jobs) + 1)
            )
        lines.extend(["", "Commands: /jobs pause <id>, resume <id>, cancel <id>, logs <id>"])
        return "\n".join(lines)

    if action not in {"pause", "resume", "cancel", "logs"} or len(tokens) != 2:
        return _JOBS_USAGE

    # Ownership check: only jobs in the calling user's own listing are
    # addressable (ids belonging to other users read as "not found").
    job = _find_job(jobs, tokens[1])
    if job is None:
        return f"No scheduled task {tokens[1]!r} found among your tasks. Use /jobs to list them."

    job_id = job["id"]
    title = job.get("title") or job_id

    if job.get("kind") == "coding":
        # Coding delegations: pause has no meaning for a one-shot headless
        # run (documented, not faked); cancel kills the process group but
        # keeps the vendor session id, so the task stays resumable.
        if action in {"pause", "resume"}:
            return (
                f"'{action}' is not supported for coding tasks: a one-shot "
                "headless run has no meaningful pause. Use /jobs cancel "
                f"{tokens[1]} to stop it (it stays resumable via a new "
                "delegation)."
            )
        if action == "cancel":
            if await delegation.cancel_job(job_id, user_id=user):
                return (
                    f'Cancelled coding task "{title}" (its process group was '
                    "killed; the session is retained, so the task can be "
                    "resumed with a new delegation)."
                )
            return f'Could not cancel "{title}" (only running coding tasks can be cancelled).'
        # logs
        trail = await delegation.get_job_trail(job_id, user_id=user)
        lines = [f'History for coding task "{title}":', ""]
        lines.append(f"Status: {job.get('status')}")
        if job.get("error"):
            lines.append(f"Error: {job.get('error')}")
        if trail:
            lines.append("Recent activity:")
            for entry in trail[-5:]:
                lines.append(f"- {entry.get('timestamp')}: {entry.get('action')}")
        return "\n".join(lines)

    if action == "pause":
        if await scheduler.pause_job(job_id, user_id=user):
            return f'Paused "{title}". Use /jobs resume {tokens[1]} when ready.'
        return f'Could not pause "{title}" (only active tasks can be paused).'

    if action == "resume":
        if await scheduler.resume_job(job_id, user_id=user):
            return f'Resumed "{title}".'
        return f'Could not resume "{title}" (only paused tasks can be resumed).'

    if action == "cancel":
        if await scheduler.delete_job(job_id, user_id=user):
            return f'Cancelled "{title}". This cannot be undone.'
        return f'Could not cancel "{title}".'

    # logs
    entries = await scheduler.job_manager.get_job_audit_trail(job_id)
    lines = [f'History for "{title}":', ""]
    lines.append(f"Runs: {job.get('total_runs', 0)} total, {job.get('total_failures', 0)} failed")
    if job.get("last_run_at"):
        lines.append(f"Last run: {job.get('last_run_at')} ({job.get('last_run_status')})")
        if job.get("last_run_failure_message"):
            lines.append(f"Last failure: {job.get('last_run_failure_message')}")
    if entries:
        lines.append("Recent activity:")
        for entry in entries[:5]:
            lines.append(f"- {entry.get('timestamp')}: {entry.get('action')}")
    return "\n".join(lines)


# ===================================================================
# /identity
# ===================================================================

_IDENTITY_USAGE = "Usage: /identity [list | link <identifier> [type] | unlink <identifier>]"


async def _cmd_identity(ctx: BuiltinCommandContext) -> str:
    if not getattr(ctx.overlord, "is_multi_user", False):
        return (
            "This formation runs in single-user mode; there are no linked " "identities to manage."
        )
    db_manager = _db_manager(ctx)
    if db_manager is None or ctx.user_id is None:
        return (
            "Identity management requires persistent memory (a database), "
            "which is not configured in this formation."
        )

    user = str(ctx.user_id).lower().strip()
    tokens = ctx.args.split()
    action = tokens[0].lower() if tokens else "list"

    if action == "list" and len(tokens) <= 1:
        return await _identity_list(ctx, db_manager, user)
    if action == "link" and len(tokens) in (2, 3):
        return await _identity_link(
            ctx, db_manager, user, tokens[1], tokens[2] if len(tokens) == 3 else None
        )
    if action == "unlink" and len(tokens) == 2:
        return await _identity_unlink(ctx, db_manager, user, tokens[1])
    return _IDENTITY_USAGE


async def _identity_rows(session, formation_id: str, internal_user_id: int):
    from sqlalchemy import select

    from ..services.memory.long_term import UserIdentifier

    result = await session.execute(
        select(UserIdentifier).where(
            UserIdentifier.user_id == internal_user_id,
            UserIdentifier.formation_id == formation_id,
        )
    )
    return result.scalars().all()


async def _identity_list(ctx: BuiltinCommandContext, db_manager, user: str) -> str:
    from sqlalchemy import select

    from ..services.memory.long_term import UserIdentifier

    formation_id = ctx.overlord.formation_id
    async with db_manager.get_async_session() as session:
        result = await session.execute(
            select(UserIdentifier).where(
                UserIdentifier.identifier == user,
                UserIdentifier.formation_id == formation_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return (
                f"Your identity: {user}\n"
                "No other identifiers are linked yet. "
                "Use /identity link <identifier> [type] to link one."
            )
        rows = await _identity_rows(session, formation_id, row.user_id)

    lines = ["Your linked identities:", ""]
    for identifier_row in rows:
        line = f"- {identifier_row.identifier}"
        if identifier_row.identifier_type:
            line += f" ({identifier_row.identifier_type})"
        if identifier_row.identifier == user:
            line += " (current)"
        lines.append(line)
    lines.extend(["", "Commands: /identity link <identifier> [type], unlink <identifier>"])
    return "\n".join(lines)


async def _identity_link(
    ctx: BuiltinCommandContext,
    db_manager,
    user: str,
    identifier: str,
    identifier_type: Optional[str],
) -> str:
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from ..services.memory.long_term import UserIdentifier
    from ..utils.user_resolution import resolve_user_identifier

    identifier = identifier.strip().lower()
    if not identifier or len(identifier) > _MAX_IDENTIFIER_LENGTH:
        return f"Invalid identifier: must be 1-{_MAX_IDENTIFIER_LENGTH} characters with no spaces."
    if identifier_type is not None:
        # Normalize like the identifier itself so "Telegram" and "telegram"
        # render as one label in /identity listings.
        identifier_type = identifier_type.strip().lower()
        if not identifier_type or len(identifier_type) > _MAX_IDENTIFIER_TYPE_LENGTH:
            return f"Invalid identifier type: must be 1-{_MAX_IDENTIFIER_TYPE_LENGTH} characters."
    if identifier == user:
        return f"{identifier} is the identity you are already using."

    formation_id = ctx.overlord.formation_id
    # Resolve (or create) the calling user's account, same as the chat path.
    resolved = await resolve_user_identifier(
        identifier=user,
        formation_id=formation_id,
        db_manager=db_manager,
        kv_cache=None,
    )
    if resolved is None:
        return "Could not resolve your user account."
    internal_user_id, _ = resolved

    async with db_manager.get_async_session() as session:
        result = await session.execute(
            select(UserIdentifier).where(
                UserIdentifier.identifier == identifier,
                UserIdentifier.formation_id == formation_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            if existing.user_id == internal_user_id:
                return f"{identifier} is already linked to your account."
            return f"{identifier} is already linked to a different user."

        session.add(
            UserIdentifier(
                user_id=internal_user_id,
                identifier=identifier,
                identifier_type=identifier_type,
                formation_id=formation_id,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            return f"{identifier} is already linked to a different user."

    suffix = f" ({identifier_type})" if identifier_type else ""
    return f"Linked {identifier}{suffix} to your account. Messages from it now share your context."


async def _identity_unlink(
    ctx: BuiltinCommandContext, db_manager, user: str, identifier: str
) -> str:
    from sqlalchemy import select

    from ..services.memory.long_term import UserIdentifier

    identifier = identifier.strip().lower()
    if identifier == user:
        return "You cannot unlink the identity you are currently using."

    formation_id = ctx.overlord.formation_id
    async with db_manager.get_async_session() as session:
        result = await session.execute(
            select(UserIdentifier).where(
                UserIdentifier.identifier == user,
                UserIdentifier.formation_id == formation_id,
            )
        )
        me = result.scalar_one_or_none()
        if me is None:
            return f"{identifier} is not linked to your account."

        result = await session.execute(
            select(UserIdentifier).where(
                UserIdentifier.identifier == identifier,
                UserIdentifier.formation_id == formation_id,
                UserIdentifier.user_id == me.user_id,
            )
        )
        target = result.scalar_one_or_none()
        if target is None:
            return f"{identifier} is not linked to your account."

        await session.delete(target)
        await session.commit()

    return f"Unlinked {identifier} from your account."


# ===================================================================
# /channels
# ===================================================================

_CHANNELS_USAGE = "Usage: /channels [list | default <channel> | test <channel>]"


async def _cmd_channels(ctx: BuiltinCommandContext) -> str:
    store = _channel_store(ctx)
    if store is None:
        return _NO_CHANNELS_MESSAGE

    user = _channel_user(ctx)
    declared = _declared_channels(ctx)
    if not declared:
        # A 'proactive' block with zero declared channels: nothing here can
        # be listed, defaulted, or tested.
        return _NO_CHANNELS_MESSAGE
    tokens = ctx.args.split()
    action = tokens[0].lower() if tokens else "list"

    if action == "list" and len(tokens) <= 1:
        state = await store.get_state(user)
        lines = ["Your notification channels:", ""]
        for name in declared:
            markers = []
            if name == state.get("preferred_channel"):
                markers.append("default")
            if name == state.get("last_channel"):
                markers.append("last used")
            suffix = f" ({', '.join(markers)})" if markers else ""
            lines.append(f"- {name}{suffix}")
        if not state.get("preferred_channel"):
            proactive = _proactive_config(ctx)
            fallback = getattr(proactive, "default_channel", None) or "webhook"
            lines.append(f"\nNo default set; notifications fall back to: {fallback}")
        lines.extend(["", "Commands: /channels default <channel>, test <channel>"])
        return "\n".join(lines)

    if action not in {"default", "test"} or len(tokens) != 2:
        return _CHANNELS_USAGE

    channel = tokens[1]
    if channel not in declared:
        return (
            f"Unknown channel {channel!r}. Declared channels: "
            f"{', '.join(declared) if declared else 'none'}."
        )

    if action == "default":
        await store.set_preferences(user, preferred_channel=channel)
        return f"Default notification channel set to {channel}."

    router = getattr(ctx.overlord, "notification_router", None)
    if router is None:
        return "Notification routing is not available."
    result = await router.notify(
        user_id=user,
        message="Test notification requested via /channels test.",
        channels=[channel],
        source="command",
    )
    if channel in (result.get("delivered") or []):
        return f"Sent a test notification to {channel}. Did you get it?"
    return (
        f"Test notification to {channel} could not be delivered "
        f"(delivered: {result.get('delivered') or 'none'})."
    )


# ===================================================================
# /preferences
# ===================================================================

_PREFERENCES_USAGE = "Usage: /preferences [timezone <IANA name>|timezone clear | channel <name>]"


async def _cmd_preferences(ctx: BuiltinCommandContext) -> str:
    store = _channel_store(ctx)
    if store is None:
        return _NO_CHANNELS_MESSAGE

    user = _channel_user(ctx)
    tokens = ctx.args.split()

    if not tokens:
        state = await store.get_state(user)
        return (
            "Your preferences:\n\n"
            f"Notification channel: {state.get('preferred_channel') or 'not set'}\n"
            f"Timezone: {state.get('timezone') or 'not set'}\n\n"
            "Update: /preferences timezone <IANA name> (or 'clear'),\n"
            "        /preferences channel <name>"
        )

    setting = tokens[0].lower()
    if setting == "timezone" and len(tokens) == 2:
        value = tokens[1]
        if value.lower() == "clear":
            await store.set_preferences(user, timezone="")
            return "Timezone cleared."
        try:
            pytz.timezone(value)
        except pytz.exceptions.UnknownTimeZoneError:
            return f"Unknown timezone {value!r}. Use an IANA name like Europe/London."
        await store.set_preferences(user, timezone=value)
        return f"Timezone set to {value}."

    if setting == "channel" and len(tokens) == 2:
        declared = _declared_channels(ctx)
        if tokens[1] not in declared:
            return (
                f"Unknown channel {tokens[1]!r}. Declared channels: "
                f"{', '.join(declared) if declared else 'none'}."
            )
        await store.set_preferences(user, preferred_channel=tokens[1])
        return f"Default notification channel set to {tokens[1]}."

    return _PREFERENCES_USAGE


# ===================================================================
# /reset
# ===================================================================


async def _cmd_reset(ctx: BuiltinCommandContext) -> str:
    buffer = getattr(ctx.overlord, "buffer_memory", None)
    if buffer is None or not hasattr(buffer, "remove_by_metadata"):
        return "Conversation history clearing is not available in this formation."
    if not ctx.session_id:
        return "There is no active session, so there is no conversation history to clear."

    user = "0" if ctx.user_id is None else str(ctx.user_id)
    removed = buffer.remove_by_metadata(
        {"user_id": user, "session_id": ctx.session_id}, namespace="buffer"
    )
    if removed:
        return f"Conversation history cleared ({removed} message(s) removed from this session)."
    return "This session has no conversation history to clear."


# ===================================================================
# /setup (deterministic multi-step flow)
# ===================================================================


def _flows(overlord: Any) -> Dict[str, SetupFlowState]:
    """The per-overlord in-memory flow map (created lazily)."""
    flows = getattr(overlord, "_setup_flows", None)
    if flows is None:
        flows = {}
        overlord._setup_flows = flows
    return flows


def cancel_setup_flow(overlord: Any, user_id: Any) -> None:
    """Drop any active /setup flow for a user (any resolved command cancels)."""
    user = "0" if user_id is None else str(user_id).lower().strip()
    _flows(overlord).pop(user, None)


def _setup_question(ctx: BuiltinCommandContext, step: str) -> str:
    if step == "channel":
        declared = ", ".join(_declared_channels(ctx))
        return (
            "Where should I send proactive notifications?\n"
            f"Available channels: {declared}\n"
            "Reply with a channel name, or 'skip'."
        )
    # timezone
    return (
        "What timezone are you in?\n"
        "Reply with an IANA name like Europe/London or America/New_York, or 'skip'."
    )


async def _setup_summary(ctx: BuiltinCommandContext) -> str:
    store = _channel_store(ctx)
    state = await store.get_state(_channel_user(ctx))
    return (
        "You're all set:\n"
        f"- Notification channel: {state.get('preferred_channel') or 'not set'}\n"
        f"- Timezone: {state.get('timezone') or 'not set'}\n\n"
        "Type /help to see what I can do."
    )


async def _cmd_setup(ctx: BuiltinCommandContext) -> str:
    store = _channel_store(ctx)
    if store is None:
        return (
            "Nothing to set up: this formation has no notification channels "
            "or per-user preferences configured."
        )

    steps: List[str] = []
    if _declared_channels(ctx):
        steps.append("channel")
    steps.append("timezone")

    user = _channel_user(ctx)
    _flows(ctx.overlord)[user] = SetupFlowState(steps=steps)

    intro = "Let's get you set up. Reply 'skip' to skip a question or 'cancel' to stop.\n\n"
    return intro + _setup_question(ctx, steps[0])


async def handle_setup_answer(
    overlord: Any,
    user_id: Any,
    session_id: Optional[str],
    message: str,
    config: CommandsConfig,
) -> Optional[str]:
    """
    Feed a plain (non-command) message into the user's active /setup flow.

    Returns the deterministic reply when a flow is active, or None when the
    message should continue through the normal chat pipeline. Never raises:
    a broken flow cancels itself with a friendly message.
    """
    ctx = BuiltinCommandContext(
        overlord=overlord, user_id=user_id, session_id=session_id, args="", config=config
    )
    user = _channel_user(ctx)
    flows = _flows(overlord)
    flow = flows.get(user)
    if flow is None:
        return None
    if time.time() - flow.updated_at > SETUP_FLOW_TIMEOUT_SECONDS:
        # Tell the user instead of silently dropping the flow: without this
        # the pending answer would fall through to the LLM unexplained.
        flows.pop(user, None)
        return "Setup session expired after 10 minutes of inactivity. " "Run /setup to start again."

    try:
        return await _advance_setup_flow(ctx, flows, flow, message)
    except Exception as e:
        flows.pop(user, None)
        observability.observe(
            event_type=observability.ConversationEvents.COMMAND_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "command": "setup",
                "user_id": user,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            description=f"/setup flow failed (isolated): {e}",
        )
        return "Sorry, setup hit an unexpected error and was cancelled. Type /setup to try again."


async def _advance_setup_flow(
    ctx: BuiltinCommandContext,
    flows: Dict[str, SetupFlowState],
    flow: SetupFlowState,
    message: str,
) -> str:
    user = _channel_user(ctx)
    store = _channel_store(ctx)
    answer = (message or "").strip()
    lowered = answer.lower()
    flow.updated_at = time.time()

    if lowered in _CANCEL_WORDS:
        flows.pop(user, None)
        return "Setup cancelled. Type /setup to start again."

    step = flow.steps[flow.index]
    ack = ""

    if lowered in _SKIP_WORDS:
        ack = "Skipped."
    elif step == "channel":
        declared = _declared_channels(ctx)
        match = next((name for name in declared if name.lower() == lowered), None)
        if match is None:
            return (
                f"I don't recognize that channel. Available: {', '.join(declared)}. "
                "Reply with a channel name, or 'skip'."
            )
        await store.set_preferences(user, preferred_channel=match)
        ack = f"Notifications will go to {match}."
    elif step == "timezone":
        try:
            pytz.timezone(answer)
        except pytz.exceptions.UnknownTimeZoneError:
            return (
                f"I don't recognize {answer!r} as a timezone. "
                "Use an IANA name like Europe/London, or 'skip'."
            )
        await store.set_preferences(user, timezone=answer)
        ack = f"Timezone set to {answer}."

    flow.index += 1
    if flow.index >= len(flow.steps):
        flows.pop(user, None)
        summary = await _setup_summary(ctx)
        return f"{ack}\n\n{summary}"

    return f"{ack}\n\n{_setup_question(ctx, flow.steps[flow.index])}"


# ===================================================================
# Executor (failure isolation + observability)
# ===================================================================


async def execute_builtin(
    overlord: Any,
    builtin: BuiltinCommand,
    parsed: ParsedCommand,
    config: CommandsConfig,
    sops: Optional[Dict[str, Dict[str, Any]]],
    user_id: Any,
    session_id: Optional[str],
) -> MuxiResponse:
    """
    Execute a built-in command handler with full failure isolation.

    A handler exception becomes a friendly error reply plus a
    COMMAND_FAILED event; it can never crash the chat turn.
    """
    ctx = BuiltinCommandContext(
        overlord=overlord,
        user_id=user_id,
        session_id=session_id,
        args=parsed.args,
        config=config,
        sops=sops or {},
    )
    try:
        reply = await builtin.handler(ctx)
        observability.observe(
            event_type=observability.ConversationEvents.COMMAND_EXECUTED,
            level=observability.EventLevel.INFO,
            data={
                "command": builtin.name,
                "invoked_as": parsed.name,
                "user_id": str(user_id),
                "has_args": bool(parsed.args),
            },
            description=f"Built-in command /{builtin.name} executed",
        )
        return MuxiResponse(
            role="assistant",
            content=reply,
            metadata={
                "command": builtin.name,
                "command_type": "builtin",
                "command_status": "ok",
            },
        )
    except Exception as e:
        observability.observe(
            event_type=observability.ConversationEvents.COMMAND_FAILED,
            level=observability.EventLevel.ERROR,
            data={
                "command": builtin.name,
                "user_id": str(user_id),
                "error": str(e),
                "error_type": type(e).__name__,
            },
            description=f"Built-in command /{builtin.name} failed (isolated): {e}",
        )
        return MuxiResponse(
            role="assistant",
            content=(
                f"Sorry, /{builtin.name} hit an unexpected error and could not complete. "
                "Please try again."
            ),
            metadata={
                "command": builtin.name,
                "command_type": "builtin",
                "command_status": "error",
            },
        )


# ===================================================================
# Registration
# ===================================================================

register_builtin(
    BuiltinCommand(
        name="setup",
        description="Set up your notification channel and preferences",
        usage="/setup",
        handler=_cmd_setup,
    )
)
register_builtin(
    BuiltinCommand(
        name="help",
        description="List available commands",
        usage="/help",
        handler=_cmd_help,
    )
)
register_builtin(
    BuiltinCommand(
        name="status",
        description="Show your current context overview",
        usage="/status",
        handler=_cmd_status,
    )
)
register_builtin(
    BuiltinCommand(
        name="jobs",
        description="Manage your scheduled tasks",
        usage="/jobs [pause|resume|cancel|logs <id>]",
        handler=_cmd_jobs,
    )
)
register_builtin(
    BuiltinCommand(
        name="identity",
        description="Manage your linked identities",
        usage="/identity [link|unlink <identifier>]",
        handler=_cmd_identity,
    )
)
register_builtin(
    BuiltinCommand(
        name="channels",
        description="Manage your notification channels",
        usage="/channels [default|test <channel>]",
        handler=_cmd_channels,
    )
)
register_builtin(
    BuiltinCommand(
        name="preferences",
        description="View and update your preferences",
        usage="/preferences [timezone <tz>|channel <name>]",
        handler=_cmd_preferences,
    )
)
register_builtin(
    BuiltinCommand(
        name="reset",
        description="Clear this session's conversation history",
        usage="/reset",
        handler=_cmd_reset,
    )
)
