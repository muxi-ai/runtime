"""
Notification routing for proactive messages.

Routes an outbound message to one or more channels using the routing
precedence from the proactiveness PRD:

    explicit channel(s)  >  user preferred channel  >  formation
    default_channel  >  webhook (existing async webhook behavior)

Channel delivery reuses the trigger transformer machinery end to end
(template substitution, auth, retry/backoff): a channel is simply a named
transformer plus the user's stored addressing context. The ``webhook``
target (and the fallback when every channel delivery fails) posts a
standard notification payload to the formation's async webhook URL via
the existing WebhookManager.

Reserved routing names:

- ``last``: the channel the user's most recent inbound message arrived on
- ``preferred``: the user's preferred channel
- ``webhook``: the formation's async webhook

v1 notifications are text-only; multi-channel arrays are supported.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...services import observability
from ...utils.id_generator import generate_request_id
from ..background.transformers import (
    TransformerConfig,
    deliver_via_transformer,
    load_transformer,
    resolve_transformer_url,
)
from .config import LAST_TARGET, PREFERRED_TARGET, WEBHOOK_TARGET, ProactiveConfig
from .user_channels import UserChannelStore

WEBHOOK_CHANNEL = WEBHOOK_TARGET


class NotificationRouter:
    """
    Routes proactive notifications to channels backed by transformers.

    All transformer configs are loaded eagerly at construction so a
    misconfigured channel fails the formation at startup instead of at
    delivery time.
    """

    def __init__(
        self,
        *,
        config: ProactiveConfig,
        formation_dir: str,
        formation_id: str,
        channel_store: UserChannelStore,
        webhook_manager: Any,
        secrets_manager: Any,
        async_webhook_url: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        """
        Args:
            config: Parsed proactive configuration
            formation_dir: Formation root directory (transformer resolution)
            formation_id: Formation id (webhook payload metadata)
            channel_store: Per-user channel state store
            webhook_manager: The formation's WebhookManager instance
            secrets_manager: The formation's SecretsManager instance
            async_webhook_url: The formation's async webhook URL (fallback)
            agent_name: Best-effort default agent name for template variables

        Raises:
            ValueError: If any declared channel references a missing or
                invalid transformer, or the channel/transformer pair yields
                no delivery URL (fail fast at formation startup)
        """
        self.config = config
        self.formation_id = formation_id
        self.channel_store = channel_store
        self.webhook_manager = webhook_manager
        self.secrets_manager = secrets_manager
        self.async_webhook_url = async_webhook_url
        self.agent_name = agent_name

        self._transformers: Dict[str, TransformerConfig] = {}
        for name, channel in config.channels.items():
            # Raises ValueError on missing/invalid transformer definitions
            transformer = load_transformer(Path(formation_dir), channel.transformer)
            # URL resolution order: channel 'url:' first, transformer's own
            # endpoint.url second; no URL from either source is a startup
            # error (a payload-only template referenced without a destination
            # must fail here, not at delivery time).
            resolve_transformer_url(transformer, channel.url)
            self._transformers[name] = transformer

    async def resolve_channels(
        self, user_id: str, channels: Optional[List[str]] = None
    ) -> List[str]:
        """
        Resolve the concrete delivery channels for a notification.

        Args:
            user_id: External user id
            channels: Optional explicit channel names (may include the
                reserved names ``last``, ``preferred``, and ``webhook``)

        Returns:
            Ordered, de-duplicated list of concrete channel names; every
            entry is either a declared channel or ``webhook``. Falls back
            to ``webhook`` when nothing resolves (existing behavior for
            users with no preference).
        """
        state = await self.channel_store.get_state(user_id)
        return self._resolve_channels_from_state(state, channels)

    def _resolve_channels_from_state(
        self, state: Dict[str, Any], channels: Optional[List[str]] = None
    ) -> List[str]:
        """Resolve channels against an already-fetched user state snapshot."""
        resolved: List[str] = []

        requested = channels if channels else [PREFERRED_TARGET]
        for name in requested:
            concrete = self._resolve_single(name, state)
            if concrete and concrete not in resolved:
                resolved.append(concrete)

        if not resolved:
            resolved = [WEBHOOK_TARGET]
        return resolved

    def _resolve_single(self, name: str, state: Dict[str, Any]) -> Optional[str]:
        """Resolve one requested channel name against user state and config."""
        if name == LAST_TARGET:
            # last -> preferred -> default -> webhook
            candidate = (
                state.get("last_channel")
                or state.get("preferred_channel")
                or self.config.default_channel
            )
        elif name == PREFERRED_TARGET:
            # preferred -> default -> webhook
            candidate = state.get("preferred_channel") or self.config.default_channel
        else:
            candidate = name

        if candidate is None or candidate == WEBHOOK_TARGET:
            return WEBHOOK_TARGET
        if candidate in self.config.channels:
            return candidate

        # Unknown channel (stale preference or explicit typo): fall back to
        # webhook rather than dropping the notification.
        observability.observe(
            event_type=observability.ConversationEvents.NOTIFICATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "requested": name,
                "resolved": candidate,
                "declared_channels": sorted(self.config.channels),
            },
            description=(
                f"Notification channel {candidate!r} is not declared in "
                "'proactive.channels'; falling back to webhook"
            ),
        )
        return WEBHOOK_TARGET

    async def notify(
        self,
        *,
        user_id: str,
        message: str,
        channels: Optional[List[str]] = None,
        request_id: Optional[str] = None,
        source: str = "notification",
    ) -> Dict[str, Any]:
        """
        Route and deliver a text notification to a user.

        Args:
            user_id: External user id
            message: Notification text (v1 is text-only)
            channels: Optional explicit channel names (overrides preference)
            request_id: Optional correlation id (generated when absent)
            source: What produced the notification (e.g. "heartbeat", "api")

        Returns:
            Dict with ``channels`` (resolved), ``delivered``, ``failed``,
            and ``request_id``. Never raises: delivery failures are logged
            and reflected in the result.
        """
        user_id = self.channel_store.normalize_user_id(user_id)
        request_id = request_id or generate_request_id()
        # One state fetch per notification: routing and per-channel
        # addressing both resolve against the same snapshot.
        state = await self.channel_store.get_state(user_id)
        resolved = self._resolve_channels_from_state(state, channels)

        observability.observe(
            event_type=observability.ConversationEvents.NOTIFICATION_ROUTED,
            level=observability.EventLevel.INFO,
            data={
                "request_id": request_id,
                "user_id": user_id,
                "source": source,
                "requested_channels": channels or [PREFERRED_TARGET],
                "resolved_channels": resolved,
            },
            description=f"Notification for user {user_id} routed to {resolved}",
        )

        delivered: List[str] = []
        failed: List[str] = []
        for channel in resolved:
            try:
                if channel == WEBHOOK_TARGET:
                    success = await self._deliver_webhook(
                        user_id=user_id, message=message, request_id=request_id, source=source
                    )
                else:
                    success = await self._deliver_channel(
                        channel=channel,
                        context=state.get("channels", {}).get(channel) or {},
                        user_id=user_id,
                        message=message,
                        request_id=request_id,
                    )
            except Exception as e:
                success = False
                observability.observe(
                    event_type=observability.ConversationEvents.NOTIFICATION_FAILED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "request_id": request_id,
                        "user_id": user_id,
                        "channel": channel,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    description=f"Notification delivery to '{channel}' raised: {e}",
                )

            if success:
                delivered.append(channel)
                observability.observe(
                    event_type=observability.ConversationEvents.NOTIFICATION_DELIVERED,
                    level=observability.EventLevel.INFO,
                    data={
                        "request_id": request_id,
                        "user_id": user_id,
                        "channel": channel,
                        "source": source,
                    },
                    description=f"Notification delivered to '{channel}' for user {user_id}",
                )
            else:
                failed.append(channel)

        # Last-resort fallback: if every channel delivery failed and the
        # webhook was not already attempted, deliver the standard payload
        # to the async webhook so the notification is not silently lost.
        if not delivered and WEBHOOK_TARGET not in resolved:
            if await self._deliver_webhook(
                user_id=user_id,
                message=message,
                request_id=request_id,
                source=source,
                failed_channels=failed,
            ):
                delivered.append(WEBHOOK_TARGET)

        return {
            "request_id": request_id,
            "channels": resolved,
            "delivered": delivered,
            "failed": failed,
        }

    async def _deliver_channel(
        self,
        *,
        channel: str,
        context: Dict[str, Any],
        user_id: str,
        message: str,
        request_id: str,
    ) -> bool:
        """Deliver via the channel's transformer (existing delivery stack)."""
        transformer = self._transformers[channel]
        return await deliver_via_transformer(
            webhook_manager=self.webhook_manager,
            secrets_manager=self.secrets_manager,
            transformer=transformer,
            url_override=self.config.channels[channel].url,
            response_content=message,
            request_user_id=user_id,
            context=context,
            agent_name=self.agent_name,
            request_id=request_id,
            formation_id=self.formation_id,
            # Channel-level webhook fallback is handled once at notify()
            # level (multi-channel arrays must not spam the webhook per
            # failed channel).
            fallback_webhook_url=None,
        )

    async def _deliver_webhook(
        self,
        *,
        user_id: str,
        message: str,
        request_id: str,
        source: str,
        failed_channels: Optional[List[str]] = None,
    ) -> bool:
        """Deliver the standard notification payload to the async webhook."""
        if not self.async_webhook_url:
            observability.observe(
                event_type=observability.ConversationEvents.NOTIFICATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "request_id": request_id,
                    "user_id": user_id,
                    "channel": WEBHOOK_TARGET,
                    "reason": "no_async_webhook_url",
                },
                description=(
                    "Notification resolved to webhook but the formation has no "
                    "'async.webhook_url' configured; notification dropped"
                ),
            )
            return False

        payload: Dict[str, Any] = {
            "request_id": request_id,
            "formation_id": self.formation_id,
            "user_id": user_id,
            "type": "notification",
            "source": source,
            "response": [{"type": "text", "text": message}],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if failed_channels:
            payload["failed_channels"] = failed_channels

        success, _, _ = await self.webhook_manager.deliver_raw(
            url=self.async_webhook_url,
            method="POST",
            headers={"Content-Type": "application/json"},
            body=payload,
            request_id=request_id,
            delivery_type="notification",
            delivery_name=source,
        )
        return success
