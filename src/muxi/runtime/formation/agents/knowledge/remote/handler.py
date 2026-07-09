# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Protocol Handler Base - Remote Knowledge Sources
# Description:  Abstract base class and datatypes for remote source handlers
# Role:         Defines the contract every protocol handler implements
# Usage:        Subclassed by HTTPHandler, S3Handler, RsyncHandler, FileHandler
# Author:       Muxi Framework Team
#
# Two handler styles share this contract:
#
# 1. Enumerating handlers (HTTP, S3, file): expose ``list_files`` +
#    ``download_file`` and let the SyncManager drive per-file change
#    detection against the manifest.
# 2. Incremental handlers (rsync): ``supports_incremental()`` returns True
#    and the SyncManager calls ``sync_tree`` instead, letting the native
#    tool (rsync) do delta transfer; the manifest is rebuilt from the
#    local tree afterwards.
# =============================================================================

import fnmatch
import hashlib
import posixpath
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default per-source limits (PRD section 2). Kept conservative and
# overridable per source via max_files / max_file_size / max_total_size.
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_MAX_TOTAL_SIZE = 100 * 1024 * 1024  # 100MB
DEFAULT_SYNC_TIMEOUT = 300  # seconds


class RemoteSyncError(Exception):
    """Raised when a remote knowledge source operation fails."""

    pass


@dataclass
class RemoteFile:
    """A file discovered at a remote source.

    Attributes:
        path: Path relative to the source root. Must be a safe relative
            path (validated by the SyncManager before use).
        url: Full URL used to download this specific file.
        size: Size in bytes when the protocol exposes it, else None.
        remote_hash: Protocol-native change token (ETag, MD5,
            size+mtime composite, ...) when available, else None.
    """

    path: str
    url: str
    size: Optional[int] = None
    remote_hash: Optional[str] = None


@dataclass
class DownloadResult:
    """Result of downloading a single remote file."""

    path: str
    local_path: Path
    size: int
    local_hash: str


@dataclass
class SourceConfig:
    """Normalized remote source configuration (secrets already interpolated).

    Built from the raw source dict by ``SourceConfig.from_dict``; protocol
    handlers read auth/headers/limits from here instead of re-parsing the
    raw config.
    """

    url: str
    source_id: str
    description: str = ""
    auth: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    max_files: int = DEFAULT_MAX_FILES
    max_file_size: int = DEFAULT_MAX_FILE_SIZE
    max_total_size: int = DEFAULT_MAX_TOTAL_SIZE
    timeout: int = DEFAULT_SYNC_TIMEOUT

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "SourceConfig":
        """Create a SourceConfig from a raw knowledge source dict."""
        url = config["url"]
        return cls(
            url=url,
            source_id=config.get("id") or derive_source_id(url),
            description=config.get("description", ""),
            auth=config.get("auth") or {},
            headers=config.get("headers") or {},
            include=list(config.get("include") or []),
            exclude=list(config.get("exclude") or []),
            max_files=int(config.get("max_files", DEFAULT_MAX_FILES)),
            max_file_size=int(config.get("max_file_size", DEFAULT_MAX_FILE_SIZE)),
            max_total_size=int(config.get("max_total_size", DEFAULT_MAX_TOTAL_SIZE)),
            timeout=int(config.get("timeout", DEFAULT_SYNC_TIMEOUT)),
        )


def derive_source_id(url: str) -> str:
    """Derive a stable, filesystem-safe source id from a URL.

    Used when the operator does not declare an explicit ``id``. Combines
    a readable slug with a short hash so two similar URLs never collide.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in url.split("://", 1)[-1])
    slug = slug.strip("-")[:48].rstrip("-") or "source"
    return f"{slug}-{digest}"


class ProtocolHandler(ABC):
    """Base class for remote knowledge source protocol handlers.

    Handlers are constructed with the normalized :class:`SourceConfig`
    (auth, headers, limits) and operate on URLs passed per call, matching
    the PRD interface. All network/disk work is async; blocking SDKs
    (boto3) must be dispatched to a thread.
    """

    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        """List files matching ``pattern`` at the remote ``url``.

        ``url`` is the source base (glob already split off); ``pattern``
        is an fnmatch-style pattern or None for a single file / whole tree.
        """

    @abstractmethod
    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        """Download a single file to ``dest`` enforcing ``max_file_size``."""

    async def get_file_hash(self, url: str) -> str:
        """Get a remote change token for ``url`` ('' when unavailable).

        Default implementation returns '' — enumerating handlers usually
        surface hashes via :meth:`list_files` instead.
        """
        return ""

    def supports_incremental(self) -> bool:
        """Whether the handler syncs whole trees natively (rsync)."""
        return False

    async def sync_tree(self, url: str, dest_dir: Path) -> None:
        """Incrementally sync the remote tree at ``url`` into ``dest_dir``.

        Only implemented by handlers where ``supports_incremental()`` is
        True; enumerating handlers never receive this call.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support incremental sync")

    async def close(self) -> None:
        """Release any connections/clients held by the handler."""
        return None


def hash_file_sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of a local file."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def matches_pattern(rel_path: str, pattern: str) -> bool:
    """fnmatch ``rel_path`` against ``pattern`` (basename fallback).

    ``*.md`` should match files at any depth (matching rsync/S3 operator
    expectations), so patterns without a slash also test the basename.
    """
    if fnmatch.fnmatch(rel_path, pattern):
        return True
    return "/" not in pattern and fnmatch.fnmatch(posixpath.basename(rel_path), pattern)


def split_url_pattern(url: str) -> tuple:
    """Split a source URL into (base_url, pattern).

    The pattern starts at the first path segment containing a glob
    character (``*``, ``?``, ``[``). Examples:

    - ``s3://bucket/docs/*.md``      -> (``s3://bucket/docs/``, ``*.md``)
    - ``s3://bucket/docs/**/*.pdf``  -> (``s3://bucket/docs/``, ``**/*.pdf``)
    - ``https://host/notes.md``      -> (``https://host/notes.md``, None)
    """
    glob_chars = ("*", "?", "[")
    first_glob = min((url.find(c) for c in glob_chars if c in url), default=-1)
    if first_glob == -1:
        return url, None
    split_at = url.rfind("/", 0, first_glob) + 1
    return url[:split_at], url[split_at:] or None
