"""
A2A Models SDK Adapter (a2a-sdk 1.0)

Bidirectional conversion between MUXI domain types and the a2a-sdk 1.0
protobuf wire types. All protobuf/pydantic boilerplate is isolated in
`_sdk_helpers`; this module stays at the MUXI-domain level.

Notable 1.0 API shifts baked into this adapter:
  * Part is a protobuf message with a `content` oneof; no `.kind` attribute.
    `isinstance(part, TextPart)` is gone — use `WhichOneof('content')`.
  * Message construction takes `parts=[Part(...)]`, `role=Role.ROLE_USER`,
    and `metadata` must be a `google.protobuf.Struct`.
  * AgentCard lost its top-level `url` field. The agent's endpoint URL is
    now carried via `supported_interfaces[].url`.
  * AgentCapabilities is a fixed-schema protobuf (streaming,
    push_notifications, extensions, extended_agent_card). Per-capability
    metadata that MUXI used to stash under AgentCard.capabilities is now
    routed through `AgentCard.skills[]`, one skill per MUXI capability.
  * MUXI extensions (muxi_agent_id, muxi_formation, created_at, updated_at,
    metadata) survive the round-trip via a single sentinel skill whose
    description holds a JSON blob.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from a2a.types import (
    AgentCapabilities as SDKAgentCapabilities,
    AgentCard as SDKAgentCard,
    AgentInterface as SDKAgentInterface,
    AgentSkill as SDKAgentSkill,
    Message as SDKMessage,
)

from ...utils.fastjson import json
from . import _sdk_helpers as sdk
from .models import (
    A2AAuthentication,
    A2ACapability,
    AgentCard as MUXIAgentCard,
    AuthType,
)

# Sentinel skill id used to carry MUXI-only metadata through the SDK AgentCard.
_MUXI_METADATA_SKILL_ID = "_muxi_metadata"


class ModelsAdapter:
    """Bidirectional converter between MUXI and a2a-sdk 1.0 types."""

    # ------------------------------------------------------------------
    # AgentCard
    # ------------------------------------------------------------------

    @staticmethod
    def muxi_to_sdk_agent_card(muxi_card: MUXIAgentCard) -> SDKAgentCard:
        """Convert a MUXI AgentCard to an SDK AgentCard."""
        skills: List[SDKAgentSkill] = []

        for cap_name, cap in (muxi_card.capabilities or {}).items():
            skills.append(
                SDKAgentSkill(
                    id=cap_name,
                    name=cap_name,
                    description=cap.description or f"Capability: {cap_name}",
                    tags=_capability_tags(cap),
                )
            )

        muxi_blob = _build_muxi_metadata_blob(muxi_card)
        if muxi_blob:
            skills.append(
                SDKAgentSkill(
                    id=_MUXI_METADATA_SKILL_ID,
                    name=_MUXI_METADATA_SKILL_ID,
                    description=muxi_blob,
                    tags=["muxi:internal"],
                )
            )

        interfaces: List[SDKAgentInterface] = []
        if muxi_card.url:
            interfaces.append(SDKAgentInterface(url=muxi_card.url))

        capabilities_pb = SDKAgentCapabilities(
            streaming=_capability_enabled(muxi_card, "streaming"),
            push_notifications=_capability_enabled(muxi_card, "pushNotifications"),
        )

        return SDKAgentCard(
            name=muxi_card.name or "",
            description=muxi_card.description or "",
            version=muxi_card.version or "",
            supported_interfaces=interfaces,
            capabilities=capabilities_pb,
            default_input_modes=["text"],
            default_output_modes=["text"],
            skills=skills,
        )

    @staticmethod
    def sdk_to_muxi_agent_card(sdk_card: SDKAgentCard) -> MUXIAgentCard:
        """Convert an SDK AgentCard back to a MUXI AgentCard."""
        capabilities: Dict[str, A2ACapability] = {}
        muxi_blob: Optional[str] = None

        for skill in sdk_card.skills:
            if skill.id == _MUXI_METADATA_SKILL_ID:
                muxi_blob = skill.description
                continue
            capabilities[skill.name or skill.id] = _skill_to_capability(skill)

        # Restore MUXI metadata from sentinel skill, if present.
        metadata: Dict[str, Any] = {}
        muxi_agent_id = None
        muxi_formation = None
        created_at = None
        updated_at = None
        if muxi_blob:
            try:
                parsed = json.loads(muxi_blob)
                metadata = parsed.get("metadata") or {}
                muxi_agent_id = parsed.get("muxi_agent_id")
                muxi_formation = parsed.get("muxi_formation")
                created_at = parsed.get("created_at")
                updated_at = parsed.get("updated_at")
            except Exception:
                metadata = {}

        url = ""
        if sdk_card.supported_interfaces:
            url = sdk_card.supported_interfaces[0].url or ""

        return MUXIAgentCard(
            name=sdk_card.name,
            description=sdk_card.description,
            version=sdk_card.version,
            url=url,
            capabilities=capabilities,
            metadata=metadata,
            muxi_agent_id=muxi_agent_id,
            muxi_formation=muxi_formation,
            created_at=created_at,
            updated_at=updated_at,
        )

    # ------------------------------------------------------------------
    # Message
    # ------------------------------------------------------------------

    @staticmethod
    def muxi_to_sdk_message(
        muxi_message: Union[str, Dict[str, Any]],
        message_id: str,
        role: int = sdk.ROLE_USER,
        context: Optional[Dict[str, Any]] = None,
    ) -> SDKMessage:
        """Convert a MUXI message (string or dict-with-parts) to an SDK Message."""
        parts = []

        if isinstance(muxi_message, str):
            parts.append(sdk.make_text_part(muxi_message))
        elif isinstance(muxi_message, dict):
            if "parts" in muxi_message:
                for part_dict in muxi_message["parts"]:
                    parts.append(sdk.muxi_part_to_sdk(part_dict))
            else:
                parts.append(sdk.make_data_part(muxi_message))

        if not parts:
            parts.append(sdk.make_text_part(""))

        resolved_role = role if isinstance(role, int) else sdk.role_from_name(str(role))

        return sdk.make_message(
            message_id=message_id,
            role=resolved_role,
            parts=parts,
            metadata=context,
        )

    @staticmethod
    def sdk_to_muxi_message(sdk_message: SDKMessage) -> Dict[str, Any]:
        """Convert an SDK Message to a MUXI message dict."""
        return {
            "parts": sdk.parts_to_muxi_list(sdk_message.parts),
            "message_id": sdk_message.message_id,
            "role": sdk.role_name(sdk_message.role),
            "metadata": sdk.message_metadata(sdk_message),
        }

    # ------------------------------------------------------------------
    # Responses
    # ------------------------------------------------------------------

    @staticmethod
    def sdk_response_to_muxi(sdk_response: Any, success: bool = True) -> Dict[str, Any]:
        """Convert an SDK SendMessageResponse (or duck-typed object) to MUXI form."""
        if sdk_response is None:
            return {"success": success, "data": None}
        # SendMessageResponse has both `task` and `message` fields in 1.0;
        # only one will be populated at a time.
        message_attr = getattr(sdk_response, "message", None)
        if message_attr is not None and getattr(message_attr, "message_id", ""):
            return {
                "success": success,
                "message": ModelsAdapter.sdk_to_muxi_message(message_attr),
            }
        task_attr = getattr(sdk_response, "task", None)
        if task_attr is not None and getattr(task_attr, "id", ""):
            return {
                "success": success,
                "task_id": task_attr.id,
                "task_state": (
                    sdk.task_state_name(getattr(task_attr, "status", 0).state)
                    if hasattr(task_attr, "status")
                    else None
                ),
            }
        if hasattr(sdk_response, "to_dict"):
            return {"success": success, "data": sdk_response.to_dict()}
        return {"success": success, "data": sdk_response}

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    @staticmethod
    def muxi_capabilities_to_sdk(
        capabilities: Dict[str, A2ACapability],
    ) -> Dict[str, Any]:
        """Project MUXI capabilities into a plain-dict representation used by MUXI APIs."""
        return {
            name: {
                "description": cap.description or f"Capability: {name}",
                "enabled": cap.enabled,
                "metadata": cap.metadata or {},
            }
            for name, cap in (capabilities or {}).items()
        }

    @staticmethod
    def sdk_capabilities_to_muxi(
        capabilities: Dict[str, Any],
    ) -> Dict[str, A2ACapability]:
        """Inverse of muxi_capabilities_to_sdk for dict-shaped payloads."""
        out: Dict[str, A2ACapability] = {}
        for name, cap_data in (capabilities or {}).items():
            if isinstance(cap_data, dict):
                out[name] = A2ACapability(
                    name=name,
                    description=cap_data.get("description"),
                    enabled=cap_data.get("enabled", True),
                    metadata=cap_data.get("metadata", {}),
                )
            else:
                out[name] = A2ACapability(name=name, enabled=True)
        return out

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @staticmethod
    def muxi_auth_to_sdk(auth: A2AAuthentication) -> Dict[str, Any]:
        return {
            "type": auth.type.value,
            "description": auth.description,
            "required": auth.required,
        }

    @staticmethod
    def sdk_auth_to_muxi(auth_data: Dict[str, Any]) -> A2AAuthentication:
        return A2AAuthentication(
            type=AuthType(auth_data.get("type", "none")),
            description=auth_data.get("description"),
            required=auth_data.get("required", False),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _capability_tags(cap: A2ACapability) -> List[str]:
    tags = [f"muxi:enabled={'true' if cap.enabled else 'false'}"]
    if cap.metadata:
        try:
            tags.append(f"muxi:meta={json.dumps(cap.metadata)}")
        except Exception:
            # Non-serializable metadata silently dropped; preserved elsewhere.
            pass
    return tags


def _skill_to_capability(skill: SDKAgentSkill) -> A2ACapability:
    enabled = True
    metadata: Dict[str, Any] = {}
    for tag in skill.tags or []:
        if tag == "muxi:enabled=false":
            enabled = False
        elif tag == "muxi:enabled=true":
            enabled = True
        elif tag.startswith("muxi:meta="):
            try:
                metadata = json.loads(tag[len("muxi:meta=") :])
            except Exception:
                metadata = {}
    return A2ACapability(
        name=skill.name or skill.id,
        description=skill.description or None,
        enabled=enabled,
        metadata=metadata,
    )


def _capability_enabled(card: MUXIAgentCard, name: str) -> bool:
    cap = (card.capabilities or {}).get(name)
    return bool(cap and cap.enabled)


def _build_muxi_metadata_blob(card: MUXIAgentCard) -> Optional[str]:
    payload: Dict[str, Any] = {}
    if card.metadata:
        payload["metadata"] = card.metadata
    if card.muxi_agent_id:
        payload["muxi_agent_id"] = card.muxi_agent_id
    if card.muxi_formation:
        payload["muxi_formation"] = card.muxi_formation
    if card.created_at:
        payload["created_at"] = card.created_at
    if card.updated_at:
        payload["updated_at"] = card.updated_at
    if not payload:
        return None
    try:
        return json.dumps(payload)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Convenience functions (compatibility wrappers)
# ---------------------------------------------------------------------------


def create_agent_card(**kwargs) -> SDKAgentCard:
    """Factory function to create an SDK AgentCard."""
    return SDKAgentCard(**kwargs)


def convert_agent_card(
    card: Union[MUXIAgentCard, SDKAgentCard], to_sdk: bool = True
) -> Union[MUXIAgentCard, SDKAgentCard]:
    """Convert AgentCard between MUXI and SDK formats."""
    if to_sdk and isinstance(card, MUXIAgentCard):
        return ModelsAdapter.muxi_to_sdk_agent_card(card)
    if not to_sdk and isinstance(card, SDKAgentCard):
        return ModelsAdapter.sdk_to_muxi_agent_card(card)
    return card
