# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        SFTP Handler - Remote Knowledge Sources
# Description:  Syncs knowledge files from SFTP servers
# Role:         Protocol handler for sftp:// sources (PRD Phase 4)
# Usage:        Created by the protocol registry for sftp:// source URLs
# Author:       Muxi Framework Team
#
# Uses paramiko (optional dependency, `muxi-runtime[sftp]` extra)
# dispatched to worker threads. Change detection is a size + mtime
# composite. Symlinks in the remote tree are skipped (same policy as the
# file:// handler and the archive extractor).
#
# Host key policy mirrors rsync+ssh: STRICT by default - the host must
# already be in known_hosts or the sync fails, so a MITM on first contact
# cannot inject knowledge content. ``accept_new_host_keys: true`` on the
# source is the explicit opt-in for trust-on-first-use.
#
# Auth: ``auth: {type: ssh_key, key: <private key material>}`` or
# ``auth: {type: basic, username, password}`` (already
# secret-interpolated). The username may also come from the URL.
# =============================================================================

import asyncio
import io
import os
import posixpath
import stat as stat_module
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from ..handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    SourceConfig,
    atomic_download,
    hash_file_sha256,
    matches_pattern,
)

try:  # pragma: no cover - import guard mirrors the boto3 optional-dep pattern
    import paramiko

    PARAMIKO_AVAILABLE = True
except ImportError:  # pragma: no cover
    paramiko = None
    PARAMIKO_AVAILABLE = False

# Hard cap on entries visited during a recursive listing (hostile server guard)
MAX_LIST_ENTRIES = 10000


