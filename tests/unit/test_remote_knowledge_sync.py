"""Unit tests for the remote knowledge SyncManager orchestration.

Uses a stub in-memory protocol handler so sync behavior (change
detection, degrade paths, path safety, limits) is tested without any
network dependency.
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from unittest import mock

from muxi.runtime.formation.agents.knowledge.remote.handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    SourceConfig,
)
from muxi.runtime.formation.agents.knowledge.remote.manifest import MANIFEST_FILENAME, Manifest
from muxi.runtime.formation.agents.knowledge.remote.sync import (
    SyncManager,
    is_remote_source,
    partition_sources,
)


class StubHandler(ProtocolHandler):
    """In-memory enumerating handler: path -> bytes, with failure knobs."""

    def __init__(
        self,
        config: SourceConfig,
        files: Dict[str, bytes],
        fail_downloads=None,
        fail_listing: bool = False,
    ):
        super().__init__(config)
        self.files = files
        self.fail_downloads = set(fail_downloads or [])
        self.fail_listing = fail_listing
        self.download_calls: List[str] = []

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        if self.fail_listing:
            raise RemoteSyncError("remote unreachable")
        return [
            RemoteFile(
                path=path,
                url=f"stub://{path}",
                size=len(content),
                remote_hash=f"hash:{hashlib.sha256(content).hexdigest()[:8]}",
            )
            for path, content in self.files.items()
        ]

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        path = url.replace("stub://", "")
        self.download_calls.append(path)
        if path in self.fail_downloads:
            raise RemoteSyncError(f"download failed: {path}")
        content = self.files[path]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=len(content),
            local_hash=hashlib.sha256(content).hexdigest(),
        )


class StubIncrementalHandler(ProtocolHandler):
    """Incremental handler that materializes ``files`` into the dest tree."""

    def __init__(self, config: SourceConfig, files: Dict[str, bytes]):
        super().__init__(config)
        self.files = files

    async def list_files(self, url, pattern=None):
        raise NotImplementedError

    async def download_file(self, url, dest):
        raise NotImplementedError

    def supports_incremental(self) -> bool:
        return True

    async def sync_tree(self, url: str, dest_dir: Path) -> None:
        existing = set()
        for dirpath, _, filenames in os.walk(dest_dir):
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), dest_dir)
                existing.add(rel.replace(os.sep, "/"))
        for rel in existing - set(self.files):
            os.remove(os.path.join(dest_dir, rel))
        for rel, content in self.files.items():
            target = dest_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)


def make_manager(tmp_path, handler_factory):
    manager = SyncManager(agent_id="agent-x", root_dir=str(tmp_path / "remote-root"))
    patcher = mock.patch(
        "muxi.runtime.formation.agents.knowledge.remote.sync.create_handler",
        side_effect=handler_factory,
    )
    return manager, patcher


SOURCE = {
    "url": "stub://source",
    "id": "stub-source",
    "description": "stub remote source",
}


class TestPartitioning:
    def test_is_remote_source(self):
        assert is_remote_source({"url": "s3://bucket/x"})
        assert not is_remote_source({"path": "knowledge/docs/"})
        assert not is_remote_source({"url": ""})
        assert not is_remote_source("knowledge/docs/")

    def test_partition_preserves_order_and_identity(self):
        local1 = {"path": "a/"}
        remote1 = {"url": "s3://b/x"}
        local2 = {"path": "c/"}
        local, remote = partition_sources([local1, remote1, local2])
        assert local == [local1, local2]
        assert remote == [remote1]
        assert local[0] is local1  # same objects, not copies

    async def test_prepare_sources_local_only_is_inert(self, tmp_path):
        """Formations with only local sources get the same list object back."""
        manager = SyncManager(agent_id="agent-x", root_dir=str(tmp_path))
        sources = [{"path": "knowledge/docs/", "description": "local"}]
        result = await manager.prepare_sources(sources)
        assert result is sources  # untouched, no sync side effects
        assert not (tmp_path / "content").exists()


class TestInertWhenUnconfigured:
    async def test_local_only_formation_never_imports_remote_sync(self, tmp_path):
        """Pin: KnowledgeHandler.from_agent_config with only local sources
        must never touch the remote sync machinery."""
        from muxi.runtime.formation.agents.knowledge.handler import KnowledgeHandler

        knowledge_file = tmp_path / "facts.md"
        knowledge_file.write_text("Local knowledge only.", encoding="utf-8")

        working_memory = mock.MagicMock()
        working_memory.get_items_by_metadata.return_value = []

        async def fake_embeddings(texts):
            return [[0.0] * 8 for _ in texts]

        # Temporarily remove any already-imported remote modules so a
        # fresh import during the call would be observable; restore them
        # afterwards so other tests keep their module identity.
        removed = {
            name: sys.modules.pop(name) for name in list(sys.modules) if ".knowledge.remote" in name
        }
        try:
            with mock.patch.object(
                KnowledgeHandler, "load_sources_from_config", autospec=True
            ) as load_mock:
                handler = await KnowledgeHandler.from_agent_config(
                    agent_id="local-agent",
                    knowledge_config={
                        "enabled": True,
                        "sources": [{"path": str(knowledge_file), "description": "facts"}],
                    },
                    generate_embeddings_fn=fake_embeddings,
                    embedding_dimension=8,
                    working_memory=working_memory,
                    cache_dir=str(tmp_path / "cache"),
                )

            assert handler is not None
            # The exact same list object flows through - identical local path
            passed_sources = load_mock.call_args[0][1]
            assert passed_sources == [
                {
                    "path": str(knowledge_file),
                    "description": "facts",
                    "max_files": 100,
                    "max_file_size": 10 * 1024 * 1024,
                }
            ]
            assert not any(".knowledge.remote" in name for name in sys.modules)
        finally:
            sys.modules.update(removed)


class TestEnumeratedSync:
    async def test_cold_sync_downloads_everything(self, tmp_path):
        files = {"a.md": b"alpha", "nested/b.md": b"beta"}
        manager, patcher = make_manager(tmp_path, lambda cfg: StubHandler(cfg, files))
        with patcher:
            result = await manager.sync_source(dict(SOURCE))

        assert result.status == "success"
        assert result.files_added == 2
        assert result.files_modified == 0
        assert result.bytes_downloaded == 9
        content_dir = Path(result.content_dir)
        assert (content_dir / "a.md").read_bytes() == b"alpha"
        assert (content_dir / "nested" / "b.md").read_bytes() == b"beta"

        manifest = Manifest.load(
            str(content_dir.parent / MANIFEST_FILENAME), "stub-source", SOURCE["url"]
        )
        assert manifest.last_sync_status == "success"
        assert set(manifest.files) == {"a.md", "nested/b.md"}

    async def test_unchanged_files_not_redownloaded(self, tmp_path):
        files = {"a.md": b"alpha"}
        handlers = []

        def factory(cfg):
            handler = StubHandler(cfg, files)
            handlers.append(handler)
            return handler

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            await manager.sync_source(dict(SOURCE))
            result = await manager.sync_source(dict(SOURCE))

        assert result.files_added == 0
        assert result.files_modified == 0
        assert handlers[1].download_calls == []

    async def test_modified_file_redownloaded_and_deleted_file_removed(self, tmp_path):
        first = {"a.md": b"alpha", "b.md": b"beta"}
        second = {"a.md": b"ALPHA v2"}
        state = {"files": first}

        def factory(cfg):
            return StubHandler(cfg, state["files"])

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            await manager.sync_source(dict(SOURCE))
            state["files"] = second
            result = await manager.sync_source(dict(SOURCE))

        assert result.files_modified == 1
        assert result.files_deleted == 1
        content_dir = Path(result.content_dir)
        assert (content_dir / "a.md").read_bytes() == b"ALPHA v2"
        assert not (content_dir / "b.md").exists()

    async def test_partial_failure_keeps_stale_copy(self, tmp_path):
        files = {"a.md": b"alpha", "b.md": b"beta"}
        state = {"files": dict(files), "fail": set()}

        def factory(cfg):
            return StubHandler(cfg, state["files"], fail_downloads=state["fail"])

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            await manager.sync_source(dict(SOURCE))
            # b.md changes remotely but its download now fails
            state["files"] = {"a.md": b"alpha", "b.md": b"beta v2"}
            state["fail"] = {"b.md"}
            result = await manager.sync_source(dict(SOURCE))

        assert result.status == "partial"
        assert result.files_failed == 1
        # Stale-wins: previous copy still present and still indexed
        content_dir = Path(result.content_dir)
        assert (content_dir / "b.md").read_bytes() == b"beta"
        manifest = Manifest.load(
            str(content_dir.parent / MANIFEST_FILENAME), "stub-source", SOURCE["url"]
        )
        assert "b.md" in manifest.files
        assert manifest.last_sync_status == "partial"

    async def test_total_failure_degrades_to_synced_state(self, tmp_path):
        state = {"fail_listing": False}

        def factory(cfg):
            return StubHandler(cfg, {"a.md": b"alpha"}, fail_listing=state["fail_listing"])

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            first = await manager.sync_source(dict(SOURCE))
            state["fail_listing"] = True
            result = await manager.sync_source(dict(SOURCE))

        assert first.status == "success"
        assert result.status == "failed"
        assert "unreachable" in result.error
        assert result.has_local_content  # stale mirror survives
        assert (Path(result.content_dir) / "a.md").read_bytes() == b"alpha"
        manifest = Manifest.load(
            str(Path(result.content_dir).parent / MANIFEST_FILENAME),
            "stub-source",
            SOURCE["url"],
        )
        assert manifest.last_sync_status == "failed"

    async def test_cold_start_failure_yields_no_content(self, tmp_path):
        manager, patcher = make_manager(
            tmp_path, lambda cfg: StubHandler(cfg, {}, fail_listing=True)
        )
        with patcher:
            result = await manager.sync_source(dict(SOURCE))
        assert result.status == "failed"
        assert not result.has_local_content

    async def test_path_traversal_files_never_written(self, tmp_path):
        files = {
            "../evil.md": b"escape",
            "/abs/evil.md": b"escape",
            "safe.md": b"ok",
        }
        manager, patcher = make_manager(tmp_path, lambda cfg: StubHandler(cfg, files))
        with patcher:
            result = await manager.sync_source(dict(SOURCE))

        content_dir = Path(result.content_dir)
        assert (content_dir / "safe.md").exists()
        assert not (tmp_path / "remote-root" / "stub-source" / "evil.md").exists()
        assert not (tmp_path / "evil.md").exists()
        assert not Path("/abs/evil.md").exists()
        assert result.files_failed == 2
        assert sorted(result.skipped_files) == ["../evil.md", "/abs/evil.md"]

    async def test_limits_and_filters(self, tmp_path):
        files = {
            "keep-1.md": b"a" * 10,
            "keep-2.md": b"b" * 10,
            "drafts/skip.md": b"c" * 10,
            "too-big.md": b"d" * 1000,
            "notes.txt": b"e" * 10,
        }
        source = {
            **SOURCE,
            "include": ["*.md"],
            "exclude": ["drafts/*"],
            "max_file_size": 100,
        }
        manager, patcher = make_manager(tmp_path, lambda cfg: StubHandler(cfg, files))
        with patcher:
            result = await manager.sync_source(source)

        content_dir = Path(result.content_dir)
        synced = sorted(
            os.path.relpath(os.path.join(d, f), content_dir)
            for d, _, names in os.walk(content_dir)
            for f in names
        )
        assert synced == ["keep-1.md", "keep-2.md"]

    async def test_max_files_limit(self, tmp_path):
        files = {f"f{i}.md": b"x" for i in range(5)}
        source = {**SOURCE, "max_files": 2}
        manager, patcher = make_manager(tmp_path, lambda cfg: StubHandler(cfg, files))
        with patcher:
            result = await manager.sync_source(source)
        assert result.files_added == 2
        assert len(result.skipped_files) == 3


class TestIncrementalSync:
    async def test_incremental_add_modify_delete(self, tmp_path):
        state = {"files": {"a.md": b"alpha", "b.md": b"beta"}}

        def factory(cfg):
            return StubIncrementalHandler(cfg, state["files"])

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            first = await manager.sync_source(dict(SOURCE))
            state["files"] = {"a.md": b"alpha v2", "c.md": b"gamma"}
            second = await manager.sync_source(dict(SOURCE))

        assert first.files_added == 2
        assert second.files_added == 1  # c.md
        assert second.files_modified == 1  # a.md
        assert second.files_deleted == 1  # b.md
        content_dir = Path(second.content_dir)
        assert sorted(p.name for p in content_dir.iterdir()) == ["a.md", "c.md"]
        manifest = Manifest.load(
            str(content_dir.parent / MANIFEST_FILENAME), "stub-source", SOURCE["url"]
        )
        assert set(manifest.files) == {"a.md", "c.md"}


class TestPrepareSources:
    async def test_mixed_sources_yield_local_plus_synthetic(self, tmp_path):
        local = {"path": "/formation/knowledge/faq/", "description": "faq"}
        remote = dict(SOURCE)
        manager, patcher = make_manager(tmp_path, lambda cfg: StubHandler(cfg, {"a.md": b"alpha"}))
        with patcher:
            prepared = await manager.prepare_sources([local, remote])

        assert prepared[0] is local
        synthetic = prepared[1]
        assert synthetic["name"] == "stub-source"
        assert synthetic["description"] == "stub remote source"
        assert synthetic["path"].endswith(os.path.join("stub-source", "content"))
        assert os.path.isfile(os.path.join(synthetic["path"], "a.md"))

    async def test_cold_start_unreachable_source_dropped_with_warning(self, tmp_path, capsys):
        remote = dict(SOURCE)
        manager, patcher = make_manager(
            tmp_path, lambda cfg: StubHandler(cfg, {}, fail_listing=True)
        )
        with patcher:
            prepared = await manager.prepare_sources([remote])

        assert prepared == []
        captured = capsys.readouterr()
        assert "no local content" in captured.out

    async def test_degraded_source_still_prepared_from_stale_mirror(self, tmp_path):
        state = {"fail_listing": False}

        def factory(cfg):
            return StubHandler(cfg, {"a.md": b"alpha"}, fail_listing=state["fail_listing"])

        manager, patcher = make_manager(tmp_path, factory)
        with patcher:
            await manager.prepare_sources([dict(SOURCE)])
            state["fail_listing"] = True
            prepared = await manager.prepare_sources([dict(SOURCE)])

        assert len(prepared) == 1
        assert os.path.isfile(os.path.join(prepared[0]["path"], "a.md"))
