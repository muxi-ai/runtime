# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Sync Manifest - Remote Knowledge Sources
# Description:  Tracks per-source sync state (files, hashes, last sync)
# Role:         Enables incremental change detection and degrade-to-synced
# Usage:        Loaded/saved by SyncManager around every sync run
# Author:       Muxi Framework Team
#
# The manifest is the source of truth for "what has already been synced".
# When a remote source becomes unreachable, the formation degrades to the
# state recorded here (stale-wins policy, PRD open question #2). The file
# lives NEXT TO the content directory (never inside it) so it is never
# ingested as knowledge content.
#
# Manifest files are treated as untrusted input: entries with unsafe
# relative paths (absolute, drive-letter, or ``..`` traversal) are dropped
# on load, and corrupt manifests reset to an empty state instead of
# breaking formation startup.
# =============================================================================

import os
import posixpath
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .....utils.fastjson import json

MANIFEST_FILENAME = "manifest.json"


def safe_relative_path(rel_path: str) -> bool:
    """Return True when ``rel_path`` is a safe path relative to a root.

    Rejects absolute paths (POSIX and Windows), drive letters, empty
    paths, NUL bytes, backslashes, and any ``..`` traversal component.
    Used to guard both manifest entries loaded from disk and remote file
    paths reported by protocol handlers, so synced content can never
    land outside the knowledge directory.
    """
    if not rel_path or not isinstance(rel_path, str):
        return False
    if "\x00" in rel_path or "\\" in rel_path:
        return False
    if rel_path.startswith("/") or rel_path.startswith("~"):
        return False
    # Windows drive letters (C:...) and UNC-ish prefixes
    if ":" in rel_path.split("/", 1)[0]:
        return False
    normalized = posixpath.normpath(rel_path)
    if normalized.startswith("..") or "/../" in f"/{normalized}/":
        return False
    return True


def resolve_within(root: str, rel_path: str) -> Optional[str]:
    """Resolve ``rel_path`` under ``root``, returning None if it escapes.

    Defense-in-depth on top of :func:`safe_relative_path` — the resolved
    absolute path must stay inside ``root`` (symlink-resolved).
    """
    if not safe_relative_path(rel_path):
        return None
    root_abs = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_abs, rel_path))
    if candidate != root_abs and not candidate.startswith(root_abs + os.sep):
        return None
    return candidate


@dataclass
class FileRecord:
    """Sync state for a single file within a source."""

    remote_hash: str = ""
    local_hash: str = ""
    size: int = 0
    synced_at: str = ""


@dataclass
class Manifest:
    """Per-source sync state (PRD section 3.2)."""

    source_id: str
    url: str
    last_sync: str = ""
    last_sync_duration_ms: int = 0
    last_sync_status: str = "never"  # never | success | partial | failed
    last_sync_error: str = ""
    # Archive sources (Phase 2): change token + size of the last archive
    # successfully downloaded AND extracted. An unchanged archive skips
    # both the download and the re-extraction.
    archive_hash: str = ""
    archive_size: int = 0
    files: Dict[str, FileRecord] = field(default_factory=dict)

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "total_files": len(self.files),
            "total_size": sum(record.size for record in self.files.values()),
        }

    def record_file(self, rel_path: str, remote_hash: str, local_hash: str, size: int) -> None:
        self.files[rel_path] = FileRecord(
            remote_hash=remote_hash or "",
            local_hash=local_hash or "",
            size=size,
            synced_at=_utc_now(),
        )

    def is_unchanged(self, rel_path: str, remote_hash: Optional[str], size: Optional[int]) -> bool:
        """Whether the remote file matches what was last synced.

        Requires a non-empty remote hash match; when the protocol exposes
        a size it must match too. Without a remote hash we cannot prove
        the file is unchanged, so it re-downloads (correctness over
        bandwidth, per PRD success metric #3).
        """
        record = self.files.get(rel_path)
        if record is None or not remote_hash or record.remote_hash != remote_hash:
            return False
        if size is not None and record.size != size:
            return False
        return True

    def mark_sync(self, status: str, duration_ms: int, error: str = "") -> None:
        self.last_sync = _utc_now()
        self.last_sync_duration_ms = duration_ms
        self.last_sync_status = status
        self.last_sync_error = error

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str, source_id: str, url: str) -> "Manifest":
        """Load a manifest from ``path``; tolerant of corruption.

        A missing, corrupt, or mismatched manifest resets to an empty
        state (the sync will simply re-verify/re-download files) instead
        of failing formation startup. Unsafe file paths are dropped.
        """
        manifest = cls(source_id=source_id, url=url)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, OSError, ValueError):
            return manifest

        if not isinstance(data, dict):
            return manifest

        manifest.last_sync = str(data.get("last_sync", ""))
        manifest.last_sync_duration_ms = int(data.get("last_sync_duration_ms", 0) or 0)
        manifest.last_sync_status = str(data.get("last_sync_status", "never"))
        manifest.last_sync_error = str(data.get("last_sync_error", ""))
        manifest.archive_hash = str(data.get("archive_hash", ""))
        manifest.archive_size = int(data.get("archive_size", 0) or 0)

        raw_files = data.get("files", {})
        if isinstance(raw_files, dict):
            for rel_path, record in raw_files.items():
                if not safe_relative_path(str(rel_path)) or not isinstance(record, dict):
                    continue
                manifest.files[str(rel_path)] = FileRecord(
                    remote_hash=str(record.get("remote_hash", "")),
                    local_hash=str(record.get("local_hash", "")),
                    size=int(record.get("size", 0) or 0),
                    synced_at=str(record.get("synced_at", "")),
                )
        return manifest

    def save(self, path: str) -> None:
        """Atomically persist the manifest to ``path``."""
        data: Dict[str, Any] = {
            "source_id": self.source_id,
            "url": self.url,
            "last_sync": self.last_sync,
            "last_sync_duration_ms": self.last_sync_duration_ms,
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "archive_hash": self.archive_hash,
            "archive_size": self.archive_size,
            "files": {rel: asdict(record) for rel, record in self.files.items()},
            "stats": self.stats,
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(data))
            os.replace(tmp_path, path)
        except OSError:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
