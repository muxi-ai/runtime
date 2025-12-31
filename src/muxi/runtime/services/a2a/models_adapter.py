"""
A2A Models SDK Adapter

This module provides adapters between MUXI's custom A2A models and the official A2A SDK types.
It allows for gradual migration while maintaining backward compatibility.
"""

from typing import Dict, Optional, Any, Union

# A2A SDK imports
from a2a.types import (
    AgentCard as SDKAgentCard,
    Message as SDKMessage,
    TextPart as SDKTextPart,
    DataPart as SDKDataPart,
    Role as SDKRole
)

# MUXI models (to be gradually replaced)
from .models import (
    AgentCard as MUXIAgentCard,
    A2ACapability,
    A2AAuthentication,
    AuthType
)


class ModelsAdapter:
    """
    Adapter for converting between MUXI models and A2A SDK types.

    This adapter provides bidirectional conversion between MUXI's custom
    models and the official A2A SDK types, allowing for gradual migration.
    """

    # ============================================================================
    # AgentCard Conversions
    # ============================================================================

    @staticmethod
    def muxi_to_sdk_agent_card(muxi_card: MUXIAgentCard) -> SDKAgentCard:
        """
        Convert MUXI AgentCard to SDK AgentCard.

        Args:
            muxi_card: MUXI AgentCard instance

        Returns:
            SDK AgentCard instance
        """
        # Convert capabilities to SDK format
        capabilities = {}
        if muxi_card.capabilities:
            for name, cap in muxi_card.capabilities.items():
                # SDK expects capabilities as a dict with description
                capabilities[name] = {
                    "description": cap.description or f"Capability: {name}",
                    "enabled": cap.enabled,
                    "metadata": cap.metadata
                }

        # Prepare metadata with MUXI extensions
        metadata = muxi_card.metadata.copy() if muxi_card.metadata else {}

        # Add MUXI-specific fields to metadata
        if muxi_card.muxi_agent_id:
            metadata["muxi_agent_id"] = muxi_card.muxi_agent_id
        if muxi_card.muxi_formation:
            metadata["muxi_formation"] = muxi_card.muxi_formation
        if muxi_card.created_at:
            metadata["created_at"] = muxi_card.created_at
        if muxi_card.updated_at:
            metadata["updated_at"] = muxi_card.updated_at

        # Create SDK AgentCard with all required fields
        return SDKAgentCard(
            name=muxi_card.name,
            description=muxi_card.description,
            version=muxi_card.version,
            url=muxi_card.url,
            capabilities=capabilities,
            # Required fields with defaults
            default_input_modes=["text"],  # Default to text input
            default_output_modes=["text"],  # Default to text output
            skills=[],  # Empty skills list for now
            # Optional fields with metadata
            metadata=metadata
        )

    @staticmethod
    def sdk_to_muxi_agent_card(sdk_card: SDKAgentCard) -> MUXIAgentCard:
        """
        Convert SDK AgentCard to MUXI AgentCard.

        Args:
            sdk_card: SDK AgentCard instance

        Returns:
            MUXI AgentCard instance
        """
        # Convert capabilities from SDK format
        capabilities = {}
        if sdk_card.capabilities:
            for name, cap_data in sdk_card.capabilities.items():
                if isinstance(cap_data, dict):
                    capabilities[name] = A2ACapability(
                        name=name,
                        description=cap_data.get("description"),
                        enabled=cap_data.get("enabled", True),
                        metadata=cap_data.get("metadata", {})
                    )
                else:
                    # Simple capability (just a string or boolean)
                    capabilities[name] = A2ACapability(
                        name=name,
                        enabled=True
                    )

        # Extract MUXI-specific fields from metadata (using copy to avoid mutation)
        metadata = (sdk_card.metadata or {}).copy()
        muxi_agent_id = metadata.pop("muxi_agent_id", None)
        muxi_formation = metadata.pop("muxi_formation", None)
        created_at = metadata.pop("created_at", None)
        updated_at = metadata.pop("updated_at", None)

        # Create MUXI AgentCard
        return MUXIAgentCard(
            name=sdk_card.name,
            description=sdk_card.description,
            version=sdk_card.version,
            url=sdk_card.url,
            capabilities=capabilities,
            metadata=metadata,
            muxi_agent_id=muxi_agent_id,
            muxi_formation=muxi_formation,
            created_at=created_at,
            updated_at=updated_at
        )

    # ============================================================================
    # Message Conversions
    # ============================================================================

    @staticmethod
    def muxi_to_sdk_message(
        muxi_message: Union[str, Dict[str, Any]],
        message_id: str,
        role: SDKRole = SDKRole.user,
        context: Optional[Dict[str, Any]] = None
    ) -> SDKMessage:
        """
        Convert MUXI message format to SDK Message.

        Args:
            muxi_message: MUXI message (string or dict with parts)
            message_id: Unique message ID
            role: Message role (USER, ASSISTANT, SYSTEM)
            context: Optional context/metadata

        Returns:
            SDK Message instance
        """
        parts = []

        if isinstance(muxi_message, str):
            # Simple text message
            parts.append(SDKTextPart(text=muxi_message, kind="text"))
        elif isinstance(muxi_message, dict):
            # Complex message with parts
            if "parts" in muxi_message:
                for part in muxi_message["parts"]:
                    if part.get("type") == "TextPart":
                        parts.append(SDKTextPart(
                            text=part.get("text", ""),
                            kind="text"
                        ))
                    elif part.get("type") == "DataPart":
                        parts.append(SDKDataPart(
                            data=part.get("data", {}),
                            kind="data"
                        ))
            else:
                # Treat entire dict as data
                parts.append(SDKDataPart(data=muxi_message, kind="data"))

        # If no parts created, add empty text part
        if not parts:
            parts.append(SDKTextPart(text="", kind="text"))

        return SDKMessage(
            message_id=message_id,
            role=role,
            parts=parts,
            metadata=context or {},
            kind="message"
        )

    @staticmethod
    def sdk_to_muxi_message(sdk_message: SDKMessage) -> Dict[str, Any]:
        """
        Convert SDK Message to MUXI message format.

        Args:
            sdk_message: SDK Message instance

        Returns:
            MUXI message format (dict with parts)
        """
        parts = []

        for part in sdk_message.parts:
            if isinstance(part, SDKTextPart):
                parts.append({
                    "type": "TextPart",
                    "text": part.text
                })
            elif isinstance(part, SDKDataPart):
                parts.append({
                    "type": "DataPart",
                    "data": part.data
                })

        return {
            "parts": parts,
            "message_id": sdk_message.message_id,
            "role": sdk_message.role.value if hasattr(sdk_message.role, 'value') else str(sdk_message.role),
            "metadata": sdk_message.metadata
        }

    # ============================================================================
    # Response Conversions
    # ============================================================================

    @staticmethod
    def sdk_response_to_muxi(
        sdk_response: Any,
        success: bool = True
    ) -> Dict[str, Any]:
        """
        Convert SDK response to MUXI response format.

        Args:
            sdk_response: Response from SDK
            success: Whether the operation was successful

        Returns:
            MUXI response format
        """
        if hasattr(sdk_response, 'message'):
            # Convert SDK message response
            return {
                "success": success,
                "message": ModelsAdapter.sdk_to_muxi_message(sdk_response.message),
                "message_id": getattr(sdk_response, 'message_id', None),
                "timestamp": getattr(sdk_response, 'timestamp', None)
            }
        elif hasattr(sdk_response, 'to_dict'):
            # SDK object with to_dict method
            return {
                "success": success,
                "data": sdk_response.to_dict()
            }
        else:
            # Generic response
            return {
                "success": success,
                "data": sdk_response
            }

    # ============================================================================
    # Capability Conversions
    # ============================================================================

    @staticmethod
    def muxi_capabilities_to_sdk(
        capabilities: Dict[str, A2ACapability]
    ) -> Dict[str, Any]:
        """
        Convert MUXI capabilities to SDK format.

        Args:
            capabilities: MUXI capabilities dict

        Returns:
            SDK capabilities format
        """
        sdk_capabilities = {}

        for name, cap in capabilities.items():
            sdk_capabilities[name] = {
                "description": cap.description or f"Capability: {name}",
                "enabled": cap.enabled,
                "metadata": cap.metadata
            }

        return sdk_capabilities

    @staticmethod
    def sdk_capabilities_to_muxi(
        capabilities: Dict[str, Any]
    ) -> Dict[str, A2ACapability]:
        """
        Convert SDK capabilities to MUXI format.

        Args:
            capabilities: SDK capabilities dict

        Returns:
            MUXI capabilities format
        """
        muxi_capabilities = {}

        for name, cap_data in capabilities.items():
            if isinstance(cap_data, dict):
                muxi_capabilities[name] = A2ACapability(
                    name=name,
                    description=cap_data.get("description"),
                    enabled=cap_data.get("enabled", True),
                    metadata=cap_data.get("metadata", {})
                )
            else:
                # Simple capability
                muxi_capabilities[name] = A2ACapability(
                    name=name,
                    enabled=True
                )

        return muxi_capabilities

    # ============================================================================
    # Authentication Conversions
    # ============================================================================

    @staticmethod
    def muxi_auth_to_sdk(auth: A2AAuthentication) -> Dict[str, Any]:
        """
        Convert MUXI authentication to SDK format.

        Args:
            auth: MUXI authentication config

        Returns:
            SDK authentication format
        """
        return {
            "type": auth.type.value,
            "description": auth.description,
            "required": auth.required
        }

    @staticmethod
    def sdk_auth_to_muxi(auth_data: Dict[str, Any]) -> A2AAuthentication:
        """
        Convert SDK authentication to MUXI format.

        Args:
            auth_data: SDK authentication dict

        Returns:
            MUXI authentication config
        """
        return A2AAuthentication(
            type=AuthType(auth_data.get("type", "none")),
            description=auth_data.get("description"),
            required=auth_data.get("required", False)
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def create_agent_card(**kwargs) -> SDKAgentCard:
    """
    Factory function to create SDK AgentCard.

    Returns SDK AgentCard.
    """
    return SDKAgentCard(**kwargs)


def convert_agent_card(
    card: Union[MUXIAgentCard, SDKAgentCard],
    to_sdk: bool = True
) -> Union[MUXIAgentCard, SDKAgentCard]:
    """
    Convert AgentCard between MUXI and SDK formats.

    Args:
        card: AgentCard to convert
        to_sdk: If True, convert to SDK format; if False, convert to MUXI format

    Returns:
        Converted AgentCard
    """
    if to_sdk and isinstance(card, MUXIAgentCard):
        return ModelsAdapter.muxi_to_sdk_agent_card(card)
    elif not to_sdk and isinstance(card, SDKAgentCard):
        return ModelsAdapter.sdk_to_muxi_agent_card(card)
    else:
        # Already in desired format
        return card
