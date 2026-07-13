from typing import Any, Dict, Optional


def get_service_identifier(service_config: Dict[str, Any]) -> Optional[str]:
    """Return the canonical service identifier, accepting the legacy alias."""
    for key in ("id", "service_id"):
        value = service_config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
