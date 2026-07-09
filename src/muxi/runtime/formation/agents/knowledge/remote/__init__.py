# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Remote Knowledge Sources
# Description:  Sync remote knowledge sources (HTTP, S3, GCS, Azure, rsync,
#               FTP, SFTP, file) to a local mirror that feeds the existing
#               knowledge pipeline
# Role:         Remote knowledge PRD Phases 1-4 (core sync, archive
#               extraction, scheduling, additional protocols)
# Usage:        Used by KnowledgeHandler.from_agent_config when an agent
#               declares url-based knowledge sources; the overlord registers
#               KnowledgeSyncService for scheduled re-sync + manual triggers
# Author:       Muxi Framework Team
# =============================================================================

from .extractor import ArchiveExtractor, ExtractionResult, is_archive_filename
from .handler import DownloadResult, ProtocolHandler, RemoteFile, RemoteSyncError
from .manifest import Manifest, safe_relative_path
from .scheduler import KnowledgeSyncService, RetryPolicy, resolve_cron_expression
from .sync import SyncManager, SyncResult, is_remote_source, partition_sources

__all__ = [
    "ArchiveExtractor",
    "DownloadResult",
    "ExtractionResult",
    "KnowledgeSyncService",
    "Manifest",
    "ProtocolHandler",
    "RemoteFile",
    "RemoteSyncError",
    "RetryPolicy",
    "SyncManager",
    "SyncResult",
    "is_archive_filename",
    "is_remote_source",
    "partition_sources",
    "resolve_cron_expression",
    "safe_relative_path",
]
