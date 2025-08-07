"""
Runtime agent processor for Formation.

Ensures agents added via API go through the same processing pipeline
as agents loaded during initialization, including:
- Secret interpolation
- MCP server processing
- Knowledge path resolution
- Validation
- Placeholder tracking
"""

from typing import Dict, Any, Tuple, TYPE_CHECKING
from pathlib import Path
from muxi.formation.config.loader import ConfigLoader

if TYPE_CHECKING:
    from .formation import Formation

# Valid MCP transport types
VALID_MCP_TRANSPORT_TYPES = ["stdio", "http", "websocket", "grpc"]

# Module-level ConfigLoader instance to avoid repeated instantiation
_config_loader = ConfigLoader()


async def process_agent_for_runtime(
    formation: "Formation",
    agent_config: Dict[str, Any],
    agent_id: str
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Process an agent configuration for runtime addition.

    This ensures the agent goes through the exact same pipeline as agents
    loaded during initialization, including secret processing, validation,
    and all other transformations.

    Args:
        formation: The Formation instance
        agent_config: Raw agent configuration from API
        agent_id: The agent ID

    Returns:
        Tuple of:
        - Processed agent configuration (with secrets interpolated)
        - Placeholder registry for this agent

    Raises:
        ValueError: If required secrets are missing or config is invalid
    """
    # 1. Process secrets (same as initialization)
    if not hasattr(formation, 'secrets_manager') or not formation.secrets_manager:
        raise RuntimeError("SecretsManager not available for secret processing")

    # Process secrets using the same method as initialization
    processed_config, secrets_used, placeholders = await _config_loader.process_secrets(
        agent_config,
        formation.secrets_manager
    )

    # 2. Track secrets in formation's used secrets (if it tracks them)
    if hasattr(formation, '_secrets_in_use'):
        formation._secrets_in_use.update(secrets_used)

    # 3. Ensure agent has required fields (same as initialization)
    if "id" not in processed_config:
        processed_config["id"] = agent_id

    # 4. Check active status (same as initialization)
    if "active" not in processed_config:
        processed_config["active"] = True

    # 5. Set source to "api" (different from initialization which uses "formation")
    processed_config["source"] = "api"

    # 6. Validate MCP servers if present
    if "mcp_servers" in processed_config:
        # Validate agent-level MCP servers configuration
        mcp_servers = processed_config["mcp_servers"]
        if not isinstance(mcp_servers, list):
            raise ValueError(f"Agent {agent_id} mcp_servers must be a list")

        server_ids = set()
        for i, server_config in enumerate(mcp_servers):
            if not isinstance(server_config, dict):
                raise ValueError(
                    f"Agent {agent_id} MCP server {i} configuration must be a dictionary"
                )

            # Check required fields for agent-level MCP servers
            required_fields = ["id", "description", "type"]
            for field in required_fields:
                if field not in server_config:
                    raise ValueError(
                        f"Agent {agent_id} MCP server {i} missing required field: {field}"
                    )

            # Validate server_id uniqueness within this agent
            server_id = server_config.get("id")
            if server_id:
                if server_id in server_ids:
                    raise ValueError(
                        f"Agent {agent_id} has duplicate MCP server id: {server_id}"
                    )
                server_ids.add(server_id)

            # Validate type field
            server_type = server_config.get("type")
            if server_type not in VALID_MCP_TRANSPORT_TYPES:
                raise ValueError(
                    f"Agent {agent_id} MCP server {server_id or i} has invalid type: {server_type}. "
                    f"Valid types are: {', '.join(VALID_MCP_TRANSPORT_TYPES)}"
                )

    # 7. Process knowledge paths if present
    if "knowledge" in processed_config:
        # Resolve relative paths relative to formation directory
        if hasattr(formation, '_formation_path') and formation._formation_path:
            formation_dir = Path(formation._formation_path).parent
            for knowledge_item in processed_config.get("knowledge", []):
                if isinstance(knowledge_item, dict) and "path" in knowledge_item:
                    path = knowledge_item["path"]
                    if not Path(path).is_absolute():
                        # Make relative paths absolute
                        knowledge_item["path"] = str(formation_dir / path)

    return processed_config, placeholders


async def add_agent_to_overlord_runtime(
    formation: "Formation",
    processed_config: Dict[str, Any]
) -> str:
    """
    Add a processed agent to the running overlord.

    This creates the agent instance and registers it with the overlord,
    ensuring it goes through the same initialization as agents loaded
    during startup.

    Args:
        formation: The Formation instance
        processed_config: Agent configuration that has been processed
                         (secrets interpolated, paths resolved, etc.)

    Returns:
        The agent ID

    Raises:
        RuntimeError: If overlord is not running
        ValueError: If agent creation fails
    """
    # Use public method to add agent to overlord
    # This handles all the agent creation, metadata setup, and workflow component updates
    await formation.add_agent_to_overlord(processed_config)

    return processed_config["id"]
