"""
MUXI.md -- the formation's CLAUDE.md.

A bounded, curated markdown file of behavioral learnings living in the
formation directory, sibling of SOUL.md. Formation-owned, git-trackable,
human-editable: a dev may write it by hand on day one. Injected into
overlord context wherever SOUL.md is injected; Phase 2's tuner curates
it. Reads are mtime-cached so hand edits and API replacements take
effect on the next turn without a restart.
"""

import os
import tempfile
import threading
from typing import Optional

# Candidate file names, checked in order (mirrors the SOUL.md loader).
_CANDIDATES = ("MUXI.md", "muxi.md")
_CANONICAL = "MUXI.md"


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
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(path), prefix=".muxi-md-", suffix=".tmp"
            )
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
            self._cached_content = content.strip() or None
            self._cached_mtime = os.path.getmtime(path)
            self._cached_path = path
        return path


__all__ = ["MuxiMdFile"]
