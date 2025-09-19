"""
Test formations for credential handling scenarios.

Provides pre-configured formations for testing different credential modes,
auth types, and security configurations.
"""

from typing import Dict, Any


def create_formation_with_redirect_mode() -> Dict[str, Any]:
    """Create formation configured for redirect mode testing."""
    return {
        "user_credentials": {
            "mode": "redirect",
            "redirect_message": "Please configure your credentials in the external credential manager."
        },
        "llm": {
            "models": [{"text": "openai/gpt-4o-mini"}]
        },
        "observability": {
            "enabled": False  # Disable for testing
        },
        "memory": {
            "buffer": {
                "enabled": True,
                "max_size": 10
            },
            "persistent": {
                "enabled": False  # Use in-memory for tests
            },
            "vector": {
                "enabled": False  # Disable for speed
            }
        },
        "services": {
            "scheduler": {"enabled": False},
            "a2a": {"enabled": False},
            "multimodal": {"enabled": False}
        }
    }


def create_formation_with_dynamic_mode() -> Dict[str, Any]:
    """Create formation configured for dynamic mode testing."""
    return {
        "user_credentials": {
            "mode": "dynamic",
            "security_warnings": {
                "basic_auth": True,
                "bearer_tokens": True
            },
            "inline_acceptance": {
                "api_key": True,
                "basic": True,
                "bearer": "require_hint",  # Requires accept_inline=True
                "oauth": False,
                "oauth2": False
            }
        },
        "llm": {
            "models": [{"text": "openai/gpt-4o-mini"}]
        },
        "observability": {
            "enabled": False
        },
        "memory": {
            "buffer": {
                "enabled": True,
                "max_size": 10
            },
            "persistent": {
                "enabled": False
            },
            "vector": {
                "enabled": False
            }
        },
        "services": {
            "scheduler": {"enabled": False},
            "a2a": {"enabled": False},
            "multimodal": {"enabled": False}
        }
    }


def create_formation_with_encryption_enabled() -> Dict[str, Any]:
    """Create formation with encryption explicitly enabled."""
    formation = create_formation_with_dynamic_mode()
    formation["user_credentials"]["encryption"] = {
        "enabled": True,
        "algorithm": "fernet",
        "key_derivation": "pbkdf2",
        "iterations": 100000
    }
    return formation


def create_formation_with_custom_redirect_message() -> Dict[str, Any]:
    """Create formation with custom redirect message."""
    formation = create_formation_with_redirect_mode()
    formation["user_credentials"]["redirect_message"] = (
        "🔐 For security, please use our credential management portal "
        "at https://credentials.example.com to configure your service access tokens."
    )
    return formation


def create_formation_with_auth_type_overrides() -> Dict[str, Any]:
    """Create formation with specific auth type handling overrides."""
    formation = create_formation_with_dynamic_mode()
    formation["user_credentials"]["auth_type_overrides"] = {
        "github": {
            "auth_type": "api_key",
            "accept_inline": True,
            "validation_pattern": r"^ghp_[a-zA-Z0-9]{36}$"
        },
        "openai": {
            "auth_type": "api_key",
            "accept_inline": True,
            "validation_pattern": r"^sk-[a-zA-Z0-9-]{20,}$"
        },
        "slack": {
            "auth_type": "bearer",
            "accept_inline": False,  # Always redirect for Slack
            "redirect_url": "https://api.slack.com/apps"
        },
        "google": {
            "auth_type": "oauth2",
            "accept_inline": False,
            "redirect_url": "https://console.cloud.google.com/apis/credentials"
        }
    }
    return formation


def create_formation_for_security_testing() -> Dict[str, Any]:
    """Create formation optimized for security testing."""
    return {
        "user_credentials": {
            "mode": "dynamic",
            "security": {
                "log_redaction": True,
                "memory_isolation": True,
                "llm_context_protection": True,
                "error_sanitization": True
            },
            "encryption": {
                "enabled": True,
                "per_user_keys": True,
                "key_rotation_days": 90
            }
        },
        "llm": {
            "models": [{"text": "openai/gpt-4o-mini"}]
        },
        "observability": {
            "enabled": True,
            "logging": {
                "level": "DEBUG",
                "filters": ["credential_redaction"]
            }
        },
        "memory": {
            "buffer": {
                "enabled": True,
                "max_size": 50,
                "credential_filtering": True
            },
            "persistent": {
                "enabled": True,
                "encryption": True
            }
        }
    }


