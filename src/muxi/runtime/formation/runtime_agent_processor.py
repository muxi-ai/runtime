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

import logging
from typing import Dict, Any, Tuple, TYPE_CHECKING
from pathlib import Path
from muxi.runtime.formation.config.loader import ConfigLoader

if TYPE_CHECKING:
    from .formation import Formation  # noqa: E402

# Get logger for this module
logger = logging.getLogger(__name__)

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

    # 2. Track secrets in formation's used secrets
    if hasattr(formation, 'track_used_secrets'):
        formation.track_used_secrets(secrets_used)

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
        formation_path = formation.get_formation_path()
        if formation_path:
            # Validate formation path is a valid string or Path object
            if not isinstance(formation_path, (str, Path)) or (
                isinstance(formation_path, str) and not formation_path.strip()
            ):
                # Log warning but don't fail - knowledge paths will remain as provided
                logger.warning(
                    f"Agent {agent_id}: Invalid formation path '{formation_path}', "
                    "skipping knowledge path resolution"
                )
            else:
                try:
                    # Safely get the parent directory
                    formation_path_obj = Path(formation_path)
                    formation_dir = formation_path_obj.parent

                    # Verify the parent directory can be determined and exists
                    if not formation_dir or formation_dir == Path("."):
                        # Handle edge case where parent can't be determined
                        # (e.g., bare filename without directory)
                        formation_dir = Path.cwd()
                        logger.info(
                            f"Agent {agent_id}: Formation path '{formation_path}' has no parent directory, "
                            f"using current working directory: {formation_dir}"
                        )
                    elif not formation_dir.exists():
                        # Parent directory doesn't exist - use current directory as fallback
                        logger.warning(
                            f"Agent {agent_id}: Formation parent directory '{formation_dir}' does not exist, "
                            f"using current working directory instead"
                        )
                        formation_dir = Path.cwd()

                    # Process knowledge items with validated formation_dir
                    for knowledge_item in processed_config.get("knowledge", []):
                        if isinstance(knowledge_item, dict) and "path" in knowledge_item:
                            path = knowledge_item["path"]
                            if path and not Path(path).is_absolute():
                                # Make relative paths absolute
                                resolved_path = formation_dir / path
                                knowledge_item["path"] = str(resolved_path)

                except (OSError, ValueError) as e:
                    # Handle any path-related errors gracefully
                    logger.error(
                        f"Agent {agent_id}: Error processing formation path '{formation_path}': {e}. "
                        "Knowledge paths will remain unresolved."
                    )

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
