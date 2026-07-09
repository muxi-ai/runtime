# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Rsync Handler - Remote Knowledge Sources
# Description:  Incrementally syncs knowledge trees via the rsync binary
# Role:         Protocol handler for rsync:// and rsync+ssh:// sources
# Usage:        Created by the protocol registry for rsync source URLs
# Author:       Muxi Framework Team
#
# This is the one incremental handler in Phase 1: rsync transfers deltas
# natively, so the SyncManager calls ``sync_tree`` (whole-tree sync into
# the content directory) instead of the list/download loop, then rebuilds
# the manifest from the resulting local tree.
#
# Auth: ``auth: {type: ssh_key, key: <private key material>}`` for
# rsync+ssh:// sources. The key (already secret-interpolated) is written
# to a 0600 temp file for the duration of the sync and removed afterwards.
# =============================================================================

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

from ..handler import DownloadResult, ProtocolHandler, RemoteFile, RemoteSyncError


class RsyncHandler(ProtocolHandler):
    """Protocol handler for rsync:// and rsync+ssh:// knowledge sources."""

    def supports_incremental(self) -> bool:
        return True

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        raise NotImplementedError("RsyncHandler syncs whole trees incrementally; use sync_tree()")

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        raise NotImplementedError("RsyncHandler syncs whole trees incrementally; use sync_tree()")

    async def sync_tree(self, url: str, dest_dir: Path) -> None:
        rsync_bin = shutil.which("rsync")
        if rsync_bin is None:
            raise RemoteSyncError("rsync:// knowledge sources require the rsync binary on PATH")

        dest_dir.mkdir(parents=True, exist_ok=True)
        key_file: Optional[str] = None
        try:
            command, key_file = self._build_command(rsync_bin, url, dest_dir)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.config.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise RemoteSyncError(f"rsync timed out after {self.config.timeout}s syncing {url}")
            if process.returncode != 0:
                detail = (stderr or b"").decode("utf-8", errors="replace").strip()
                raise RemoteSyncError(
                    f"rsync exited with code {process.returncode} syncing {url}: {detail}"
                )
        finally:
            if key_file:
                try:
                    os.remove(key_file)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_command(self, rsync_bin: str, url: str, dest_dir: Path) -> tuple:
        """Build the rsync argv for ``url`` -> ``dest_dir`` (returns key file).

        - ``--delete`` mirrors remote deletions locally (remote wins).
        - ``--safe-links`` refuses symlinks that point outside the tree.
        - ``--max-size`` enforces the per-file size limit natively.
        - include/exclude config maps to rsync filter rules.
        """
        command = [
            rsync_bin,
            "-rtz",
            "--delete",
            "--safe-links",
            f"--timeout={self.config.timeout}",
            f"--max-size={self.config.max_file_size}",
        ]
        for pattern in self.config.include:
            command.append(f"--include={pattern}")
        if self.config.include:
            # rsync include semantics: keep directories traversable, then
            # drop everything not explicitly included.
            command.append("--include=*/")
            command.append("--exclude=*")
        for pattern in self.config.exclude:
            command.append(f"--exclude={pattern}")

        key_file: Optional[str] = None
        parsed = urlparse(url)
        if parsed.scheme == "rsync+ssh":
            source, ssh_command, key_file = self._ssh_source(parsed)
            command.extend(["-e", ssh_command])
        else:
            # Native rsync daemon URL: pass through as-is (rsync://host/module/path)
            source = url if url.endswith("/") else url + "/"

        command.append(source)
        command.append(str(dest_dir) + os.sep)
        return command, key_file

    def _ssh_source(self, parsed) -> tuple:
        """Convert rsync+ssh://user@host[:port]/path into rsync-over-ssh args."""
        host = parsed.hostname or ""
        if not host:
            raise RemoteSyncError("rsync+ssh:// knowledge source URL is missing a host")
        user_prefix = f"{parsed.username}@" if parsed.username else ""
        path = unquote(parsed.path) or "/"
        source = f"{user_prefix}{host}:{path if path.endswith('/') else path + '/'}"

        # Host key policy: strict by default (the host must already be in
        # known_hosts, or the sync fails) so a MITM on first contact
        # cannot inject knowledge content. Operators can opt into SSH's
        # trust-on-first-use with `accept_new_host_keys: true` on the
        # source (accept-new still rejects CHANGED keys).
        host_key_policy = "accept-new" if self.config.accept_new_host_keys else "yes"
        ssh_parts = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"StrictHostKeyChecking={host_key_policy}",
        ]
        if parsed.port:
            ssh_parts.extend(["-p", str(parsed.port)])

        key_file: Optional[str] = None
        auth = self.config.auth or {}
        if (auth.get("type") or "").lower() == "ssh_key" and auth.get("key"):
            # mkstemp already creates the file 0600; the explicit chmod is
            # belt-and-braces. Any failure after creation (write, chmod)
            # must remove the written key material immediately - the
            # caller's finally only covers paths it has received.
            fd, key_file = tempfile.mkstemp(prefix="muxi-rsync-key-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(auth["key"])
                    if not auth["key"].endswith("\n"):
                        f.write("\n")
                os.chmod(key_file, 0o600)
            except BaseException:
                try:
                    os.remove(key_file)
                except OSError:
                    pass
                raise
            ssh_parts.extend(["-i", key_file])

        return source, " ".join(ssh_parts), key_file