def create_formation_for_multi_user_testing() -> Dict[str, Any]:
    """Create formation for multi-user isolation testing."""
    formation = create_formation_with_dynamic_mode()
    formation["multi_user"] = {
        "enabled": True,
        "isolation": {
            "memory": True,
            "credentials": True,
            "sessions": True
        },
        "user_management": {
            "auto_create": True,
            "session_timeout": 3600
        }
    }
    formation["user_credentials"]["per_user_encryption"] = True
    return formation


def create_formation_for_management_testing() -> Dict[str, Any]:
    """Create formation with credential management features enabled."""
    formation = create_formation_with_dynamic_mode()
    formation["user_credentials"]["management"] = {
        "enabled": True,
        "commands": {
            "list": "list my credentials",
            "remove": "remove {service} credentials",
            "update": "update {service} credentials"
        },
        "confirmation_required": ["remove", "update"],
        "audit_logging": True
    }
    return formation


def create_minimal_test_formation() -> Dict[str, Any]:
    """Create minimal formation for basic testing."""
    return {
        "llm": {
            "models": [{"text": "openai/gpt-4o-mini"}]
        },
        "observability": {"enabled": False},
        "memory": {"buffer": {"enabled": False}},
        "services": {}
    }


def create_formation_with_mcp_services() -> Dict[str, Any]:
    """Create formation with mock MCP services for testing."""
    formation = create_formation_with_dynamic_mode()
    formation["mcp"] = {
        "servers": [
            {
                "name": "github",
                "command": ["mock-github-mcp"],
                "auth_type": "api_key",
                "accept_inline": True
            },
            {
                "name": "openai",
                "command": ["mock-openai-mcp"],
                "auth_type": "api_key",
                "accept_inline": True
            },
            {
                "name": "slack",
                "command": ["mock-slack-mcp"],
                "auth_type": "bearer",
                "accept_inline": False
            },
            {
                "name": "google",
                "command": ["mock-google-mcp"],
                "auth_type": "oauth2",
                "accept_inline": False
            },
            {
                "name": "basic_service",
                "command": ["mock-basic-mcp"],
                "auth_type": "basic",
                "accept_inline": True
            }
        ]
    }
    return formation


# Formation templates for specific test scenarios
FORMATION_TEMPLATES = {
    "redirect_mode": create_formation_with_redirect_mode,
    "dynamic_mode": create_formation_with_dynamic_mode,
    "encryption_enabled": create_formation_with_encryption_enabled,
    "custom_redirect": create_formation_with_custom_redirect_message,
    "auth_overrides": create_formation_with_auth_type_overrides,
    "security_testing": create_formation_for_security_testing,
    "multi_user": create_formation_for_multi_user_testing,
    "management": create_formation_for_management_testing,
    "minimal": create_minimal_test_formation,
    "with_mcp": create_formation_with_mcp_services
}


def get_formation_template(template_name: str) -> Dict[str, Any]:
    """Get a formation template by name."""
    if template_name not in FORMATION_TEMPLATES:
        raise ValueError(f"Unknown formation template: {template_name}")

    return FORMATION_TEMPLATES[template_name]()


def get_all_template_names() -> list[str]:
    """Get all available formation template names."""
    return list(FORMATION_TEMPLATES.keys())


# Service configurations for testing different auth types
MCP_SERVICE_CONFIGS = {
    "api_key_service": {
        "auth_type": "api_key",
        "accept_inline": True,
        "validation_pattern": r"^[a-zA-Z0-9-_]{20,}$"
    },
    "basic_auth_service": {
        "auth_type": "basic",
        "accept_inline": True,
        "security_warning": True
    },
    "bearer_token_service": {
        "auth_type": "bearer",
        "accept_inline": "require_hint",
        "validation_pattern": r"^[a-zA-Z0-9-._~+/]+=*$"
    },
    "oauth_service": {
        "auth_type": "oauth",
        "accept_inline": False,
        "redirect_url": "https://oauth.example.com/authorize"
    },
    "oauth2_service": {
        "auth_type": "oauth2",
        "accept_inline": False,
        "redirect_url": "https://oauth2.example.com/authorize"
    },
    "unknown_auth_service": {
        "auth_type": "unknown",
        "accept_inline": False
    }
}


def get_service_config(service_type: str) -> Dict[str, Any]:
    """Get service configuration for testing."""
    return MCP_SERVICE_CONFIGS.get(service_type, {})


def create_mock_mcp_registry(services: list[str]) -> Dict[str, Any]:
    """Create mock MCP registry with specified services."""
    registry = {}

    for service in services:
        if service in MCP_SERVICE_CONFIGS:
            config = MCP_SERVICE_CONFIGS[service].copy()
            registry[service] = {
                "id": service,
                "name": service.replace("_", " ").title(),
                **config
            }

    return registry
