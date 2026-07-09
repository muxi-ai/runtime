# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Remote Knowledge Sources
# Description:  Sync remote knowledge sources (HTTP, S3, rsync, file) to a
#               local mirror that feeds the existing knowledge pipeline
# Role:         Phase 1 core sync infrastructure (PRD: Remote Knowledge Sources)
# Usage:        Used by KnowledgeHandler.from_agent_config when an agent
#               declares url-based knowledge sources
# Author:       Muxi Framework Team
#
# Phase 1 scope: protocol handlers (HTTP, S3, rsync, file), manifest-based
# change detection, and startup-time sync orchestration. Archive extraction
# (Phase 2), cron scheduling (Phase 3), and additional protocols (Phase 4)
# are intentionally out of scope; the module layout leaves seams for them.
# =============================================================================

from .handler import DownloadResult, ProtocolHandler, RemoteFile, RemoteSyncError
from .manifest import Manifest, safe_relative_path
from .sync import SyncManager, SyncResult, is_remote_source, partition_sources

__all__ = [
    "DownloadResult",
    "Manifest",
    "ProtocolHandler",
    "RemoteFile",
    "RemoteSyncError",
    "SyncManager",
    "SyncResult",
    "is_remote_source",
    "partition_sources",
    "safe_relative_path",
]
