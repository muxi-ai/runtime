# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Archive Extractor - Remote Knowledge Sources
# Description:  Safely extracts knowledge archives (zip/tar) into a directory
# Role:         Phase 2 of the remote knowledge PRD (archive extraction)
# Usage:        SyncManager extracts downloaded archives when `extract: true`
# Author:       Muxi Framework Team
#
# Security posture (all enforced per member, streaming):
# - Path traversal: member names are untrusted. safe_relative_path +
#   resolve_within (the same guards the manifest uses) reject absolute
#   paths, drive letters, backslashes, and any `..` component, and
#   re-verify the resolved target stays inside the extraction root.
# - Symlinks/hardlinks/devices: rejected (skipped and reported). A symlink
#   member could otherwise alias content outside the extraction root.
# - Decompression bombs: cumulative extracted bytes and file count are
#   bounded (`max_extracted_size`, `max_extracted_files`). Bytes are
#   counted as they are decompressed - header-declared sizes are treated
#   as hints, never trusted. Exceeding a bound aborts the whole
#   extraction (RemoteSyncError), so a malicious archive can never
#   partially ingest.
# =============================================================================

import os
import posixpath
import shutil
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, List, Optional

from .handler import RemoteSyncError, matches_pattern
from .manifest import resolve_within

# Decompression-bomb bounds. Conservative but roomy: the per-source
# ingestion limits (max_files / max_total_size) still apply downstream,
# so these only need to stop pathological archives before they fill the
# disk. Overridable per source via max_extracted_files / max_extracted_size.
DEFAULT_MAX_EXTRACTED_FILES = 1000
DEFAULT_MAX_EXTRACTED_SIZE = 500 * 1024 * 1024  # 500MB

_COPY_CHUNK = 65536

# Recognized archive filename suffixes (PRD section 5). Ordered longest
# first so `.tar.gz` wins over `.gz`-style suffix probing.
ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".tar",
    ".zip",
)


def is_archive_filename(name: str) -> bool:
    """Whether ``name`` looks like a supported archive."""
    lowered = name.lower()
    return any(lowered.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


@dataclass
class ExtractionResult:
    """Outcome of extracting one archive."""

    files: List[str] = field(default_factory=list)  # rel paths extracted
    skipped: List[str] = field(default_factory=list)  # unsafe/symlink/filtered members
    total_size: int = 0  # cumulative extracted bytes


class ArchiveExtractor:
    """Path-traversal-safe, bomb-bounded archive extraction.

    Supports ZIP and TAR (plain, gz, bz2, xz). ``pattern`` is the source's
    ``extract_pattern`` glob; members not matching it are skipped (not
    counted against the bomb bounds - they are never decompressed).
    """

    def __init__(
        self,
        pattern: Optional[str] = None,
        max_files: int = DEFAULT_MAX_EXTRACTED_FILES,
        max_total_size: int = DEFAULT_MAX_EXTRACTED_SIZE,
    ):
        self.pattern = pattern
        self.max_files = max_files
        self.max_total_size = max_total_size

    def extract(self, archive_path: Path, dest_dir: Path) -> ExtractionResult:
        """Extract ``archive_path`` into ``dest_dir`` (created if missing).

        Returns the list of extracted rel paths; raises RemoteSyncError on
        unsupported formats, corrupt archives, or bomb-bound violations.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = archive_path.name.lower()
        try:
            if name.endswith(".zip"):
                return self._extract_zip(archive_path, dest_dir)
            if name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                return self._extract_tar(archive_path, dest_dir)
        except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
            raise RemoteSyncError(f"Failed to extract archive {archive_path.name}: {e}") from e
        raise RemoteSyncError(
            f"Unsupported archive format: {archive_path.name} "
            f"(supported: {', '.join(ARCHIVE_SUFFIXES)})"
        )

    # ------------------------------------------------------------------
    # Format-specific extraction
    # ------------------------------------------------------------------

    def _extract_zip(self, archive_path: Path, dest_dir: Path) -> ExtractionResult:
        result = ExtractionResult()
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                # Unix mode lives in the high 16 bits of external_attr.
                # Reject any member whose file-type bits declare a
                # non-regular file (symlink members are the classic escape
                # vector). Members without type bits (Windows-produced
                # zips) are treated as regular files.
                file_type = stat.S_IFMT(info.external_attr >> 16)
                if file_type and file_type != stat.S_IFREG:
                    result.skipped.append(info.filename)
                    continue
                target = self._member_target(info.filename, dest_dir, result)
                if target is None:
                    continue
                with archive.open(info) as src:
                    self._copy_bounded(src, target, result, info.filename)
        return result

    def _extract_tar(self, archive_path: Path, dest_dir: Path) -> ExtractionResult:
        result = ExtractionResult()
        with tarfile.open(archive_path, mode="r:*") as archive:
            for member in archive:
                if member.isdir():
                    continue
                # Symlinks, hardlinks, devices, FIFOs: rejected. Only
                # regular file members are ever written to disk.
                if not member.isreg():
                    result.skipped.append(member.name)
                    continue
                target = self._member_target(member.name, dest_dir, result)
                if target is None:
                    continue
                src = archive.extractfile(member)
                if src is None:
                    result.skipped.append(member.name)
                    continue
                with src:
                    self._copy_bounded(src, target, result, member.name)
        return result

    # ------------------------------------------------------------------
    # Shared member handling
    # ------------------------------------------------------------------

    def _member_target(
        self, member_name: str, dest_dir: Path, result: ExtractionResult
    ) -> Optional[str]:
        """Resolve a member's safe target path; None to skip the member.

        Normalization keeps benign internal ``a/./b`` shapes working while
        absolute names and any net-``..`` traversal are rejected by the
        resolve_within/safe_relative_path guards.
        """
        rel_path = posixpath.normpath(member_name)
        if self.pattern and not matches_pattern(rel_path, self.pattern):
            result.skipped.append(member_name)
            return None
        # Untrusted member name: must resolve inside the extraction root
        # (rejects traversal, absolute paths, backslashes, drive letters).
        target = resolve_within(str(dest_dir), rel_path)
        if target is None:
            result.skipped.append(member_name)
            return None
        if len(result.files) + 1 > self.max_files:
            raise RemoteSyncError(
                f"Archive exceeds max_extracted_files ({self.max_files}); "
                "aborting extraction (possible decompression bomb)"
            )
        result.files.append(rel_path)
        return target

    def _copy_bounded(
        self, src: IO[bytes], target: str, result: ExtractionResult, member_name: str
    ) -> None:
        """Stream-copy a member, enforcing the cumulative size bound.

        Bytes are counted as decompressed - never trusted from headers. On
        violation the partially written tree is removed by the caller's
        temp-dir cleanup; here we just abort loudly.
        """
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as out:
            while True:
                chunk = src.read(_COPY_CHUNK)
                if not chunk:
                    break
                result.total_size += len(chunk)
                if result.total_size > self.max_total_size:
                    out.close()
                    self._remove_quietly(target)
                    raise RemoteSyncError(
                        f"Archive exceeds max_extracted_size ({self.max_total_size} bytes) "
                        f"while extracting '{member_name}'; aborting extraction "
                        "(possible decompression bomb)"
                    )
                out.write(chunk)

    @staticmethod
    def _remove_quietly(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass


def cleanup_dir(path: str) -> None:
    """Best-effort recursive removal of a temp extraction directory."""
    shutil.rmtree(path, ignore_errors=True)
