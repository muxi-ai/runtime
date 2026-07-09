# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Sync Manager - Remote Knowledge Sources
# Description:  Orchestrates syncing remote sources into local mirrors
# Role:         Bridges url-based sources into the local knowledge pipeline
# Usage:        KnowledgeHandler.from_agent_config calls prepare_sources()
# Author:       Muxi Framework Team
#
# Design:
# - Remote content is mirrored under the runtime knowledge cache dir
#   (never inside the formation directory, which may be read-only):
#   <knowledge_dir>/remote/<agent_id>/<source_id>/content/
#   with the manifest one level up (so it is never ingested as content).
# - Each remote source becomes a synthetic local ``path`` source pointing
#   at its content mirror, feeding the unchanged local ingestion pipeline.
# - Failure isolation / cold-start policy: a failing sync NEVER blocks
#   formation startup or chat. The source degrades to whatever the
#   manifest says was previously synced (stale-wins, PRD open question
#   #2). On a cold start (nothing synced yet + source unreachable) the
#   source contributes zero knowledge; a loud init warning plus an
#   ERROR-level KNOWLEDGE_SYNC_FAILED event surface the gap.
# - Every remote source syncs once at formation startup; sources with a
#   periodic ``schedule`` are then re-synced by the Phase 3 scheduler
#   (see scheduler.py), which re-embeds only the changed files.
# - Archive sources (``extract: true``, Phase 2) download a single
#   archive and extract it (path-safe, bomb-bounded) into the mirror.
#
# Path safety: relative paths from handlers and manifests are validated
# (safe_relative_path + resolve_within) so synced files can never land
# outside the per-source content directory.
# =============================================================================

import asyncio
import os
import posixpath
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .....services import observability
from .....utils.user_dirs import get_knowledge_dir
from .extractor import (
    DEFAULT_MAX_EXTRACTED_FILES,
    DEFAULT_MAX_EXTRACTED_SIZE,
    ArchiveExtractor,
    cleanup_dir,
    is_archive_filename,
)
from .handler import (
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    SourceConfig,
    hash_file_sha256,
    matches_pattern,
    split_url_pattern,
)
from .manifest import MANIFEST_FILENAME, Manifest, resolve_within
from .protocols import create_handler


def is_remote_source(source_config: Any) -> bool:
    """Whether a knowledge source config declares a remote URL."""
    return isinstance(source_config, dict) and bool(source_config.get("url"))


