"""
MUXI.md -- the formation's CLAUDE.md.

A bounded, curated markdown file of behavioral learnings living in the
formation directory, sibling of SOUL.md. Formation-owned, git-trackable,
human-editable: a dev may write it by hand on day one. Injected into
overlord context wherever SOUL.md is injected; the tuner curates it.
Reads are mtime-cached so hand edits and API replacements take effect
on the next turn without a restart.

Under ``auto_apply: false`` the tuner writes PENDING-MUXI.md instead --
its suggested next version of the live file, regenerated every run.
Review = diff the two files; accept promotes pending to live.
"""

import os
import tempfile
import threading
from typing import Optional

# Candidate file names, checked in order (mirrors the SOUL.md loader).
_CANDIDATES = ("MUXI.md", "muxi.md")
_CANONICAL = "MUXI.md"
_PENDING = "PENDING-MUXI.md"

# MUXI.md is injected into every user's turn, so the "bounded file"
# contract is enforced at every write surface: ~32KB keeps it comparable
# to a large SOUL.md while bounding per-turn context inflation.
MUXI_MD_MAX_BYTES = 32_768


class MuxiMdFile:
    """The live MUXI.md file: mtime-cached reads, atomic replacement."""

    def __init__(self, formation_dir: Optional[str]):
        self.formation_dir = formation_dir
        self._lock = threading.Lock()
        self._cached_content: Optional[str] = None
        self._cached_mtime: Optional[float] = None
        self._cached_path: Optional[str] = None

    def resolve_path(self) -> Optional[str]:
        """The existing MUXI.md path, or None when the file is absent."""
        if not self.formation_dir:
            return None
        for candidate in _CANDIDATES:
            path = os.path.join(self.formation_dir, candidate)
            if os.path.isfile(path):
                return path
        return None

    def canonical_path(self) -> Optional[str]:
        """Where a write lands: the existing file, or MUXI.md when absent."""
        existing = self.resolve_path()
        if existing:
            return existing
        if not self.formation_dir:
            return None
        return os.path.join(self.formation_dir, _CANONICAL)

    def read(self) -> Optional[str]:
        """Current content, or None when absent/unreadable. Never raises."""
        path = self.resolve_path()
        if path is None:
            with self._lock:
                self._cached_content = None
                self._cached_mtime = None
                self._cached_path = None
            return None
        try:
            mtime = os.path.getmtime(path)
            with self._lock:
                if (
                    self._cached_path == path
                    and self._cached_mtime == mtime
                    and self._cached_content is not None
                ):
                    return self._cached_content
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            with self._lock:
                self._cached_content = content or None
                self._cached_mtime = mtime
                self._cached_path = path
            return content or None
        except OSError:
            return None

    def write(self, content: str) -> str:
        """Replace the live file atomically; returns the written path.

        Raises ValueError when no formation directory exists to hold it.
        """
        path = self.canonical_path()
        if path is None:
            raise ValueError("Formation has no directory to hold MUXI.md")
        # The lock covers the whole temp-write/replace/cache sequence so
        # concurrent replacements cannot interleave, and the temp file is
        # uniquely named so a crashed writer never corrupts a later one.
        with self._lock:
            _atomic_write(path, content)
            self._cached_content = content.strip() or None
            self._cached_mtime = os.path.getmtime(path)
            self._cached_path = path
        return path

    # ------------------------------------------------------------------
    # PENDING-MUXI.md (auto_apply: false suggestion flow)
    # ------------------------------------------------------------------

    def pending_path(self) -> Optional[str]:
        """Where the pending suggestion lives, or None without a dir."""
        if not self.formation_dir:
            return None
        return os.path.join(self.formation_dir, _PENDING)

    def read_pending(self) -> Optional[str]:
        """Pending suggestion content, or None when absent. Never raises."""
        path = self.pending_path()
        if path is None or not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            return content or None
        except OSError:
            return None

    def write_pending(self, content: str) -> str:
        """Replace the pending suggestion atomically; returns the path."""
        path = self.pending_path()
        if path is None:
            raise ValueError("Formation has no directory to hold PENDING-MUXI.md")
        with self._lock:
            _atomic_write(path, content)
        return path

    def promote_pending(self) -> str:
        """Accept the suggestion: pending becomes live, pending is removed.

        Raises ValueError when no pending suggestion exists.
        """
        content = self.read_pending()
        if content is None:
            raise ValueError("No pending MUXI.md suggestion to apply")
        path = self.write(content)
        self.discard_pending()
        return path

    def discard_pending(self) -> bool:
        """Dismiss the suggestion; True when a pending file was removed."""
        path = self.pending_path()
        if path is None:
            return False
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False


def _atomic_write(path: str, content: str) -> None:
    """Uniquely-named-tempfile atomic replace (crash never corrupts)."""
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".muxi-md-", suffix=".tmp")
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            # fdopen never took ownership; close the raw fd.
            os.close(fd)
            raise
        with f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


__all__ = ["MUXI_MD_MAX_BYTES", "MuxiMdFile"]
