"""
Formation and service validation utilities.
"""

import yaml
import socket
from pathlib import Path
from typing import List, Tuple, Dict, Any


class FormationValidator:
    """Validate formations before test execution."""

    REQUIRED_FIELDS = ["id", "llm", "agents"]
    REQUIRED_LLM_FIELDS = ["models"]

    @classmethod
    def validate_formation(cls, formation_path: Path) -> Tuple[bool, List[str]]:
        """
        Validate formation has required fields and structure.

        Args:
            formation_path: Path to formation YAML or directory

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not formation_path.exists():
            return False, [f"Formation not found: {formation_path}"]

        try:
            if formation_path.is_dir():
                # Look for formation.yaml in directory
                yaml_path = formation_path / "formation.yaml"
                if not yaml_path.exists():
                    return False, [f"No formation.yaml in {formation_path}"]
                formation_path = yaml_path

            with open(formation_path) as f:
                config = yaml.safe_load(f)

            if not config:
                return False, ["Empty formation configuration"]

            # Check required fields
            for field in cls.REQUIRED_FIELDS:
                if field not in config:
                    errors.append(f"Missing required field: {field}")

            # Validate LLM configuration
            if "llm" in config:
                if "models" not in config["llm"]:
                    errors.append("LLM configuration missing 'models'")
                else:
                    models = config["llm"]["models"]
                    if not models:
                        errors.append("No models configured")
                    else:
                        # Check for text model (required)
                        has_text = any("text" in str(m) for m in models)
                        if not has_text:
                            errors.append("Missing required text model")

            # Validate agents
            if "agents" in config:
                if not config["agents"]:
                    errors.append("No agents configured")
                else:
                    for i, agent in enumerate(config["agents"]):
                        if isinstance(agent, dict):
                            if "id" not in agent and "path" not in agent:
                                errors.append(f"Agent {i} missing 'id' or 'path'")

            # Check secrets if referenced
            if "secrets_file" in config:
                secrets_path = formation_path.parent / config["secrets_file"]
                if not secrets_path.exists():
                    errors.append(f"Secrets file not found: {secrets_path}")

                # Also check for .key file
                key_path = formation_path.parent / ".key"
                if not key_path.exists():
                    errors.append(f"Key file not found: {key_path}")

            return len(errors) == 0, errors

        except yaml.YAMLError as e:
            return False, [f"Invalid YAML: {e}"]
        except Exception as e:
            return False, [f"Failed to parse formation: {e}"]

    @staticmethod
    def validate_services(required_services: List[Tuple[str, int]]) -> Tuple[bool, List[str]]:
        """
        Verify all required services are accessible.

        Args:
            required_services: List of (service_name, port) tuples

        Returns:
            Tuple of (all_available, list_of_errors)
        """
        errors = []

        for service_name, port in required_services:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                sock.close()

                if result != 0:
                    errors.append(f"{service_name} not available on port {port}")
            except Exception as e:
                errors.append(f"{service_name} check failed: {e}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_credentials(formation_config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Check if required credentials are available.

        Args:
            formation_config: Loaded formation configuration

        Returns:
            Tuple of (has_all_credentials, list_of_missing)
        """
        errors = []

        # These are typically loaded from secrets.enc
        # For now, we'll just check the structure
        if "secrets" in formation_config:
            required_keys = []  # Will be populated based on formation needs

            # Check based on LLM models
            if "llm" in formation_config and "models" in formation_config["llm"]:
                for model in formation_config["llm"]["models"]:
                    if isinstance(model, dict) and "text" in model:
                        model_str = str(model["text"])
                        if "openai" in model_str.lower():
                            required_keys.append("OPENAI_API_KEY")
                        elif "anthropic" in model_str.lower():
                            required_keys.append("ANTHROPIC_API_KEY")

            for key in required_keys:
                # This would check actual secrets in real implementation
                pass  # Placeholder

        return len(errors) == 0, errors
