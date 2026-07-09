# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Protocol Registry - Remote Knowledge Sources
# Description:  Maps URL schemes to protocol handler implementations
# Role:         Single lookup point for scheme -> handler resolution
# Usage:        SyncManager calls create_handler(source_config)
# Author:       Muxi Framework Team
#
# Protocol auto-detection: the URL scheme picks the handler. Handler
# imports are local so optional/heavy protocol dependencies (boto3,
# google-cloud-storage, azure-storage-blob, paramiko) are only touched
# when a formation actually declares that protocol; missing optional
# dependencies raise a clear RemoteSyncError naming the install extra.
# =============================================================================

from urllib.parse import urlparse

from ..handler import ProtocolHandler, RemoteSyncError, SourceConfig

# Every scheme with a shipped handler (PRD Phases 1 + 4)
SUPPORTED_SCHEMES = frozenset(
    {"http", "https", "s3", "gs", "az", "rsync", "rsync+ssh", "ftp", "sftp", "file"}
)


def get_url_scheme(url: str) -> str:
    """Extract the lowercase scheme from a source URL ('' if missing)."""
    return urlparse(url).scheme.lower()


def create_handler(config: SourceConfig) -> ProtocolHandler:
    """Create the protocol handler for a normalized source config.

    Imports are local so optional/heavy protocol dependencies are only
    touched when a formation actually declares that protocol.
    """
    scheme = get_url_scheme(config.url)

    if scheme in ("http", "https"):
        from .http import HTTPHandler

        return HTTPHandler(config)
    if scheme == "s3":
        from .s3 import S3Handler

        return S3Handler(config)
    if scheme == "gs":
        from .gcs import GCSHandler

        return GCSHandler(config)
    if scheme == "az":
        from .azure import AzureHandler

        return AzureHandler(config)
    if scheme in ("rsync", "rsync+ssh"):
        from .rsync import RsyncHandler

        return RsyncHandler(config)
    if scheme == "ftp":
        from .ftp import FTPHandler

        return FTPHandler(config)
    if scheme == "sftp":
        from .sftp import SFTPHandler

        return SFTPHandler(config)
    if scheme == "file":
        from .file import FileHandler

        return FileHandler(config)

    raise RemoteSyncError(
        f"Unsupported remote knowledge source scheme '{scheme}' for URL: {config.url}"
    )


__all__ = [
    "SUPPORTED_SCHEMES",
    "create_handler",
    "get_url_scheme",
]
