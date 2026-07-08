"""
Per-user channel state for proactive notifications.

Stores, per external user id:

- ``preferred_channel``: the user's chosen notification channel
- ``channels``: per-channel addressing context (e.g. a Telegram ``chat_id``
  or a Slack ``channel``) used as ``context.*`` variables when rendering the
  channel's transformer
- ``last_channel``: the channel the user's most recent inbound message
  arrived on (the "reply where they are" signal)
- ``timezone``: optional per-user IANA timezone (used by heartbeat active
  hours when ``timezone: user`` is configured)

State is held in memory (authoritative for the process) and written through
to the ``user_channel_state`` table when the formation has persistent memory
configured, so preferences survive restarts. Without a database the store
degrades gracefully to memory-only.
"""

import asyncio
import copy
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, String, Text, select

from ...services import observability
from ...services.db import Base
from ...utils.datetime_utils import utc_now_naive


class UserChannelState(Base):
    """SQLAlchemy model for persisted per-user channel state."""

    __tablename__ = "user_channel_state"

    user_id = Column(String(255), primary_key=True)  # External user id (normalized)
    formation_id = Column(String(255), primary_key=True)
    state = Column(Text, nullable=False)  # JSON blob (portable across PG/SQLite)
    updated_at = Column(
        DateTime,
        default=lambda: utc_now_naive(),
        onupdate=lambda: utc_now_naive(),
    )

    def __repr__(self) -> str:
        """Return a string representation for debugging."""
        return f"<UserChannelState(user_id={self.user_id!r})>"


@dataclass
class _ChannelState:
    """In-memory channel state for a single user."""

    preferred_channel: Optional[str] = None
    channels: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_channel: Optional[str] = None
    timezone: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preferred_channel": self.preferred_channel,
            "channels": self.channels,
            "last_channel": self.last_channel,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "_ChannelState":
        return cls(
            preferred_channel=raw.get("preferred_channel"),
            channels=dict(raw.get("channels") or {}),
            last_channel=raw.get("last_channel"),
            timezone=raw.get("timezone"),
        )


