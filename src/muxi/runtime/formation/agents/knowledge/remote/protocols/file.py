# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        File Handler - Remote Knowledge Sources
# Description:  Syncs knowledge from mounted volumes via file:// URLs
# Role:         Protocol handler for file:// sources (bind mounts)
# Usage:        Created by the protocol registry for file:// source URLs
# Author:       Muxi Framework Team
#
# Intended for container bind mounts: content that lives OUTSIDE the
# formation directory (which local ``path`` sources cannot reach by
# design) but is mounted into the runtime filesystem. Files are copied
# into the managed knowledge mirror so the ingestion pipeline sees a
# stable, sandboxed tree. Change detection uses a size+mtime composite
# (cheap, no full-content hashing of the source tree on every sync).
# =============================================================================

import asyncio
import os
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

from ..handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    hash_file_sha256,
    matches_pattern,
)


class FileHandler(ProtocolHandler):
    """Protocol handler for file:// knowledge sources (mounted volumes)."""

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        root = self._local_path(url)
        return await asyncio.to_thread(self._list_files_sync, root, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        src = self._local_path(url)
        return await asyncio.to_thread(self._copy_sync, src, dest)

    async def get_file_hash(self, url: str) -> str:
        src = self._local_path(url)
        try:
            stat = os.stat(src)
        except OSError:
            return ""
        return _stat_token(stat)

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _list_files_sync(self, root: str, pattern: Optional[str]) -> List[RemoteFile]:
        if os.path.isfile(root):
            stat = os.stat(root)
            return [
                RemoteFile(
                    path=os.path.basename(root),
                    url=Path(root).as_uri(),
                    size=stat.st_size,
                    remote_hash=_stat_token(stat),
                )
            ]

        if not os.path.isdir(root):
            raise RemoteSyncError(f"file:// knowledge source path does not exist: {root}")

        results: List[RemoteFile] = []
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            for filename in sorted(filenames):
                full_path = os.path.join(dirpath, filename)
                if os.path.islink(full_path) or not os.path.isfile(full_path):
                    continue
                rel_path = os.path.relpath(full_path, root).replace(os.sep, "/")
                if pattern and not matches_pattern(rel_path, pattern):
                    continue
                stat = os.stat(full_path)
                results.append(
                    RemoteFile(
                        path=rel_path,
                        url=Path(full_path).as_uri(),
                        size=stat.st_size,
                        remote_hash=_stat_token(stat),
                    )
                )
        return results

    def _copy_sync(self, src: str, dest: Path) -> DownloadResult:
        try:
            size = os.path.getsize(src)
        except OSError as e:
            raise RemoteSyncError(f"file:// knowledge source file unreadable: {src}") from e
        if size > self.config.max_file_size:
            raise RemoteSyncError(
                f"Remote file exceeds max_file_size ({size} > {self.config.max_file_size}): {src}"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=size,
            local_hash=hash_file_sha256(dest),
        )

    @staticmethod
    def _local_path(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc not in ("", "localhost"):
            raise RemoteSyncError(f"file:// knowledge sources must be local (file:///path): {url}")
        path = unquote(parsed.path)
        if not path or not os.path.isabs(path):
            raise RemoteSyncError(f"file:// knowledge sources require an absolute path: {url}")
        return path


def _stat_token(stat: os.stat_result) -> str:
    return f"stat:{stat.st_size}:{stat.st_mtime_ns}"
