"""
A2A Cache Manager

This module provides intelligent caching for A2A agent cards based on
configuration hash to avoid regeneration when configs haven't changed.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from .models import AgentCard
from .. import observability
from ...utils.user_dirs import get_a2a_cache_dir


class A2ACacheManager:
    """
    Manages caching of A2A agent cards with hash-based invalidation

    The cache is stored in `~/.muxi/cache/a2a_cards/` directory and uses configuration
    hash to determine if cached cards are still valid.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize cache manager

        Args:
            cache_dir: Directory to store cache files. Defaults to ~/.muxi/cache/a2a_cards/
        """
        if cache_dir is None:
            from ...utils.user_dirs import get_a2a_cards_dir
            cache_dir = get_a2a_cards_dir()

        self.cache_dir = Path(get_a2a_cache_dir())

        # Cache metadata file
        self.metadata_file = self.cache_dir / "metadata.json"
        self._load_metadata()

    def _load_metadata(self) -> None:
        """Load cache metadata from disk"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    self.metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.metadata = {}

        else:
            self.metadata = {}

    def _save_metadata(self) -> None:
        """Save cache metadata to disk"""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self.metadata, f, indent=2)

        except IOError as e:
            print(f"Warning: Failed to save cache metadata: {e}")
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "save_metadata",
                    "error": str(e),
                    "entries_attempted": len(self.metadata),
                },
            )

    def _compute_config_hash(
        self, agent_config: Dict[str, Any], mcp_configs: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Compute hash of agent and MCP configurations

        Args:
            agent_config: Agent YAML configuration
            mcp_configs: Optional MCP server configurations

        Returns:
            SHA256 hash of the combined configuration
        """

        # Create a combined config for hashing
        combined_config = {"agent": agent_config, "mcp": mcp_configs or {}}

        # Sort keys to ensure consistent hashing
        config_str = json.dumps(combined_config, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()

        return config_hash

    def _get_cache_path(self, agent_id: str) -> Path:
        """Get cache file path for an agent"""
        return self.cache_dir / f"{agent_id}.json"

    def is_cached(self, agent_id: str, config_hash: str) -> bool:
        """
        Check if a valid cached agent card exists

        Args:
            agent_id: Unique agent identifier
            config_hash: Current configuration hash

        Returns:
            True if valid cached card exists
        """

        if agent_id not in self.metadata:

            return False

        cache_info = self.metadata[agent_id]

        # Check if configuration hash matches
        if cache_info.get("config_hash") != config_hash:

            return False

        # Check if cache file exists
        cache_path = self._get_cache_path(agent_id)
        file_exists = cache_path.exists()

        return file_exists

    def get_cached_card(self, agent_id: str) -> Optional[AgentCard]:
        """
        Retrieve cached agent card

        Args:
            agent_id: Unique agent identifier

        Returns:
            Cached AgentCard or None if not found/invalid
        """

        cache_path = self._get_cache_path(agent_id)

        if not cache_path.exists():

            return None

        try:
            with open(cache_path, "r") as f:
                card_data = json.load(f)
            card = AgentCard.from_dict(card_data)

            return card

        except (json.JSONDecodeError, IOError, KeyError, ValueError) as e:
            print(f"Warning: Failed to load cached card for {agent_id}: {e}")
            # Remove invalid cache entry
            self._remove_cache_entry(agent_id)

            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "get_cached_card",
                    "agent_id": agent_id,
                    "error": str(e),
                    "action": "removed_invalid_cache",
                },
            )

            return None

    def cache_card(self, agent_id: str, card: AgentCard, config_hash: str) -> None:
        """
        Cache an agent card with metadata

        Args:
            agent_id: Unique agent identifier
            card: AgentCard to cache
            config_hash: Configuration hash for invalidation
        """

        cache_path = self._get_cache_path(agent_id)

        try:
            # Save card to cache file
            with open(cache_path, "w") as f:
                json.dump(card.to_dict(), f, indent=2)

            # Update metadata
            self.metadata[agent_id] = {
                "config_hash": config_hash,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "card_version": card.version,
                "cache_file": str(cache_path.name),
            }

            self._save_metadata()

        except IOError as e:
            print(f"Warning: Failed to cache card for {agent_id}: {e}")
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "cache_card",
                    "agent_id": agent_id,
                    "error": str(e),
                    "cache_path": str(cache_path),
                },
            )

    def _remove_cache_entry(self, agent_id: str) -> None:
        """Remove cache entry and file"""

        cache_path = self._get_cache_path(agent_id)
        file_removed = False
        metadata_removed = False

        # Remove cache file
        if cache_path.exists():
            try:
                cache_path.unlink()
                file_removed = True
            except OSError:
                pass

        # Remove from metadata
        if agent_id in self.metadata:
            del self.metadata[agent_id]
            metadata_removed = True
            self._save_metadata()

    def invalidate_cache(self, agent_id: str) -> None:
        """
        Invalidate cached card for specific agent

        Args:
            agent_id: Agent identifier to invalidate
        """

        self._remove_cache_entry(agent_id)

    def invalidate_all(self) -> None:
        """Invalidate all cached cards"""

        files_removed = 0
        try:
            # Remove all cache files
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name != "cache_metadata.json":
                    cache_file.unlink(missing_ok=True)
                    files_removed += 1

            # Clear metadata
            self.metadata = {}
            self._save_metadata()

        except OSError as e:
            print(f"Warning: Failed to clear cache: {e}")
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "invalidate_all",
                    "error": str(e),
                    "files_removed": files_removed,
                },
            )

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache statistics
        """

        total_cached = len(self.metadata)
        cache_size = 0

        try:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_size += cache_file.stat().st_size
        except OSError:
            cache_size = 0

        stats = {
            "total_cached_cards": total_cached,
            "cache_size_bytes": cache_size,
            "cache_directory": str(self.cache_dir),
            "cached_agents": list(self.metadata.keys()),
        }

        return stats

    def cleanup_orphaned_cache(self) -> int:
        """
        Clean up orphaned cache files (files without metadata entries)

        Returns:
            Number of orphaned files removed
        """

        removed_count = 0

        try:
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.name == "cache_metadata.json":
                    continue

                # Extract agent_id from filename
                agent_id = cache_file.stem

                if agent_id not in self.metadata:
                    cache_file.unlink(missing_ok=True)
                    removed_count += 1

        except OSError as e:
            print(f"Warning: Failed during cache cleanup: {e}")
            observability.observe(
                event_type=observability.ErrorEvents.RETRY_ATTEMPTED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "cleanup_orphaned_cache",
                    "error": str(e),
                    "files_removed_before_error": removed_count,
                },
            )

        return removed_count