def partition_sources(sources_config: List[Any]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Split knowledge sources into (local, remote) preserving order.

    Formations without remote sources get their original list back
    untouched, keeping the local-only path byte-for-byte identical.
    """
    local: List[Any] = []
    remote: List[Dict[str, Any]] = []
    for source in sources_config:
        (remote if is_remote_source(source) else local).append(source)
    return local, remote


@dataclass
class SyncResult:
    """Outcome of syncing one remote source."""

    source_id: str
    url: str
    status: str  # success | partial | failed
    content_dir: str
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    bytes_downloaded: int = 0
    duration_ms: int = 0
    error: str = ""
    skipped_files: List[str] = field(default_factory=list)
    # Rel paths whose local content changed (added or modified) / vanished
    # this sync. Phase 3 uses these to re-embed only what changed.
    changed_paths: List[str] = field(default_factory=list)
    deleted_paths: List[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Whether this sync changed any local content."""
        return bool(self.changed_paths or self.deleted_paths)

    @property
    def has_local_content(self) -> bool:
        """Whether any synced content exists locally (current or stale)."""
        try:
            for _, _, filenames in os.walk(self.content_dir):
                if filenames:
                    return True
        except OSError:
            pass
        return False


class SyncManager:
    """Orchestrates remote knowledge source syncs for one agent.

    Phase 1 syncs at formation startup only (scheduling is Phase 3);
    the per-source manifest keeps re-syncs incremental across restarts.
    """

    def __init__(
        self,
        agent_id: str,
        formation_id: str = "default-formation",
        root_dir: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.formation_id = formation_id
        self.root_dir = root_dir or os.path.join(get_knowledge_dir(), "remote", agent_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prepare_sources(self, sources_config: List[Any]) -> List[Any]:
        """Sync remote sources and return a fully-local source list.

        Local sources pass through untouched. Each remote source syncs
        into its content mirror and is replaced by a synthetic local
        source pointing at the mirror. Sources with no local content at
        all (cold start + unreachable) are dropped with a loud warning.
        """
        local_sources, remote_sources = partition_sources(sources_config)
        if not remote_sources:
            return sources_config

        prepared = list(local_sources)
        for raw_source in remote_sources:
            config = SourceConfig.from_dict(raw_source)
            result = await self.sync_source(raw_source)
            if result.has_local_content:
                prepared.append(self.synthetic_local_source(config, result))
            else:
                from .....datatypes.observability import InitEventFormatter

                print(
                    InitEventFormatter.format_warn(
                        f"Remote knowledge source '{config.source_id}' has no local content",
                        f"{result.error or 'sync failed before any content was mirrored'} "
                        f"- agent '{self.agent_id}' starts without this source",
                    )
                )
        return prepared

    async def sync_source(self, raw_source: Dict[str, Any], trigger: str = "startup") -> SyncResult:
        """Sync a single remote source, degrading to synced state on failure."""
        config = SourceConfig.from_dict(raw_source)
        source_dir = os.path.join(self.root_dir, config.source_id)
        content_dir = os.path.join(source_dir, "content")
        manifest_path = os.path.join(source_dir, MANIFEST_FILENAME)
        os.makedirs(content_dir, exist_ok=True)

        observability.observe(
            event_type=observability.SystemEvents.KNOWLEDGE_SYNC_STARTED,
            level=observability.EventLevel.INFO,
            description="Remote knowledge source sync started",
            data={
                "source_id": config.source_id,
                "url": config.url,
                "agent_id": self.agent_id,
                "trigger": trigger,
            },
        )

        manifest = Manifest.load(manifest_path, config.source_id, config.url)
        started = time.time()
        handler: Optional[ProtocolHandler] = None
        try:
            handler = create_handler(config)
            if config.extract:
                result = await self._sync_archive(handler, config, content_dir, manifest)
            elif handler.supports_incremental():
                result = await self._sync_incremental(handler, config, content_dir, manifest)
            else:
                result = await self._sync_enumerated(handler, config, content_dir, manifest)
        except Exception as e:
            duration_ms = int((time.time() - started) * 1000)
            result = SyncResult(
                source_id=config.source_id,
                url=config.url,
                status="failed",
                content_dir=content_dir,
                duration_ms=duration_ms,
                error=str(e),
            )
            manifest.mark_sync("failed", duration_ms, error=str(e))
            self._save_manifest(manifest, manifest_path)
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                level=(
                    observability.EventLevel.WARNING
                    if result.has_local_content
                    else observability.EventLevel.ERROR
                ),
                description="Remote knowledge source sync failed - degrading to synced state",
                data={
                    "source_id": config.source_id,
                    "url": config.url,
                    "agent_id": self.agent_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "has_local_content": result.has_local_content,
                    "trigger": trigger,
                },
            )
            return result
        finally:
            if handler is not None:
                try:
                    await handler.close()
                except Exception:
                    pass

        result.duration_ms = int((time.time() - started) * 1000)
        manifest.mark_sync(result.status, result.duration_ms, error=result.error)
        self._save_manifest(manifest, manifest_path)

        observability.observe(
            event_type=observability.SystemEvents.KNOWLEDGE_SYNC_COMPLETED,
            level=observability.EventLevel.INFO,
            description="Remote knowledge source sync completed",
            data={
                "source_id": config.source_id,
                "url": config.url,
                "agent_id": self.agent_id,
                "status": result.status,
                "duration_ms": result.duration_ms,
                "files_added": result.files_added,
                "files_modified": result.files_modified,
                "files_deleted": result.files_deleted,
                "files_failed": result.files_failed,
                "bytes_downloaded": result.bytes_downloaded,
                "trigger": trigger,
            },
        )
        return result

    # ------------------------------------------------------------------
    # Sync strategies
    # ------------------------------------------------------------------

    async def _sync_enumerated(
        self,
        handler: ProtocolHandler,
        config: SourceConfig,
        content_dir: str,
        manifest: Manifest,
    ) -> SyncResult:
        """List/compare/download sync for enumerating handlers (HTTP, S3, file)."""
        base_url, pattern = split_url_pattern(config.url)
        remote_files = await handler.list_files(base_url, pattern)

        result = SyncResult(
            source_id=config.source_id, url=config.url, status="success", content_dir=content_dir
        )

        selected: List[RemoteFile] = []
        total_size = 0
        for remote_file in sorted(remote_files, key=lambda f: f.path):
            if not self._passes_filters(remote_file.path, config):
                continue
            local_path = resolve_within(content_dir, remote_file.path)
            if local_path is None:
                # Path traversal guard: never let remote paths escape the mirror
                result.skipped_files.append(remote_file.path)
                result.files_failed += 1
                continue
            if remote_file.size is not None and remote_file.size > config.max_file_size:
                result.skipped_files.append(remote_file.path)
                continue
            if len(selected) >= config.max_files:
                result.skipped_files.append(remote_file.path)
                continue
            if remote_file.size is not None:
                if total_size + remote_file.size > config.max_total_size:
                    result.skipped_files.append(remote_file.path)
                    continue
                total_size += remote_file.size
            selected.append(remote_file)

        seen_paths = set()
        new_files: Dict[str, Any] = {}
        for remote_file in selected:
            rel_path = remote_file.path
            seen_paths.add(rel_path)
            local_path = resolve_within(content_dir, rel_path)
            existing = manifest.files.get(rel_path)

            if manifest.is_unchanged(
                rel_path, remote_file.remote_hash, remote_file.size
            ) and os.path.isfile(local_path):
                new_files[rel_path] = existing
                continue

            try:
                download = await handler.download_file(remote_file.url, Path(local_path))
            except Exception as e:
                result.files_failed += 1
                if existing is not None and os.path.isfile(local_path):
                    # Stale-wins: keep the previously synced copy
                    new_files[rel_path] = existing
                observability.observe(
                    event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="Remote knowledge file download failed",
                    data={
                        "source_id": config.source_id,
                        "file": rel_path,
                        "error": str(e),
                        "stale_copy_kept": existing is not None,
                    },
                )
                continue

            manifest.record_file(
                rel_path,
                remote_hash=remote_file.remote_hash or "",
                local_hash=download.local_hash,
                size=download.size,
            )
            new_files[rel_path] = manifest.files[rel_path]
            result.bytes_downloaded += download.size
            if existing is None:
                result.files_added += 1
            else:
                result.files_modified += 1
            if existing is None or existing.local_hash != download.local_hash:
                result.changed_paths.append(rel_path)

        # Remote deletions: drop local files whose manifest entry vanished
        for rel_path in list(manifest.files.keys()):
            if rel_path in seen_paths:
                continue
            local_path = resolve_within(content_dir, rel_path)
            if local_path and os.path.isfile(local_path):
                try:
                    os.remove(local_path)
                    result.files_deleted += 1
                    result.deleted_paths.append(rel_path)
                except OSError:
                    pass

        manifest.files = {rel: record for rel, record in new_files.items() if record is not None}
        _prune_empty_dirs(content_dir)

        if result.files_failed:
            result.status = "partial"
            result.error = f"{result.files_failed} file(s) failed to sync"
        return result

    async def _sync_incremental(
        self,
        handler: ProtocolHandler,
        config: SourceConfig,
        content_dir: str,
        manifest: Manifest,
    ) -> SyncResult:
        """Whole-tree sync for incremental handlers (rsync)."""
        before = _snapshot_tree(content_dir)
        await handler.sync_tree(config.url, Path(content_dir))
        after = _snapshot_tree(content_dir)

        result = SyncResult(
            source_id=config.source_id, url=config.url, status="success", content_dir=content_dir
        )

        manifest.files.clear()
        for rel_path, (size, token) in after.items():
            local_path = resolve_within(content_dir, rel_path)
            if local_path is None:
                # Never index a path that resolves outside the mirror
                try:
                    os.remove(os.path.join(content_dir, rel_path))
                except OSError:
                    pass
                result.skipped_files.append(rel_path)
                continue
            previous = before.get(rel_path)
            if previous is None:
                result.files_added += 1
                result.bytes_downloaded += size
                result.changed_paths.append(rel_path)
            elif previous != (size, token):
                result.files_modified += 1
                result.bytes_downloaded += size
                result.changed_paths.append(rel_path)
            manifest.record_file(
                rel_path,
                remote_hash=token,
                local_hash=hash_file_sha256(Path(local_path)),
                size=size,
            )

        result.deleted_paths = sorted(set(before) - set(after))
        result.files_deleted = len(result.deleted_paths)
        return result

    async def _sync_archive(
        self,
        handler: ProtocolHandler,
        config: SourceConfig,
        content_dir: str,
        manifest: Manifest,
    ) -> SyncResult:
        """Download-and-extract sync for archive sources (``extract: true``).

        The archive downloads and extracts into a hidden temp dir NEXT TO
        the content mirror (same filesystem, never ingested); only after
        extraction fully succeeds does the mirror get updated file-by-file
        (``os.replace``). Any failure before that point leaves the previous
        mirror untouched (stale-wins). Temp state is always cleaned up.
        """
        remote_files = await handler.list_files(config.url, None)
        if len(remote_files) != 1:
            raise RemoteSyncError(
                f"Archive knowledge source must resolve to exactly one file, "
                f"got {len(remote_files)}: {config.url}"
            )
        archive = remote_files[0]

        result = SyncResult(
            source_id=config.source_id, url=config.url, status="success", content_dir=content_dir
        )

        # Unchanged archive with an intact mirror: skip download + extraction.
        if (
            archive.remote_hash
            and manifest.archive_hash == archive.remote_hash
            and (archive.size is None or manifest.archive_size == archive.size)
            and result.has_local_content
        ):
            return result

        work_dir = tempfile.mkdtemp(prefix=".archive-", dir=os.path.dirname(content_dir))
        try:
            archive_path = Path(work_dir) / self._archive_filename(archive, config)
            download = await handler.download_file(archive.url, archive_path)
            result.bytes_downloaded = download.size

            if not is_archive_filename(archive_path.name):
                raise RemoteSyncError(
                    f"'extract: true' source is not a supported archive: {archive_path.name}"
                )

            extractor = ArchiveExtractor(
                pattern=config.extract_pattern,
                max_files=config.max_extracted_files or DEFAULT_MAX_EXTRACTED_FILES,
                max_total_size=config.max_extracted_size or DEFAULT_MAX_EXTRACTED_SIZE,
            )
            extract_dir = Path(work_dir) / "extracted"
            extraction = await asyncio.to_thread(extractor.extract, archive_path, extract_dir)
            result.skipped_files.extend(extraction.skipped)

            # Apply the standard per-source selection limits to the
            # extracted tree (include/exclude, per-file size, count, total).
            selected: List[Tuple[str, str, int]] = []
            total_size = 0
            for rel_path in sorted(extraction.files):
                if not self._passes_filters(rel_path, config):
                    continue
                src_path = os.path.join(str(extract_dir), rel_path)
                try:
                    size = os.path.getsize(src_path)
                except OSError:
                    result.skipped_files.append(rel_path)
                    continue
                if size > config.max_file_size:
                    result.skipped_files.append(rel_path)
                    continue
                if len(selected) >= config.max_files:
                    result.skipped_files.append(rel_path)
                    continue
                if total_size + size > config.max_total_size:
                    result.skipped_files.append(rel_path)
                    continue
                total_size += size
                selected.append((rel_path, src_path, size))

            # Materialize into the content mirror (extraction is complete
            # and bounded at this point). Same filesystem -> atomic swaps.
            seen_paths = set()
            new_files: Dict[str, Any] = {}
            for rel_path, src_path, size in selected:
                target = resolve_within(content_dir, rel_path)
                if target is None:
                    result.skipped_files.append(rel_path)
                    result.files_failed += 1
                    continue
                seen_paths.add(rel_path)
                local_hash = hash_file_sha256(Path(src_path))
                existing = manifest.files.get(rel_path)
                if (
                    existing is not None
                    and existing.local_hash == local_hash
                    and os.path.isfile(target)
                ):
                    new_files[rel_path] = existing
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.replace(src_path, target)
                manifest.record_file(
                    rel_path,
                    remote_hash=archive.remote_hash or "",
                    local_hash=local_hash,
                    size=size,
                )
                new_files[rel_path] = manifest.files[rel_path]
                result.changed_paths.append(rel_path)
                if existing is None:
                    result.files_added += 1
                else:
                    result.files_modified += 1

            # Files present in the previous archive but not this one
            for rel_path in list(manifest.files.keys()):
                if rel_path in seen_paths:
                    continue
                target = resolve_within(content_dir, rel_path)
                if target and os.path.isfile(target):
                    try:
                        os.remove(target)
                        result.files_deleted += 1
                        result.deleted_paths.append(rel_path)
                    except OSError:
                        pass

            manifest.files = new_files
            manifest.archive_hash = archive.remote_hash or ""
            manifest.archive_size = archive.size if archive.size is not None else download.size
            _prune_empty_dirs(content_dir)
        finally:
            cleanup_dir(work_dir)

        if result.files_failed:
            result.status = "partial"
            result.error = f"{result.files_failed} file(s) failed to sync"
        return result

    @staticmethod
    def _archive_filename(archive: RemoteFile, config: SourceConfig) -> str:
        """Pick a local filename that preserves the archive's format suffix."""
        for candidate in (
            posixpath.basename(urlparse(archive.url).path),
            archive.path,
            posixpath.basename(urlparse(config.url).path),
        ):
            candidate = posixpath.basename(candidate or "")
            if candidate and is_archive_filename(candidate):
                return candidate
        return "archive"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _passes_filters(self, rel_path: str, config: SourceConfig) -> bool:
        if config.include and not any(
            matches_pattern(rel_path, pattern) for pattern in config.include
        ):
            return False
        return not any(matches_pattern(rel_path, pattern) for pattern in config.exclude)

    def synthetic_local_source(self, config: SourceConfig, result: SyncResult) -> Dict[str, Any]:
        """Build the local ``path`` source config for a synced mirror.

        Used at startup (prepare_sources) and by the Phase 3 re-sync
        scheduler when re-embedding changed mirror files.
        """
        return {
            "path": result.content_dir,
            "name": config.source_id,
            "description": config.description or f"Remote knowledge source: {config.url}",
            "max_files": config.max_files,
            "max_file_size": config.max_file_size,
            "recursive": True,
        }

    def _save_manifest(self, manifest: Manifest, manifest_path: str) -> None:
        try:
            manifest.save(manifest_path)
        except OSError as e:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SYNC_FAILED,
                level=observability.EventLevel.WARNING,
                description="Failed to persist remote knowledge manifest",
                data={"source_id": manifest.source_id, "error": str(e)},
            )


def _snapshot_tree(root: str) -> Dict[str, Tuple[int, str]]:
    """Map rel_path -> (size, stat token) for every file under ``root``."""
    snapshot: Dict[str, Tuple[int, str]] = {}
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            if os.path.islink(full_path) or not os.path.isfile(full_path):
                continue
            rel_path = os.path.relpath(full_path, root).replace(os.sep, "/")
            stat = os.stat(full_path)
            snapshot[rel_path] = (stat.st_size, f"stat:{stat.st_size}:{stat.st_mtime_ns}")
    return snapshot


def _prune_empty_dirs(root: str) -> None:
    """Remove empty directories left behind by deletions (keep ``root``)."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath == root or dirnames or filenames:
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass


# Re-exported for convenience in tests and callers
__all__ = [
    "RemoteSyncError",
    "SyncManager",
    "SyncResult",
    "is_remote_source",
    "partition_sources",
]
