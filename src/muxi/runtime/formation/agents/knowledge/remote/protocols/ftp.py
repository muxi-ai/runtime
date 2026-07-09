# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        FTP Handler - Remote Knowledge Sources
# Description:  Syncs knowledge files from FTP servers
# Role:         Protocol handler for ftp:// sources (PRD Phase 4)
# Usage:        Created by the protocol registry for ftp:// source URLs
# Author:       Muxi Framework Team
#
# Uses the stdlib ftplib (no extra dependency) dispatched to worker
# threads. Change detection is a size + mtime composite (MLSD facts, with
# SIZE/MDTM fallback for servers without MLSD) - FTP exposes no content
# hashes, so a missing token simply re-downloads (correctness over
# bandwidth, same policy as the other handlers).
#
# Auth: ``auth: {type: basic, username, password}`` (already
# secret-interpolated), URL userinfo (ftp://user:pass@host/), or
# anonymous when neither is present.
# =============================================================================

import asyncio
import ftplib
import posixpath
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ..handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    atomic_download,
    hash_file_sha256,
    matches_pattern,
)

# Hard cap on directory entries visited during a recursive listing so a
# pathological/hostile server cannot spin the walk forever.
MAX_LIST_ENTRIES = 10000


class FTPHandler(ProtocolHandler):
    """Protocol handler for ftp:// knowledge sources."""

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        return await asyncio.to_thread(self._list_files_sync, url, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        return await asyncio.to_thread(self._download_sync, url, dest)

    async def get_file_hash(self, url: str) -> str:
        return await asyncio.to_thread(self._head_hash_sync, url)

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _connect(self, parsed) -> ftplib.FTP:
        host = parsed.hostname or ""
        if not host:
            raise RemoteSyncError("ftp:// knowledge source URL is missing a host")
        auth = self.config.auth or {}
        username = auth.get("username") or (
            unquote(parsed.username) if parsed.username else "anonymous"
        )
        password = auth.get("password") or (
            unquote(parsed.password) if parsed.password else "anonymous@"
        )
        try:
            ftp = ftplib.FTP(timeout=self.config.timeout)
            ftp.connect(host, parsed.port or 21)
            ftp.login(username, password)
        except (ftplib.all_errors, OSError) as e:
            raise RemoteSyncError(f"Failed to connect to ftp://{host}: {e}") from e
        return ftp

    def _list_files_sync(self, url: str, pattern: Optional[str]) -> List[RemoteFile]:
        parsed = urlparse(url)
        base_path = unquote(parsed.path) or "/"
        ftp = self._connect(parsed)
        try:
            results: List[RemoteFile] = []
            if self._is_file(ftp, base_path):
                size, token = self._probe_file(ftp, base_path)
                rel_path = posixpath.basename(base_path.rstrip("/"))
                if not pattern or matches_pattern(rel_path, pattern):
                    results.append(
                        RemoteFile(
                            path=rel_path,
                            url=self._file_url(parsed, base_path),
                            size=size if size >= 0 else None,
                            remote_hash=token,
                        )
                    )
                return results

            entries: List[Tuple[str, int, Optional[str]]] = []
            base_dir = base_path.rstrip("/") or "/"
            self._walk(ftp, base_dir, "", entries)
            for rel_path, size, token in entries:
                if pattern and not matches_pattern(rel_path, pattern):
                    continue
                results.append(
                    RemoteFile(
                        path=rel_path,
                        url=self._file_url(parsed, posixpath.join(base_dir, rel_path)),
                        size=size if size >= 0 else None,
                        remote_hash=token,
                    )
                )
            return results
        except ftplib.all_errors as e:
            raise RemoteSyncError(f"Failed to list ftp source {url}: {e}") from e
        finally:
            self._quit(ftp)

    def _walk(
        self,
        ftp: ftplib.FTP,
        directory: str,
        rel_prefix: str,
        entries: List[Tuple[str, int, Optional[str]]],
    ) -> None:
        """Recursively collect (rel_path, size, token) under ``directory``."""
        if len(entries) > MAX_LIST_ENTRIES:
            raise RemoteSyncError(
                f"ftp listing exceeded {MAX_LIST_ENTRIES} entries; refusing to continue"
            )
        try:
            listing = list(ftp.mlsd(directory, facts=["type", "size", "modify"]))
        except (ftplib.error_perm, AttributeError):
            listing = None

        if listing is not None:
            for name, facts in listing:
                if name in (".", ".."):
                    continue
                entry_type = (facts.get("type") or "").lower()
                rel_path = posixpath.join(rel_prefix, name) if rel_prefix else name
                if entry_type == "dir":
                    self._walk(ftp, posixpath.join(directory, name), rel_path, entries)
                elif entry_type == "file":
                    size = int(facts.get("size", -1) or -1)
                    modify = facts.get("modify", "")
                    token = f"stat:{size}:{modify}" if size >= 0 and modify else None
                    entries.append((rel_path, size, token))
                # links and special entries are ignored
            return

        # MLSD unsupported: NLST + probe each entry (file via SIZE, dir
        # via a recursive walk attempt).
        try:
            names = ftp.nlst(directory)
        except ftplib.error_perm as e:
            # Empty directory on some servers responds 550
            if str(e).startswith("550"):
                return
            raise
        for full_name in names:
            name = posixpath.basename(full_name.rstrip("/"))
            if not name or name in (".", ".."):
                continue
            full_path = posixpath.join(directory, name)
            rel_path = posixpath.join(rel_prefix, name) if rel_prefix else name
            if self._is_file(ftp, full_path):
                size, token = self._probe_file(ftp, full_path)
                entries.append((rel_path, size, token))
            else:
                self._walk(ftp, full_path, rel_path, entries)

    @staticmethod
    def _is_file(ftp: ftplib.FTP, path: str) -> bool:
        """Whether ``path`` is a regular file (SIZE succeeds on files only)."""
        try:
            ftp.voidcmd("TYPE I")
            return ftp.size(path) is not None
        except ftplib.all_errors:
            return False

    @staticmethod
    def _probe_file(ftp: ftplib.FTP, path: str) -> Tuple[int, Optional[str]]:
        """(size, change token) for a single file via SIZE + MDTM."""
        size = -1
        modify = ""
        try:
            ftp.voidcmd("TYPE I")
            size = ftp.size(path) or -1
        except ftplib.all_errors:
            pass
        try:
            response = ftp.voidcmd(f"MDTM {path}")
            modify = response.split(maxsplit=1)[1] if " " in response else ""
        except ftplib.all_errors:
            pass
        token = f"stat:{size}:{modify}" if size >= 0 and modify else None
        return size, token

    def _download_sync(self, url: str, dest: Path) -> DownloadResult:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        max_size = self.config.max_file_size
        ftp = self._connect(parsed)
        try:
            # Stream into a temp file and atomically swap it in on
            # success (see atomic_download in handler.py).
            with atomic_download(dest) as tmp_path:
                written = 0
                with open(tmp_path, "wb") as f:

                    def _write(chunk: bytes) -> None:
                        nonlocal written
                        written += len(chunk)
                        if written > max_size:
                            raise RemoteSyncError(
                                f"Remote file exceeds max_file_size "
                                f"({written} > {max_size}): {url}"
                            )
                        f.write(chunk)

                    try:
                        ftp.retrbinary(f"RETR {path}", _write)
                    except RemoteSyncError:
                        raise
                    except ftplib.all_errors as e:
                        raise RemoteSyncError(f"Failed to download {url}: {e}") from e
        finally:
            self._quit(ftp)
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=written,
            local_hash=hash_file_sha256(dest),
        )

    def _head_hash_sync(self, url: str) -> str:
        parsed = urlparse(url)
        ftp = self._connect(parsed)
        try:
            _, token = self._probe_file(ftp, unquote(parsed.path))
            return token or ""
        finally:
            self._quit(ftp)

    @staticmethod
    def _file_url(parsed, file_path: str) -> str:
        """Rebuild a per-file ftp:// URL (credentials stay in config)."""
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        return f"ftp://{host}{port}{file_path}"

    @staticmethod
    def _quit(ftp: ftplib.FTP) -> None:
        try:
            ftp.quit()
        except ftplib.all_errors:
            try:
                ftp.close()
            except OSError:
                pass
