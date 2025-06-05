"""
Formation configuration validation utilities.

This module provides tools for validating formation configurations,
detecting common issues, and ensuring configurations are well-formed.
"""

import logging
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import yaml
import json

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when formation validation fails."""
    pass


class ValidationResult:
    """
    Result of formation validation.

    Contains information about validation status, errors, warnings,
    and suggestions for fixing issues.
    """

    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.suggestions: List[str] = []
        self.context: Dict[str, Any] = {}

    def add_error(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Add a validation error."""
        self.is_valid = False
        self.errors.append(message)
        if context:
            self.context.update(context)

    def add_warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Add a validation warning."""
        self.warnings.append(message)
        if context:
            self.context.update(context)

    def add_suggestion(self, message: str):
        """Add a suggestion for improvement."""
        self.suggestions.append(message)

    def summary(self) -> str:
        """Get a summary of validation results."""
        if self.is_valid and not self.warnings:
            return "✅ Formation configuration is valid"

        parts = []
        if not self.is_valid:
            parts.append(f"❌ {len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"⚠️  {len(self.warnings)} warning(s)")
        if self.suggestions:
            parts.append(f"💡 {len(self.suggestions)} suggestion(s)")

        return " | ".join(parts)

    def detailed_report(self) -> str:
        """Get a detailed validation report."""
        lines = [self.summary(), ""]

        if self.errors:
            lines.append("ERRORS:")
            for i, error in enumerate(self.errors, 1):
                lines.append(f"  {i}. {error}")
            lines.append("")

        if self.warnings:
            lines.append("WARNINGS:")
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"  {i}. {warning}")
            lines.append("")

        if self.suggestions:
            lines.append("SUGGESTIONS:")
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {suggestion}")
            lines.append("")

        return "\n".join(lines)


class FormationValidator:
    """
    Comprehensive formation configuration validator.

    Validates both flattened formation files and modular formation directories,
    checking for structural issues, missing required fields, invalid references,
    and providing suggestions for improvements.
    """

    REQUIRED_FORMATION_FIELDS = ['name', 'version']
    REQUIRED_AGENT_FIELDS = ['agent_id', 'model']
    REQUIRED_MODEL_FIELDS = ['provider']
    REQUIRED_MCP_SERVER_FIELDS = ['id']

    def __init__(self):
        self.result = ValidationResult()

    def validate(
        self,
        formation_path: Union[str, Path],
        secrets_manager: Optional[Any] = None
    ) -> ValidationResult:
        """
        Validate a formation configuration.

        Args:
            formation_path: Path to formation file or directory
            secrets_manager: Optional secrets manager for credential validation

        Returns:
            ValidationResult: Comprehensive validation results
        """
        self.result = ValidationResult()
        formation_path = Path(formation_path)

        try:
            # Check if path exists
            if not formation_path.exists():
                self.result.add_error(f"Formation path does not exist: {formation_path}")
                return self.result

            # Determine formation type and validate accordingly
            if formation_path.is_file():
                self._validate_flattened_formation(formation_path, secrets_manager)
            elif formation_path.is_dir():
                self._validate_modular_formation(formation_path, secrets_manager)
            else:
                self.result.add_error(
                    f"Formation path is neither file nor directory: {formation_path}"
                )

        except Exception as e:
            self.result.add_error(f"Validation failed with exception: {str(e)}")

        return self.result

    def _validate_flattened_formation(
        self,
        file_path: Path,
        secrets_manager: Optional[Any]
    ) -> None:
        """Validate a flattened formation file."""
        try:
            # Load and parse the file
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    config = yaml.safe_load(f)
                elif file_path.suffix.lower() == '.json':
                    config = json.load(f)
                else:
                    self.result.add_error(f"Unsupported file format: {file_path.suffix}")
                    return

            if not isinstance(config, dict):
                self.result.add_error("Formation configuration must be a dictionary")
                return

            # Validate basic structure
            self._validate_formation_structure(config)

            # Validate agents
            if 'agents' in config:
                self._validate_agents(config['agents'])

            # Validate MCP servers
            if 'mcp' in config:
                self._validate_mcp_config(config['mcp'])

            # Validate A2A configuration
            if 'a2a' in config:
                self._validate_a2a_config(config['a2a'])

            # Validate knowledge configuration
            if 'knowledge' in config:
                self._validate_knowledge_config(config['knowledge'], file_path.parent)

        except yaml.YAMLError as e:
            self.result.add_error(f"YAML parsing error: {str(e)}")
        except json.JSONDecodeError as e:
            self.result.add_error(f"JSON parsing error: {str(e)}")
        except Exception as e:
            self.result.add_error(f"Error validating flattened formation: {str(e)}")

    def _validate_modular_formation(
        self,
        dir_path: Path,
        secrets_manager: Optional[Any]
    ) -> None:
        """Validate a modular formation directory."""
        try:
            # Check for formation.yaml
            formation_file = dir_path / 'formation.yaml'
            if not formation_file.exists():
                formation_file = dir_path / 'formation.yml'

            if not formation_file.exists():
                self.result.add_error("Missing formation.yaml file in modular formation")
                return

            # Load main formation config
            with open(formation_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                self.result.add_error("Formation configuration must be a dictionary")
                return

            # Validate basic structure
            self._validate_formation_structure(config)

            # Validate component directories
            self._validate_agents_directory(dir_path / 'agents')
            self._validate_mcp_directory(dir_path / 'mcp')
            self._validate_a2a_directory(dir_path / 'a2a')
            self._validate_knowledge_directory(dir_path / 'knowledge')

        except Exception as e:
            self.result.add_error(f"Error validating modular formation: {str(e)}")

    def _validate_formation_structure(self, config: Dict[str, Any]) -> None:
        """Validate basic formation structure."""
        # Check required fields
        for field in self.REQUIRED_FORMATION_FIELDS:
            if field not in config:
                self.result.add_error(f"Missing required formation field: {field}")

        # Validate name
        if 'name' in config:
            name = config['name']
            if not isinstance(name, str) or not name.strip():
                self.result.add_error("Formation name must be a non-empty string")

        # Validate version
        if 'version' in config:
            version = config['version']
            if not isinstance(version, str) or not version.strip():
                self.result.add_error("Formation version must be a non-empty string")

        # Check for unknown top-level fields
        known_fields = {
            'name', 'version', 'description', 'author', 'agents', 'mcp',
            'a2a', 'knowledge', 'overlord', 'secrets'
        }
        unknown_fields = set(config.keys()) - known_fields
        if unknown_fields:
            self.result.add_warning(f"Unknown formation fields: {list(unknown_fields)}")

    def _validate_agents(self, agents_config: List[Dict[str, Any]]) -> None:
        """Validate agents configuration."""
        if not isinstance(agents_config, list):
            self.result.add_error("Agents configuration must be a list")
            return

        agent_ids = set()
        for i, agent_config in enumerate(agents_config):
            if not isinstance(agent_config, dict):
                self.result.add_error(f"Agent {i} configuration must be a dictionary")
                continue

            # Check required fields
            for field in self.REQUIRED_AGENT_FIELDS:
                if field not in agent_config:
                    self.result.add_error(f"Agent {i} missing required field: {field}")

            # Validate agent_id uniqueness
            agent_id = agent_config.get('agent_id')
            if agent_id:
                if agent_id in agent_ids:
                    self.result.add_error(f"Duplicate agent_id: {agent_id}")
                agent_ids.add(agent_id)

            # Validate model configuration
            if 'model' in agent_config:
                self._validate_model_config(agent_config['model'], f"Agent {agent_id or i}")

            # Validate knowledge configuration
            if 'knowledge' in agent_config:
                self._validate_agent_knowledge_config(agent_config['knowledge'])

    def _validate_model_config(self, model_config: Dict[str, Any], context: str) -> None:
        """Validate model configuration."""
        if not isinstance(model_config, dict):
            self.result.add_error(f"{context} model configuration must be a dictionary")
            return

        # Check required fields
        for field in self.REQUIRED_MODEL_FIELDS:
            if field not in model_config:
                self.result.add_error(f"{context} model missing required field: {field}")

        # Validate provider
        provider = model_config.get('provider')
        if provider:
            known_providers = {'openai', 'anthropic', 'ollama', 'groq', 'openrouter'}
            if provider not in known_providers:
                self.result.add_warning(f"{context} uses unknown provider: {provider}")

    def _validate_mcp_config(self, mcp_config: Dict[str, Any]) -> None:
        """Validate MCP configuration."""
        if not isinstance(mcp_config, dict):
            self.result.add_error("MCP configuration must be a dictionary")
            return

        # Validate servers
        if 'servers' in mcp_config:
            servers = mcp_config['servers']
            if not isinstance(servers, list):
                self.result.add_error("MCP servers must be a list")
                return

            server_ids = set()
            for i, server_config in enumerate(servers):
                if not isinstance(server_config, dict):
                    self.result.add_error(f"MCP server {i} configuration must be a dictionary")
                    continue

                # Check required fields
                for field in self.REQUIRED_MCP_SERVER_FIELDS:
                    if field not in server_config:
                        self.result.add_error(f"MCP server {i} missing required field: {field}")

                # Validate server_id uniqueness
                server_id = server_config.get('id')
                if server_id:
                    if server_id in server_ids:
                        self.result.add_error(f"Duplicate MCP server id: {server_id}")
                    server_ids.add(server_id)

                # Validate transport configuration
                has_url = 'url' in server_config
                has_command = 'command' in server_config

                if not has_url and not has_command:
                    self.result.add_error(
                        f"MCP server {server_id or i} must have either 'url' or 'command'"
                    )
                elif has_url and has_command:
                    self.result.add_warning(
                        f"MCP server {server_id or i} has both 'url' and 'command' - "
                        f"'url' will be used"
                    )

    def _validate_a2a_config(self, a2a_config: Dict[str, Any]) -> None:
        """Validate A2A configuration."""
        if not isinstance(a2a_config, dict):
            self.result.add_error("A2A configuration must be a dictionary")
            return

        # Validate inbound configuration
        if 'inbound' in a2a_config:
            inbound = a2a_config['inbound']
            if not isinstance(inbound, dict):
                self.result.add_error("A2A inbound configuration must be a dictionary")

        # Validate outbound configuration
        if 'outbound' in a2a_config:
            outbound = a2a_config['outbound']
            if not isinstance(outbound, dict):
                self.result.add_error("A2A outbound configuration must be a dictionary")
                return

            # Validate services
            if 'services' in outbound:
                services = outbound['services']
                if not isinstance(services, list):
                    self.result.add_error("A2A outbound services must be a list")
                    return

                service_ids = set()
                for i, service_config in enumerate(services):
                    if not isinstance(service_config, dict):
                        self.result.add_error(f"A2A service {i} configuration must be a dictionary")
                        continue

                    # Check for service id
                    service_id = service_config.get('id')
                    if service_id:
                        if service_id in service_ids:
                            self.result.add_error(f"Duplicate A2A service id: {service_id}")
                        service_ids.add(service_id)

    def _validate_knowledge_config(self, knowledge_config: Dict[str, Any], base_path: Path) -> None:
        """Validate knowledge configuration."""
        if not isinstance(knowledge_config, dict):
            self.result.add_error("Knowledge configuration must be a dictionary")
            return

        # Validate sources
        if 'sources' in knowledge_config:
            sources = knowledge_config['sources']
            if not isinstance(sources, list):
                self.result.add_error("Knowledge sources must be a list")
                return

            for i, source in enumerate(sources):
                if not isinstance(source, dict):
                    self.result.add_error(f"Knowledge source {i} must be a dictionary")
                    continue

                # Check for path
                path = source.get('path')
                if not path:
                    self.result.add_error(f"Knowledge source {i} missing 'path' field")
                    continue

                # Validate path exists (resolve relative to base_path)
                if not Path(path).is_absolute():
                    full_path = base_path / path
                else:
                    full_path = Path(path)

                if not full_path.exists():
                    self.result.add_warning(f"Knowledge source path does not exist: {path}")

    def _validate_agent_knowledge_config(self, knowledge_config: Dict[str, Any]) -> None:
        """Validate agent-level knowledge configuration."""
        if not isinstance(knowledge_config, dict):
            self.result.add_error("Agent knowledge configuration must be a dictionary")
            return

        # Basic structure validation
        if 'enabled' in knowledge_config:
            enabled = knowledge_config['enabled']
            if not isinstance(enabled, bool):
                self.result.add_error("Agent knowledge 'enabled' must be a boolean")

    def _validate_agents_directory(self, agents_dir: Path) -> None:
        """Validate agents directory in modular formation."""
        if not agents_dir.exists():
            self.result.add_suggestion(
                "Consider adding 'agents/' directory for agent configurations"
            )
            return

        if not agents_dir.is_dir():
            self.result.add_error("'agents' must be a directory")
            return

        # Check for agent files
        agent_files = list(agents_dir.glob('*.yaml')) + list(agents_dir.glob('*.yml'))
        if not agent_files:
            self.result.add_warning("No agent configuration files found in agents/ directory")

        # Validate each agent file
        for agent_file in agent_files:
            try:
                with open(agent_file, 'r', encoding='utf-8') as f:
                    agent_config = yaml.safe_load(f)

                if isinstance(agent_config, dict):
                    # Set agent_id from filename if not provided
                    if 'agent_id' not in agent_config:
                        agent_config['agent_id'] = agent_file.stem

                    self._validate_agents([agent_config])
                else:
                    self.result.add_error(f"Agent file {agent_file.name} must contain a dictionary")

            except Exception as e:
                self.result.add_error(f"Error parsing agent file {agent_file.name}: {str(e)}")

    def _validate_mcp_directory(self, mcp_dir: Path) -> None:
        """Validate MCP directory in modular formation."""
        if not mcp_dir.exists():
            self.result.add_suggestion(
                "Consider adding 'mcp/' directory for MCP server configurations"
            )
            return

        if not mcp_dir.is_dir():
            self.result.add_error("'mcp' must be a directory")
            return

        # Check for MCP files
        mcp_files = list(mcp_dir.glob('*.yaml')) + list(mcp_dir.glob('*.yml'))
        if not mcp_files:
            self.result.add_warning("No MCP configuration files found in mcp/ directory")

        # Validate each MCP file
        for mcp_file in mcp_files:
            try:
                with open(mcp_file, 'r', encoding='utf-8') as f:
                    mcp_config = yaml.safe_load(f)

                if isinstance(mcp_config, dict):
                    # Set id from filename if not provided
                    if 'id' not in mcp_config:
                        mcp_config['id'] = mcp_file.stem

                    # Create servers list structure for validation
                    servers_config = {'servers': [mcp_config]}
                    self._validate_mcp_config(servers_config)
                else:
                    self.result.add_error(f"MCP file {mcp_file.name} must contain a dictionary")

            except Exception as e:
                self.result.add_error(f"Error parsing MCP file {mcp_file.name}: {str(e)}")

    def _validate_a2a_directory(self, a2a_dir: Path) -> None:
        """Validate A2A directory in modular formation."""
        if not a2a_dir.exists():
            self.result.add_suggestion("Consider adding 'a2a/' directory for A2A configurations")
            return

        if not a2a_dir.is_dir():
            self.result.add_error("'a2a' must be a directory")
            return

        # Check for A2A files
        a2a_files = list(a2a_dir.glob('*.yaml')) + list(a2a_dir.glob('*.yml'))
        if not a2a_files:
            self.result.add_warning("No A2A configuration files found in a2a/ directory")

    def _validate_knowledge_directory(self, knowledge_dir: Path) -> None:
        """Validate knowledge directory in modular formation."""
        if not knowledge_dir.exists():
            self.result.add_suggestion("Consider adding 'knowledge/' directory for knowledge files")
            return

        if not knowledge_dir.is_dir():
            self.result.add_error("'knowledge' must be a directory")
            return

        # Check for knowledge files
        knowledge_files = (
            list(knowledge_dir.glob('*.txt')) +
            list(knowledge_dir.glob('*.md')) +
            list(knowledge_dir.glob('*.markdown'))
        )
        if not knowledge_files:
            self.result.add_warning("No knowledge files found in knowledge/ directory")


def validate_formation(
    formation_path: Union[str, Path],
    secrets_manager: Optional[Any] = None
) -> ValidationResult:
    """
    Convenience function to validate a formation configuration.

    Args:
        formation_path: Path to formation file or directory
        secrets_manager: Optional secrets manager for credential validation

    Returns:
        ValidationResult: Comprehensive validation results
    """
    validator = FormationValidator()
    return validator.validate(formation_path, secrets_manager)


def validate_formation_cli(formation_path: Union[str, Path]) -> None:
    """
    CLI-friendly validation function that prints results to console.

    Args:
        formation_path: Path to formation file or directory
    """
    result = validate_formation(formation_path)

    print(result.detailed_report())

    if not result.is_valid:
        exit(1)
