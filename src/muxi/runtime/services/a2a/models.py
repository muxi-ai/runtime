"""
A2A Data Models

This module defines the data structures for Google's Agent-to-Agent protocol,
including agent cards, capabilities, and authentication configurations.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json


class A2AVersion(str, Enum):
    """Supported A2A protocol versions"""

    V1_0 = "1.0"


class AuthType(str, Enum):
    """Authentication types supported by A2A"""

    NONE = "none"
    BEARER = "bearer"
    API_KEY = "apiKey"
    OAUTH2 = "oauth2"


class CapabilityType(str, Enum):
    """Types of capabilities an agent can advertise"""

    STREAMING = "streaming"
    PUSH_NOTIFICATIONS = "pushNotifications"
    MULTIMODAL = "multimodal"
    FORMS = "forms"
    TOOLS = "tools"
    KNOWLEDGE = "knowledge"


@dataclass
class A2AAuthentication:
    """Authentication configuration for A2A agent"""

    type: AuthType = AuthType.NONE
    description: Optional[str] = None
    required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {"type": self.type.value}
        if self.description:
            result["description"] = self.description
        if self.required:
            result["required"] = self.required
        return result


@dataclass
class A2ACapability:
    """Represents a capability that an agent can advertise"""

    name: str
    description: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {"name": self.name, "enabled": self.enabled}
        if self.description:
            result["description"] = self.description
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class A2AEndpoint:
    """A2A API endpoint configuration"""

    url: str
    methods: List[str] = field(default_factory=lambda: ["POST"])
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {"url": self.url, "methods": self.methods}
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class AgentCard:
    """
    A2A Agent Card - contains metadata about an agent's capabilities and endpoints

    This follows Google's A2A Agent Card specification and is served at
    /.well-known/agent.json
    """

    # Required fields
    name: str
    description: str
    version: str
    url: str

    # Optional fields
    a2a_version: A2AVersion = A2AVersion.V1_0
    capabilities: Dict[str, A2ACapability] = field(default_factory=dict)
    authentication: Optional[A2AAuthentication] = None
    endpoints: Dict[str, A2AEndpoint] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # MUXI-specific extensions
    muxi_agent_id: Optional[str] = None
    muxi_formation: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def add_capability(self, capability: A2ACapability) -> None:
        """Add a capability to this agent card"""
        self.capabilities[capability.name] = capability

    def add_endpoint(self, name: str, endpoint: A2AEndpoint) -> None:
        """Add an endpoint to this agent card"""
        self.endpoints[name] = endpoint

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "a2aVersion": self.a2a_version.value,
        }

        if self.capabilities:
            result["capabilities"] = {
                name: cap.to_dict() for name, cap in self.capabilities.items()
            }

        if self.authentication:
            result["authentication"] = self.authentication.to_dict()

        if self.endpoints:
            result["endpoints"] = {
                name: endpoint.to_dict() for name, endpoint in self.endpoints.items()
            }

        if self.metadata:
            result["metadata"] = self.metadata

        # Add MUXI extensions if present
        muxi_extensions = {}
        if self.muxi_agent_id:
            muxi_extensions["agentId"] = self.muxi_agent_id
        if self.muxi_formation:
            muxi_extensions["formation"] = self.muxi_formation
        if self.created_at:
            muxi_extensions["createdAt"] = self.created_at
        if self.updated_at:
            muxi_extensions["updatedAt"] = self.updated_at

        if muxi_extensions:
            result["muxiExtensions"] = muxi_extensions

        return result

    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCard":
        """Create AgentCard from dictionary"""
        # Extract required fields
        name = data["name"]
        description = data["description"]
        version = data["version"]
        url = data["url"]

        # Extract optional fields
        a2a_version = A2AVersion(data.get("a2aVersion", "1.0"))

        # Parse capabilities
        capabilities = {}
        if "capabilities" in data and data["capabilities"]:
            for cap_name, cap_data in data["capabilities"].items():
                # Skip if cap_data is None or not a dict
                if not cap_data or not isinstance(cap_data, dict):
                    continue

                try:
                    capabilities[cap_name] = A2ACapability(
                        name=cap_data.get("name", cap_name),  # fallback to cap_name
                        description=cap_data.get("description"),
                        enabled=cap_data.get("enabled", True),
                        metadata=cap_data.get("metadata", {}),
                    )
                except Exception:
                    # Skip malformed capabilities
                    continue

        # Parse authentication
        authentication = None
        if "authentication" in data and data["authentication"]:
            auth_data = data["authentication"]
            try:
                authentication = A2AAuthentication(
                    type=AuthType(auth_data["type"]),
                    description=auth_data.get("description"),
                    required=auth_data.get("required", False),
                )
            except Exception:
                # Skip malformed authentication
                pass

        # Parse endpoints
        endpoints = {}
        if "endpoints" in data and data["endpoints"]:
            for ep_name, ep_data in data["endpoints"].items():
                # Skip if ep_data is None or not a dict
                if not ep_data or not isinstance(ep_data, dict):
                    continue

                try:
                    endpoints[ep_name] = A2AEndpoint(
                        url=ep_data["url"],
                        methods=ep_data.get("methods", ["POST"]),
                        description=ep_data.get("description"),
                    )
                except Exception:
                    # Skip malformed endpoints
                    continue

        # Parse MUXI extensions
        muxi_ext = data.get("muxiExtensions", {}) or {}

        return cls(
            name=name,
            description=description,
            version=version,
            url=url,
            a2a_version=a2a_version,
            capabilities=capabilities,
            authentication=authentication,
            endpoints=endpoints,
            metadata=data.get("metadata", {}) or {},
            muxi_agent_id=muxi_ext.get("agentId"),
            muxi_formation=muxi_ext.get("formation"),
            created_at=muxi_ext.get("createdAt"),
            updated_at=muxi_ext.get("updatedAt"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "AgentCard":
        """Create AgentCard from JSON string"""
        return cls.from_dict(json.loads(json_str))