class SFTPHandler(ProtocolHandler):
    """Protocol handler for sftp:// knowledge sources."""

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        if not PARAMIKO_AVAILABLE:
            raise RemoteSyncError(
                "sftp:// knowledge sources require the paramiko library. "
                "Install it with: pip install 'muxi-runtime[sftp]' "
                "(or pip install paramiko)"
            )

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        return await asyncio.to_thread(self._list_files_sync, url, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        return await asyncio.to_thread(self._download_sync, url, dest)

    async def get_file_hash(self, url: str) -> str:
        return await asyncio.to_thread(self._head_hash_sync, url)

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _connect(self, parsed) -> Tuple[Any, Any]:
        """Open (ssh_client, sftp_client) for a parsed sftp:// URL."""
        host = parsed.hostname or ""
        if not host:
            raise RemoteSyncError("sftp:// knowledge source URL is missing a host")

        auth = self.config.auth or {}
        auth_type = (auth.get("type") or "").lower()
        username = auth.get("username") or (unquote(parsed.username) if parsed.username else None)
        password = auth.get("password") if auth_type == "basic" else None
        pkey = None
        if auth_type == "ssh_key" and auth.get("key"):
            pkey = self._load_private_key(auth["key"])

        client = paramiko.SSHClient()
        # Known-hosts policy: strict by default (host must already be
        # known), trust-on-first-use only with the explicit source opt-in.
        client.load_system_host_keys()
        user_known_hosts = os.path.expanduser("~/.ssh/known_hosts")
        if os.path.isfile(user_known_hosts):
            try:
                client.load_host_keys(user_known_hosts)
            except (IOError, OSError):
                pass
        if self.config.accept_new_host_keys:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            client.connect(
                hostname=host,
                port=parsed.port or 22,
                username=username,
                password=password,
                pkey=pkey,
                timeout=self.config.timeout,
                allow_agent=pkey is None and password is None,
                look_for_keys=pkey is None and password is None,
            )
            sftp = client.open_sftp()
        except Exception as e:
            try:
                client.close()
            except Exception:
                pass
            raise RemoteSyncError(f"Failed to connect to sftp://{host}: {e}") from e
        return client, sftp

    @staticmethod
    def _load_private_key(key_material: str) -> Any:
        """Parse private key material (Ed25519 / ECDSA / RSA)."""
        last_error: Optional[Exception] = None
        for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
            try:
                return key_class.from_private_key(io.StringIO(key_material))
            except Exception as e:  # try the next key type
                last_error = e
        raise RemoteSyncError(
            f"Could not parse sftp ssh_key material as Ed25519/ECDSA/RSA: {last_error}"
        )

    def _list_files_sync(self, url: str, pattern: Optional[str]) -> List[RemoteFile]:
        parsed = urlparse(url)
        base_path = unquote(parsed.path) or "/"
        client, sftp = self._connect(parsed)
        try:
            base_stat = sftp.stat(base_path.rstrip("/") or "/")
            results: List[RemoteFile] = []
            if stat_module.S_ISREG(base_stat.st_mode):
                rel_path = posixpath.basename(base_path.rstrip("/"))
                if not pattern or matches_pattern(rel_path, pattern):
                    results.append(
                        RemoteFile(
                            path=rel_path,
                            url=self._file_url(parsed, base_path),
                            size=base_stat.st_size,
                            remote_hash=_stat_token(base_stat),
                        )
                    )
                return results

            entries: List[Tuple[str, Any]] = []
            base_dir = base_path.rstrip("/") or "/"
            self._walk(sftp, base_dir, "", entries)
            for rel_path, attrs in entries:
                if pattern and not matches_pattern(rel_path, pattern):
                    continue
                results.append(
                    RemoteFile(
                        path=rel_path,
                        url=self._file_url(parsed, posixpath.join(base_dir, rel_path)),
                        size=attrs.st_size,
                        remote_hash=_stat_token(attrs),
                    )
                )
            return results
        except RemoteSyncError:
            raise
        except Exception as e:
            raise RemoteSyncError(f"Failed to list sftp source {url}: {e}") from e
        finally:
            self._close(client, sftp)

    def _walk(self, sftp: Any, directory: str, rel_prefix: str, entries: List) -> None:
        """Recursively collect (rel_path, attrs) for regular files."""
        if len(entries) > MAX_LIST_ENTRIES:
            raise RemoteSyncError(
                f"sftp listing exceeded {MAX_LIST_ENTRIES} entries; refusing to continue"
            )
        for attrs in sftp.listdir_attr(directory):
            name = attrs.filename
            if name in (".", ".."):
                continue
            rel_path = posixpath.join(rel_prefix, name) if rel_prefix else name
            if stat_module.S_ISDIR(attrs.st_mode):
                self._walk(sftp, posixpath.join(directory, name), rel_path, entries)
            elif stat_module.S_ISREG(attrs.st_mode):
                entries.append((rel_path, attrs))
            # symlinks and special files are skipped (never followed)

    def _download_sync(self, url: str, dest: Path) -> DownloadResult:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        client, sftp = self._connect(parsed)
        try:
            try:
                remote_stat = sftp.stat(path)
            except Exception as e:
                raise RemoteSyncError(f"Failed to stat sftp file {url}: {e}") from e
            size = remote_stat.st_size or 0
            if size > self.config.max_file_size:
                raise RemoteSyncError(
                    f"Remote file exceeds max_file_size "
                    f"({size} > {self.config.max_file_size}): {url}"
                )
            # Download into a temp file and atomically swap it in on
            # success (see atomic_download in handler.py).
            with atomic_download(dest) as tmp_path:
                try:
                    sftp.get(path, str(tmp_path))
                except Exception as e:
                    raise RemoteSyncError(f"Failed to download {url}: {e}") from e
        finally:
            self._close(client, sftp)
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=size,
            local_hash=hash_file_sha256(dest),
        )

    def _head_hash_sync(self, url: str) -> str:
        parsed = urlparse(url)
        client, sftp = self._connect(parsed)
        try:
            attrs = sftp.stat(unquote(parsed.path))
        except Exception:
            return ""
        finally:
            self._close(client, sftp)
        return _stat_token(attrs) or ""

    @staticmethod
    def _file_url(parsed, file_path: str) -> str:
        """Rebuild a per-file sftp:// URL (credentials stay in config)."""
        host = parsed.hostname or ""
        user = f"{parsed.username}@" if parsed.username else ""
        port = f":{parsed.port}" if parsed.port else ""
        return f"sftp://{user}{host}{port}{file_path}"

    @staticmethod
    def _close(client: Any, sftp: Any) -> None:
        for closable in (sftp, client):
            try:
                closable.close()
            except Exception:
                pass


def _stat_token(attrs: Any) -> Optional[str]:
    size = getattr(attrs, "st_size", None)
    mtime = getattr(attrs, "st_mtime", None)
    if size is None or mtime is None:
        return None
    return f"stat:{size}:{int(mtime)}"
