# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Protocol Registry - Remote Knowledge Sources
# Description:  Maps URL schemes to protocol handler implementations
# Role:         Single lookup point for scheme -> handler resolution
# Usage:        SyncManager calls create_handler(source_config)
# Author:       Muxi Framework Team
#
# Phase 1 protocols: http(s), s3, rsync(+ssh), file. Phase 4 protocols
# (gs, az, ftp, sftp) are declared in PLANNED_SCHEMES so config validation
# can distinguish "not yet supported" from "unknown scheme".
# =============================================================================

from urllib.parse import urlparse

from ..handler import ProtocolHandler, RemoteSyncError, SourceConfig

# Schemes implemented in Phase 1
SUPPORTED_SCHEMES = frozenset({"http", "https", "s3", "rsync", "rsync+ssh", "file"})

# Schemes on the roadmap (PRD Phase 4) - rejected at validation time with
# a "planned" message rather than "unknown scheme"
PLANNED_SCHEMES = frozenset({"gs", "az", "ftp", "sftp"})


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
    if scheme in ("rsync", "rsync+ssh"):
        from .rsync import RsyncHandler

        return RsyncHandler(config)
    if scheme == "file":
        from .file import FileHandler

        return FileHandler(config)

    raise RemoteSyncError(
        f"Unsupported remote knowledge source scheme '{scheme}' for URL: {config.url}"
    )


__all__ = [
    "PLANNED_SCHEMES",
    "SUPPORTED_SCHEMES",
    "create_handler",
    "get_url_scheme",
]
