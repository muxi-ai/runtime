# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        HTTP Handler - Remote Knowledge Sources
# Description:  Downloads knowledge files from HTTP(S) URLs via aiohttp
# Role:         Protocol handler for http:// and https:// sources
# Usage:        Created by the protocol registry for http(s) source URLs
# Author:       Muxi Framework Team
#
# Phase 1 scope: single-file URLs only. HTTP has no standard directory
# listing, so glob patterns over http(s) are rejected at validation time.
# Change detection uses ETag / Last-Modified from a HEAD probe; servers
# that expose neither simply re-download on every sync.
#
# Auth: ``headers`` map (already secret-interpolated) plus optional
# ``auth: {type: basic|bearer, ...}`` block.
# =============================================================================

import mimetypes
import posixpath
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

import aiohttp

from ..handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    hash_file_sha256,
)

# Content types we can map to an ingestible extension when the URL path
# itself has none (extension drives FileKnowledge discovery).
_CONTENT_TYPE_EXTENSIONS = {
    "text/markdown": ".md",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/xml": ".xml",
}


class HTTPHandler(ProtocolHandler):
    """Protocol handler for single-file HTTP(S) knowledge sources."""

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        if pattern:
            raise RemoteSyncError(
                "HTTP(S) knowledge sources do not support glob patterns in Phase 1: "
                f"{url}{pattern}"
            )

        size: Optional[int] = None
        remote_hash: Optional[str] = None
        content_type = ""

        async with self._session() as session:
            try:
                async with session.head(url, allow_redirects=True) as response:
                    if response.status < 400:
                        size = _int_or_none(response.headers.get("Content-Length"))
                        remote_hash = _change_token(response.headers)
                        content_type = response.headers.get("Content-Type", "")
                    elif response.status in (403, 405, 501):
                        # Server rejects HEAD; fall through with unknown
                        # metadata and let the GET in download_file decide.
                        pass
                    else:
                        raise RemoteSyncError(
                            f"HTTP {response.status} probing remote knowledge source: {url}"
                        )
            except aiohttp.ClientError as e:
                raise RemoteSyncError(f"Failed to reach remote knowledge source {url}: {e}") from e

        return [
            RemoteFile(
                path=self._relative_name(url, content_type),
                url=url,
                size=size,
                remote_hash=remote_hash,
            )
        ]

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        max_size = self.config.max_file_size
        dest.parent.mkdir(parents=True, exist_ok=True)

        async with self._session() as session:
            try:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status >= 400:
                        raise RemoteSyncError(
                            f"HTTP {response.status} downloading remote knowledge file: {url}"
                        )
                    declared = _int_or_none(response.headers.get("Content-Length"))
                    if declared is not None and declared > max_size:
                        raise RemoteSyncError(
                            f"Remote file exceeds max_file_size ({declared} > {max_size}): {url}"
                        )
                    written = 0
                    with open(dest, "wb") as f:
                        async for chunk in response.content.iter_chunked(65536):
                            written += len(chunk)
                            if written > max_size:
                                raise RemoteSyncError(
                                    f"Remote file exceeds max_file_size "
                                    f"({written} > {max_size}): {url}"
                                )
                            f.write(chunk)
            except aiohttp.ClientError as e:
                raise RemoteSyncError(f"Failed to download remote knowledge file {url}: {e}") from e

        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=written,
            local_hash=hash_file_sha256(dest),
        )

    async def get_file_hash(self, url: str) -> str:
        files = await self.list_files(url)
        return files[0].remote_hash or "" if files else ""

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _session(self) -> aiohttp.ClientSession:
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        auth = None
        headers: Dict[str, str] = dict(self.config.headers)
        auth_config = self.config.auth
        auth_type = (auth_config.get("type") or "").lower() if auth_config else ""
        if auth_type == "basic":
            auth = aiohttp.BasicAuth(
                auth_config.get("username", ""), auth_config.get("password", "")
            )
        elif auth_type == "bearer":
            headers.setdefault("Authorization", f"Bearer {auth_config.get('token', '')}")
        return aiohttp.ClientSession(timeout=timeout, headers=headers, auth=auth)

    def _relative_name(self, url: str, content_type: str) -> str:
        """Derive the local filename for a single-file HTTP source.

        FileKnowledge discovers files by extension, so a URL without one
        gets an extension inferred from the Content-Type (default .txt).
        """
        parsed = urlparse(url)
        name = posixpath.basename(unquote(parsed.path)) or "document"
        # Sanitize: the name becomes a path component inside the content dir
        name = name.replace("/", "_").replace("\\", "_").replace("\x00", "")
        if name in (".", ".."):
            name = "document"
        if not posixpath.splitext(name)[1]:
            base_type = content_type.split(";", 1)[0].strip().lower()
            name += (
                _CONTENT_TYPE_EXTENSIONS.get(base_type)
                or mimetypes.guess_extension(base_type)
                or ".txt"
            )
        return name


def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _change_token(headers) -> Optional[str]:
    """Build a change-detection token from ETag / Last-Modified headers."""
    etag = headers.get("ETag", "").strip('"')
    last_modified = headers.get("Last-Modified", "")
    if etag:
        return f"etag:{etag}"
    if last_modified:
        return f"modified:{last_modified}"
    return None
