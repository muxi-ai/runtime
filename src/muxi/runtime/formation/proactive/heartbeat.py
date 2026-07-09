"""
Heartbeat: periodic proactive check-ins driven by the scheduler service.

The heartbeat is NOT a second scheduler loop. It registers with the
existing SchedulerService as a periodic task; the scheduler's worker cycle
dispatches ``tick()`` onto the main event loop alongside due-job execution.
The heartbeat then applies its own interval gating and, when due, runs one
check per known user:

    tick (scheduler cadence)
      -> interval due?           no -> return
      -> for each known user:
           -> within active hours?   no -> HEARTBEAT_SKIPPED (silent)
           -> overlord.chat(heartbeat prompt)
           -> response mentions HEARTBEAT_OK? yes -> silent
           -> otherwise route to the configured target channel
              (default: the user's last-used channel)

Failure isolation: every layer catches and observes; a heartbeat failure
can never break interactive chat.

Prompt resolution: a formation-configured ``sop:`` wins; otherwise the
bundled default heartbeat SOP (``builtin/heartbeat.md``, shipped as
content next to this module, same convention as the bundled channel
templates) drives the check. ``instruction:`` is appended either way.
The formation-author fields stay policy; the bundled SOP is just a
sensible default policy that ships with the mechanism.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import pytz

from ...services import observability
from ...utils.id_generator import generate_request_id
from .config import HeartbeatConfig
from .router import NotificationRouter
from .user_channels import UserChannelStore

HEARTBEAT_OK_SENTINEL = "HEARTBEAT_OK"

# Prefix of the runtime-generated heartbeat session ids
# (``heartbeat_<user>_<request>``). The overlord's persona formatter uses
# it to recognize heartbeat-originated requests and keep the suppression
# sentinel intact (see ``Overlord._apply_persona``).
HEARTBEAT_SESSION_PREFIX = "heartbeat_"

# Bundled default heartbeat SOP (Proactiveness Phase 4): the base prompt
# when the heartbeat is enabled without a formation-configured `sop:`.
BUILTIN_HEARTBEAT_SOP_PATH = Path(__file__).parent / "builtin" / "heartbeat.md"

# Last-resort minimal prompt, used only if the bundled SOP file cannot be
# read (broken install). The heartbeat must never fire with an empty prompt.
DEFAULT_HEARTBEAT_PROMPT = (
    "You have been woken by a periodic heartbeat check. Review the user's "
    "context and determine whether anything genuinely needs their attention "
    "right now.\n\n"
    "Guidelines:\n"
    "- Only produce a message if something genuinely needs attention\n"
    "- Be concise: this is a quick check-in, not a report\n"
    f"- If nothing needs attention, respond with exactly: {HEARTBEAT_OK_SENTINEL}"
)

_default_heartbeat_sop: Optional[str] = None


def load_default_heartbeat_sop() -> str:
    """
    Load the bundled default heartbeat SOP (cached after the first read).

    Falls back to the minimal built-in prompt if the packaged file is
    missing or unreadable, so a broken install degrades to Phase 1
    behavior instead of an empty heartbeat prompt.
    """
    global _default_heartbeat_sop
    if _default_heartbeat_sop is None:
        try:
            content = BUILTIN_HEARTBEAT_SOP_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        _default_heartbeat_sop = content or DEFAULT_HEARTBEAT_PROMPT
    return _default_heartbeat_sop


def _reset_default_sop_cache() -> None:
    """
    Clear the cached bundled SOP so the next load re-reads the file.

    Test isolation only: production never needs invalidation (the bundled
    file is immutable for the life of the process).
    """
    global _default_heartbeat_sop
    _default_heartbeat_sop = None


class HeartbeatService:
    """
    Periodic proactive check-ins for users with known channel state.

    Registered with the SchedulerService via ``register_periodic_task``;
    the scheduler invokes ``tick()`` once per worker cycle on the main
    event loop.
    """

    def __init__(
        self,
        *,
        config: HeartbeatConfig,
        overlord: Any,
        router: NotificationRouter,
        channel_store: UserChannelStore,
    ):
        self.config = config
        self.overlord = overlord
        self.router = router
        self.channel_store = channel_store
        # First heartbeat fires one full interval after startup, not
        # immediately: formations restarting frequently must not turn the
        # heartbeat into a startup notification.
        self._last_run: Optional[datetime] = datetime.now(timezone.utc)
        self._running = False

    async def tick(self, now: Optional[datetime] = None) -> None:
        """
        Scheduler-cycle hook: run the heartbeat when the interval elapsed.

        Never raises.
        """
        try:
            now = now or datetime.now(timezone.utc)
            if self._running:
                return
            if self._last_run is not None:
                elapsed = (now - self._last_run).total_seconds()
                if elapsed < self.config.interval_seconds:
                    return
            self._last_run = now
            await self.run_once(now)
        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.HEARTBEAT_FAILED,
                level=observability.EventLevel.ERROR,
                data={"error": str(e), "error_type": type(e).__name__, "phase": "tick"},
                description=f"Heartbeat tick failed (isolated): {e}",
            )

    async def run_once(self, now: Optional[datetime] = None) -> List[str]:
        """
        Run one heartbeat pass over all known users, bypassing interval
        gating (active hours still apply). Used by tick() and tests.

        Returns:
            List of user ids for which a notification was sent
        """
        now = now or datetime.now(timezone.utc)
        self._running = True
        notified: List[str] = []
        try:
            users = await self.channel_store.known_users()
            for user_id in users:
                try:
                    if await self._run_user_heartbeat(user_id, now):
                        notified.append(user_id)
                except Exception as e:
                    observability.observe(
                        event_type=observability.ConversationEvents.HEARTBEAT_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "user_id": user_id,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                        description=f"Heartbeat for user {user_id} failed (isolated): {e}",
                    )
        finally:
            self._running = False
        return notified

    async def _run_user_heartbeat(self, user_id: str, now: datetime) -> bool:
        """Run the heartbeat for one user. Returns True when a message was sent."""
        state = await self.channel_store.get_state(user_id)

        if not self.is_within_active_hours(now, user_timezone=state.get("timezone")):
            observability.observe(
                event_type=observability.ConversationEvents.HEARTBEAT_SKIPPED,
                level=observability.EventLevel.DEBUG,
                data={"user_id": user_id, "reason": "outside_active_hours"},
                description=f"Heartbeat for user {user_id} suppressed (outside active hours)",
            )
            return False

        request_id = generate_request_id()
        observability.observe(
            event_type=observability.ConversationEvents.HEARTBEAT_STARTED,
            level=observability.EventLevel.INFO,
            data={"user_id": user_id, "request_id": request_id, "target": self.config.target},
            description=f"Heartbeat started for user {user_id}",
        )

        prompt = self._build_prompt()
        # Fresh session per heartbeat run: a fixed session id would
        # accumulate conversation history (and session-scoped buffer
        # memory) without bound across ticks. Heartbeat context comes
        # from the SOP/instruction plus the user's memory, not from
        # prior tick chatter; the request id keeps the session
        # correlated with this run's observability events.
        # Internally-originated request: traverses the formation
        # middleware + RBAC pipeline exactly like external traffic,
        # identified by route_class "heartbeat". A middleware failure or
        # RBAC rejection raises and is isolated per user by run_once().
        response = await self.overlord.chat(
            message=prompt,
            user_id=user_id,
            session_id=f"{HEARTBEAT_SESSION_PREFIX}{user_id}_{request_id}",
            request_id=request_id,
            use_async=False,
            stream=False,
            bypass_workflow_approval=True,
            is_scheduled_execution=True,
            route_class="heartbeat",
        )
        content = self._extract_content(response)

        if self._is_heartbeat_ok(content):
            observability.observe(
                event_type=observability.ConversationEvents.HEARTBEAT_COMPLETED,
                level=observability.EventLevel.INFO,
                data={"user_id": user_id, "request_id": request_id, "delivered": False},
                description=f"Heartbeat OK for user {user_id}, nothing to report",
            )
            return False

        result = await self.router.notify(
            user_id=user_id,
            message=content,
            channels=[self.config.target],
            request_id=request_id,
            source="heartbeat",
        )
        observability.observe(
            event_type=observability.ConversationEvents.HEARTBEAT_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "user_id": user_id,
                "request_id": request_id,
                "delivered": bool(result.get("delivered")),
                "channels": result.get("delivered"),
            },
            description=f"Heartbeat for user {user_id} delivered to {result.get('delivered')}",
        )
        return bool(result.get("delivered"))

    def is_within_active_hours(self, now: datetime, user_timezone: Optional[str] = None) -> bool:
        """
        Check the active-hours gate for a moment in time.

        Windows where start <= end are same-day windows; start > end wraps
        past midnight (e.g. 22:00-06:00). With ``timezone: user`` the user's
        stored timezone applies (UTC when the user has none).
        """
        hours = self.config.active_hours
        if hours is None:
            return True

        tz_name = hours.timezone
        if tz_name == "user":
            tz_name = user_timezone or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.utc

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        local_now = now.astimezone(tz)

        if not hours.weekends and local_now.weekday() >= 5:
            return False

        current = local_now.time()
        if hours.start <= hours.end:
            return hours.start <= current <= hours.end
        # Overnight window (e.g. 22:00-06:00)
        return current >= hours.start or current <= hours.end

    def _build_prompt(self) -> str:
        """
        Assemble the heartbeat prompt: formation SOP content (when
        configured and loadable) or the bundled default heartbeat SOP,
        plus the formation's extra instruction.
        """
        base = load_default_heartbeat_sop()
        if self.config.sop:
            sop_content = self._load_sop_content(self.config.sop)
            if sop_content:
                base = sop_content
        if self.config.instruction:
            base = f"{base}\n\n## Additional Instructions\n{self.config.instruction}"
        return base

    def _load_sop_content(self, sop_name: str) -> Optional[str]:
        """Fetch SOP content from the overlord's SOP system (best effort)."""
        try:
            if not self.overlord._ensure_sop_system():
                return None
            sop = self.overlord.sop_system.sops.get(sop_name)
            if sop:
                return sop.get("content")
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={"sop": sop_name, "error": str(e), "error_type": type(e).__name__},
                description=f"Heartbeat SOP '{sop_name}' could not be loaded: {e}",
            )
        return None

    @staticmethod
    def _is_heartbeat_ok(content: str) -> bool:
        """
        Whether a heartbeat response is an all-clear acknowledgment.

        The sentinel is matched anywhere in the response, not only as a
        prefix: agent pipelines (persona formatting, workflow synthesis)
        routinely wrap the agent's raw sentinel in prose ("Everything is
        fine, the check replied with **HEARTBEAT_OK**"). The sentinel
        exists only inside the heartbeat prompt, so a response that
        mentions it is protocol chatter about the check itself -- never a
        legitimate user notification -- and must stay silent.
        """
        return HEARTBEAT_OK_SENTINEL in content

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Extract text content from an overlord chat response."""
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if content is not None:
            return str(content)
        if isinstance(response, dict):
            value = response.get("content") or response.get("response")
            if isinstance(value, str):
                return value
        return str(response)