class UserChannelStore:
    """
    Store for per-user channel preferences and last-channel tracking.

    All lookups are served from memory; the optional database backend is a
    write-through persistence layer loaded lazily per user. Persistence
    failures are logged and never propagate: channel state must never break
    the interactive chat path.
    """

    def __init__(self, formation_id: str, async_session_maker: Any = None):
        """
        Args:
            formation_id: The formation id (state is formation-scoped)
            async_session_maker: Optional async SQLAlchemy session factory.
                When None the store is memory-only.
        """
        self.formation_id = formation_id
        self._async_session_maker = async_session_maker
        self._states: Dict[str, _ChannelState] = {}
        self._loaded: set = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_user_id(user_id: Any) -> str:
        """Normalize an external user id the way the overlord chat path does."""
        return str(user_id).lower().strip()

    async def get_state(self, user_id: str) -> Dict[str, Any]:
        """Return a copy of the user's channel state (empty defaults if unset)."""
        user_id = self.normalize_user_id(user_id)
        async with self._lock:
            state = await self._get_or_load(user_id)
            return copy.deepcopy(state.to_dict())

    async def known_users(self) -> List[str]:
        """
        Return user ids with channel state (heartbeat iterates these).

        Includes persisted users when a database is configured, so heartbeats
        keep reaching users after a restart.
        """
        users = set(self._states.keys())
        if self._async_session_maker is not None:
            try:
                async with self._async_session_maker() as session:
                    result = await session.execute(
                        select(UserChannelState.user_id).where(
                            UserChannelState.formation_id == self.formation_id
                        )
                    )
                    users.update(row[0] for row in result.all())
            except Exception as e:
                self._observe_persistence_warning("known_users", e)
        return sorted(users)

    async def set_preferences(
        self,
        user_id: str,
        *,
        preferred_channel: Optional[str] = None,
        channels: Optional[Dict[str, Dict[str, Any]]] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a user's channel preferences (only provided fields change).

        ``channels`` entries are merged per channel; passing an empty dict for
        a channel name removes that channel's addressing context.
        """
        user_id = self.normalize_user_id(user_id)
        async with self._lock:
            state = await self._get_or_load(user_id)
            if preferred_channel is not None:
                state.preferred_channel = preferred_channel or None
            if channels is not None:
                for name, context in channels.items():
                    if context:
                        merged = dict(state.channels.get(name) or {})
                        merged.update(context)
                        state.channels[name] = merged
                    else:
                        state.channels.pop(name, None)
            if timezone is not None:
                state.timezone = timezone or None
            await self._persist(user_id, state)
            return copy.deepcopy(state.to_dict())

    async def record_inbound(
        self,
        user_id: str,
        channel: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record that an inbound message from a user arrived on a channel.

        Updates ``last_channel`` and merges any addressing context captured
        from the inbound payload (e.g. a chat id parsed by the trigger's
        ``parse:`` spec) so later notifications can route back to the same
        place. Never raises.
        """
        try:
            user_id = self.normalize_user_id(user_id)
            async with self._lock:
                state = await self._get_or_load(user_id)
                state.last_channel = channel
                if context:
                    merged = dict(state.channels.get(channel) or {})
                    # Sparse platform payloads routinely omit optional fields;
                    # only overwrite with concrete values.
                    merged.update({k: v for k, v in context.items() if v is not None})
                    state.channels[channel] = merged
                await self._persist(user_id, state)
            observability.observe(
                event_type=observability.ConversationEvents.USER_CHANNEL_RECORDED,
                level=observability.EventLevel.DEBUG,
                data={"user_id": user_id, "channel": channel},
                description=f"Recorded inbound channel '{channel}' for user {user_id}",
            )
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "user_id": str(user_id),
                    "channel": channel,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Failed to record inbound channel for user {user_id}: {e}",
            )

    async def _get_or_load(self, user_id: str) -> _ChannelState:
        """
        Return the in-memory state, loading from the database on first access.

        Callers MUST hold ``self._lock``: the DB load awaits, and without the
        lock a concurrent first-access load could overwrite in-memory state
        that another caller just modified and persisted (losing e.g. a fresh
        ``last_channel``). Load-if-absent is enforced with a re-check after
        the await as a second line of defense.
        """
        if user_id in self._states:
            return self._states[user_id]

        state = _ChannelState()
        if self._async_session_maker is not None and user_id not in self._loaded:
            try:
                async with self._async_session_maker() as session:
                    row = await session.get(UserChannelState, (user_id, self.formation_id))
                    if row is not None:
                        state = _ChannelState.from_dict(json.loads(row.state))
            except Exception as e:
                self._observe_persistence_warning("load", e)

        # Never clobber an entry created while the load awaited: the
        # in-memory state is authoritative for the process lifetime.
        if user_id in self._states:
            return self._states[user_id]

        self._loaded.add(user_id)
        self._states[user_id] = state
        return state

    async def _persist(self, user_id: str, state: _ChannelState) -> None:
        """Write the state through to the database (best effort)."""
        if self._async_session_maker is None:
            return
        try:
            payload = json.dumps(state.to_dict())
            async with self._async_session_maker() as session:
                row = await session.get(UserChannelState, (user_id, self.formation_id))
                if row is None:
                    session.add(
                        UserChannelState(
                            user_id=user_id,
                            formation_id=self.formation_id,
                            state=payload,
                        )
                    )
                else:
                    row.state = payload
                await session.commit()
        except Exception as e:
            self._observe_persistence_warning("persist", e)

    def _observe_persistence_warning(self, operation: str, error: Exception) -> None:
        """Log a persistence failure without breaking the caller."""
        observability.observe(
            event_type=observability.ErrorEvents.WARNING,
            level=observability.EventLevel.WARNING,
            data={
                "operation": f"user_channel_state_{operation}",
                "error": str(error),
                "error_type": type(error).__name__,
            },
            description=f"User channel state {operation} failed (memory state still valid): {error}",
        )
