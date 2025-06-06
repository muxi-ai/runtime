"""
A2A Agent Card Generator

This module provides functionality to automatically generate A2A-compliant agent cards
from existing MUXI agent YAML configurations, with intelligent caching support.
"""

import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timezone
import logging

from .models import (AgentCard, A2ACapability, A2AAuthentication, A2AEndpoint,
                     AuthType, CapabilityType)
from .cache_manager import A2ACacheManager


class AgentCardGenerator:
    """
    Generates A2A agent cards from MUXI agent configurations

    This class reads existing YAML agent configurations and automatically generates
    A2A-compliant agent cards with appropriate capabilities, endpoints, and metadata.
    """

    def __init__(self, cache_manager: Optional[A2ACacheManager] = None):
        """
        Initialize the agent card generator

        Args:
            cache_manager: Optional cache manager for card caching
        """
        self.cache_manager = cache_manager or A2ACacheManager()
        self.logger = logging.getLogger(__name__)

    def load_agent_config(self, config_path: Path) -> Dict[str, Any]:
        """
        Load agent configuration from YAML file

        Args:
            config_path: Path to agent YAML configuration

        Returns:
            Parsed agent configuration
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            self.logger.error(f"Failed to load agent config from {config_path}: {e}")
            raise

    def generate_agent_card(self, config_path: Path, base_url: str,
                          mcp_configs: Optional[Dict[str, Any]] = None,
                          formation_name: Optional[str] = None) -> AgentCard:
        """
        Generate A2A agent card from MUXI agent configuration

        Args:
            config_path: Path to agent YAML configuration
            base_url: Base URL where the agent will be hosted
            mcp_configs: Optional MCP server configurations
            formation_name: Optional formation name for MUXI extensions

        Returns:
            Generated AgentCard
        """
        # Load agent configuration
        agent_config = self.load_agent_config(config_path)

        # Generate cache key
        agent_id = self._extract_agent_id(config_path, agent_config)
        config_hash = self.cache_manager._compute_config_hash(agent_config, mcp_configs)

        # Check cache first
        if self.cache_manager.is_cached(agent_id, config_hash):
            cached_card = self.cache_manager.get_cached_card(agent_id)
            if cached_card:
                self.logger.info(f"Using cached agent card for {agent_id}")
                return cached_card

        # Generate new card
        self.logger.info(f"Generating new agent card for {agent_id}")
        card = self._generate_card_from_config(agent_config, base_url, agent_id, formation_name)

        # Add MCP capabilities if present
        if mcp_configs:
            self._add_mcp_capabilities(card, mcp_configs)

        # Cache the generated card
        self.cache_manager.cache_card(agent_id, card, config_hash)

        return card

    def _extract_agent_id(self, config_path: Path, config: Dict[str, Any]) -> str:
        """Extract unique agent ID from config path and content"""
        # Try to get ID from config first
        agent_id = config.get('id') or config.get('name')

        # Fall back to filename if no ID in config
        if not agent_id:
            agent_id = config_path.stem

        return agent_id

    def _generate_card_from_config(self, config: Dict[str, Any], base_url: str,
                                  agent_id: str, formation_name: Optional[str]) -> AgentCard:
        """Generate agent card from configuration"""

        # Extract basic information
        name = config.get('name', agent_id)
        description = config.get('description', f"MUXI Agent: {name}")
        version = config.get('version', '1.0.0')

        # Ensure base_url ends with agent_id path
        if not base_url.endswith('/'):
            base_url += '/'
        agent_url = f"{base_url.rstrip('/')}"

        # Create base card
        now = datetime.now(timezone.utc).isoformat()
        card = AgentCard(
            name=name,
            description=description,
            version=version,
            url=agent_url,
            muxi_agent_id=agent_id,
            muxi_formation=formation_name,
            created_at=now,
            updated_at=now
        )

        # Add capabilities based on config
        self._add_capabilities_from_config(card, config)

        # Add endpoints
        self._add_standard_endpoints(card, agent_url)

        # Add authentication if specified
        self._add_authentication_from_config(card, config)

        # Add metadata
        self._add_metadata_from_config(card, config)

        return card

    def _add_capabilities_from_config(self, card: AgentCard, config: Dict[str, Any]) -> None:
        """Add capabilities based on agent configuration"""

        # Always add basic capabilities
        card.add_capability(A2ACapability(
            name=CapabilityType.TOOLS.value,
            description="Agent can use tools and perform actions",
            enabled=True
        ))

        # Check for streaming support
        if config.get('streaming', {}).get('enabled', False):
            card.add_capability(A2ACapability(
                name=CapabilityType.STREAMING.value,
                description="Agent supports streaming responses",
                enabled=True
            ))

        # Check for multimodal support
        if config.get('multimodal', {}).get('enabled', False):
            card.add_capability(A2ACapability(
                name=CapabilityType.MULTIMODAL.value,
                description="Agent supports multiple input/output modalities",
                enabled=True,
                metadata={
                    "supported_types": config.get('multimodal', {}).get('types', ['text'])
                }
            ))

        # Check for knowledge capabilities
        if config.get('knowledge', {}).get('enabled', False):
            card.add_capability(A2ACapability(
                name=CapabilityType.KNOWLEDGE.value,
                description="Agent has access to knowledge bases",
                enabled=True,
                metadata={
                    "knowledge_sources": list(config.get('knowledge', {}).get('sources', {}).keys())
                }
            ))

        # Check for form capabilities
        if config.get('forms', {}).get('enabled', False):
            card.add_capability(A2ACapability(
                name=CapabilityType.FORMS.value,
                description="Agent can handle form-based interactions",
                enabled=True
            ))

        # Add specialties as capabilities
        specialties = config.get('specialties', [])
        for specialty in specialties:
            card.add_capability(A2ACapability(
                name=f"specialty_{specialty.lower().replace(' ', '_')}",
                description=f"Specialized knowledge in {specialty}",
                enabled=True,
                metadata={"category": "specialty", "domain": specialty}
            ))

        # Add custom capabilities from config
        custom_capabilities = config.get('capabilities', {})
        for cap_name, cap_config in custom_capabilities.items():
            if isinstance(cap_config, dict) and cap_config.get('enabled', True):
                card.add_capability(A2ACapability(
                    name=cap_name,
                    description=cap_config.get('description', f"Custom capability: {cap_name}"),
                    enabled=True,
                    metadata=cap_config.get('metadata', {})
                ))

    def _add_mcp_capabilities(self, card: AgentCard, mcp_configs: Dict[str, Any]) -> None:
        """Add MCP-related capabilities to the agent card"""

        if mcp_configs:
            # Add MCP tools capability
            mcp_servers = list(mcp_configs.keys())
            card.add_capability(A2ACapability(
                name="mcp_tools",
                description="Agent can access MCP tools and services",
                enabled=True,
                metadata={
                    "mcp_servers": mcp_servers,
                    "total_servers": len(mcp_servers)
                }
            ))

    def _add_standard_endpoints(self, card: AgentCard, base_url: str) -> None:
        """Add standard A2A endpoints"""

        # tasks/send endpoint (required by A2A)
        card.add_endpoint("tasks_send", A2AEndpoint(
            url=f"{base_url}/tasks/send",
            methods=["POST"],
            description="Send a task to the agent"
        ))

        # tasks/subscribe endpoint for streaming
        card.add_endpoint("tasks_subscribe", A2AEndpoint(
            url=f"{base_url}/tasks/subscribe",
            methods=["POST"],
            description="Subscribe to task updates via Server-Sent Events"
        ))

        # Well-known agent card endpoint
        card.add_endpoint("agent_card", A2AEndpoint(
            url=f"{base_url}/.well-known/agent.json",
            methods=["GET"],
            description="Get agent card metadata"
        ))

    def _add_authentication_from_config(self, card: AgentCard, config: Dict[str, Any]) -> None:
        """Add authentication configuration if present"""

        auth_config = config.get('authentication', {})
        if auth_config.get('enabled', False):
            auth_type = auth_config.get('type', 'none')

            # Map MUXI auth types to A2A auth types
            type_mapping = {
                'none': AuthType.NONE,
                'bearer': AuthType.BEARER,
                'api_key': AuthType.API_KEY,
                'oauth2': AuthType.OAUTH2
            }

            card.authentication = A2AAuthentication(
                type=type_mapping.get(auth_type, AuthType.NONE),
                description=auth_config.get('description'),
                required=auth_config.get('required', False)
            )

    def _add_metadata_from_config(self, card: AgentCard, config: Dict[str, Any]) -> None:
        """Add metadata from agent configuration"""

        metadata = {}

        # Add tags if present
        if 'tags' in config:
            metadata['tags'] = config['tags']

        # Add role information
        if 'role' in config:
            metadata['role'] = config['role']

        # Add author information
        if 'author' in config:
            metadata['author'] = config['author']

        # Add license information
        if 'license' in config:
            metadata['license'] = config['license']

        # Add custom metadata
        if 'metadata' in config:
            metadata.update(config['metadata'])

        # Add MUXI-specific metadata
        metadata['muxi_runtime'] = True
        metadata['generated_at'] = datetime.now(timezone.utc).isoformat()

        card.metadata = metadata

    def generate_cards_for_formation(self, config_dir: Path, base_url: str,
                                   formation_name: str) -> Dict[str, AgentCard]:
        """
        Generate agent cards for all agents in a formation

        Args:
            config_dir: Directory containing agent YAML configurations
            base_url: Base URL where agents will be hosted
            formation_name: Name of the formation

        Returns:
            Dictionary mapping agent IDs to their agent cards
        """
        cards = {}

        # Find all YAML config files
        config_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))

        for config_file in config_files:
            try:
                # Generate URL for this specific agent
                agent_config = self.load_agent_config(config_file)
                agent_id = self._extract_agent_id(config_file, agent_config)

                # Create agent-specific URL
                agent_url = f"{base_url.rstrip('/')}/agents/{agent_id}"

                card = self.generate_agent_card(
                    config_file,
                    agent_url,
                    formation_name=formation_name
                )
                cards[agent_id] = card

                self.logger.info(f"Generated card for agent {agent_id}")

            except Exception as e:
                self.logger.error(f"Failed to generate card for {config_file}: {e}")
                continue

        return cards

    def export_cards_to_directory(self, cards: Dict[str, AgentCard],
                                 output_dir: Path) -> None:
        """
        Export agent cards to individual JSON files

        Args:
            cards: Dictionary of agent cards
            output_dir: Directory to write card files
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for agent_id, card in cards.items():
            card_file = output_dir / f"{agent_id}.json"
            try:
                with open(card_file, 'w', encoding='utf-8') as f:
                    f.write(card.to_json(indent=2))
                self.logger.info(f"Exported card for {agent_id} to {card_file}")
            except Exception as e:
                self.logger.error(f"Failed to export card for {agent_id}: {e}")
