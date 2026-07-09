"""Unit tests for remote knowledge manifest tracking and path safety."""

import json
import os

from muxi.runtime.formation.agents.knowledge.remote.manifest import (
    Manifest,
    resolve_within,
    safe_relative_path,
)

SOURCE_ID = "test-source"
URL = "https://example.com/docs.md"


class TestSafeRelativePath:
    def test_accepts_simple_and_nested_paths(self):
        assert safe_relative_path("docs.md")
        assert safe_relative_path("nested/dir/file.txt")
        assert safe_relative_path("with-dash_and.dots.md")

    def test_rejects_traversal_and_absolute_paths(self):
        assert not safe_relative_path("../escape.md")
        assert not safe_relative_path("nested/../../escape.md")
        assert not safe_relative_path("/etc/passwd")
        assert not safe_relative_path("~/secrets")
        assert not safe_relative_path("C:/windows/system32")
        assert not safe_relative_path("back\\slash.md")
        assert not safe_relative_path("nul\x00byte.md")
        assert not safe_relative_path("")
        assert not safe_relative_path(None)

    def test_rejects_traversal_hidden_by_normalization(self):
        assert not safe_relative_path("a/b/../../../escape.md")
        assert not safe_relative_path("..")


class TestResolveWithin:
    def test_resolves_inside_root(self, tmp_path):
        resolved = resolve_within(str(tmp_path), "sub/file.md")
        assert resolved is not None
        assert resolved.startswith(os.path.realpath(str(tmp_path)) + os.sep)

    def test_rejects_escaping_paths(self, tmp_path):
        assert resolve_within(str(tmp_path), "../outside.md") is None
        assert resolve_within(str(tmp_path), "/abs/path.md") is None

    def test_rejects_symlink_escape(self, tmp_path):
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        (root / "link").symlink_to(outside)
        assert resolve_within(str(root), "link/file.md") is None


class TestManifestStateTransitions:
    def test_fresh_manifest_state(self, tmp_path):
        manifest = Manifest.load(str(tmp_path / "manifest.json"), SOURCE_ID, URL)
        assert manifest.last_sync_status == "never"
        assert manifest.files == {}
        assert not manifest.is_unchanged("docs.md", "etag:abc", 10)

    def test_record_then_unchanged(self, tmp_path):
        manifest = Manifest(source_id=SOURCE_ID, url=URL)
        manifest.record_file("docs.md", remote_hash="etag:abc", local_hash="sha", size=10)
        assert manifest.is_unchanged("docs.md", "etag:abc", 10)
        assert not manifest.is_unchanged("docs.md", "etag:def", 10)  # hash changed
        assert not manifest.is_unchanged("docs.md", "etag:abc", 11)  # size changed
        assert not manifest.is_unchanged("other.md", "etag:abc", 10)  # unknown file

    def test_missing_remote_hash_forces_redownload(self):
        manifest = Manifest(source_id=SOURCE_ID, url=URL)
        manifest.record_file("docs.md", remote_hash="", local_hash="sha", size=10)
        assert not manifest.is_unchanged("docs.md", "", 10)
        assert not manifest.is_unchanged("docs.md", None, 10)

    def test_mark_sync_lifecycle(self):
        manifest = Manifest(source_id=SOURCE_ID, url=URL)
        manifest.mark_sync("success", 123)
        assert manifest.last_sync_status == "success"
        assert manifest.last_sync_duration_ms == 123
        assert manifest.last_sync_error == ""
        manifest.mark_sync("failed", 456, error="boom")
        assert manifest.last_sync_status == "failed"
        assert manifest.last_sync_error == "boom"

    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "sub" / "manifest.json")
        manifest = Manifest(source_id=SOURCE_ID, url=URL)
        manifest.record_file("a/b.md", remote_hash="etag:1", local_hash="h1", size=5)
        manifest.mark_sync("success", 42)
        manifest.save(path)

        loaded = Manifest.load(path, SOURCE_ID, URL)
        assert loaded.last_sync_status == "success"
        assert loaded.last_sync_duration_ms == 42
        assert loaded.files["a/b.md"].remote_hash == "etag:1"
        assert loaded.files["a/b.md"].size == 5
        assert loaded.stats == {"total_files": 1, "total_size": 5}

    def test_corrupt_manifest_resets_to_empty(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text("{not valid json", encoding="utf-8")
        loaded = Manifest.load(str(path), SOURCE_ID, URL)
        assert loaded.files == {}
        assert loaded.last_sync_status == "never"

    def test_non_dict_manifest_resets_to_empty(self, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        loaded = Manifest.load(str(path), SOURCE_ID, URL)
        assert loaded.files == {}

    def test_load_drops_unsafe_paths(self, tmp_path):
        path = tmp_path / "manifest.json"
        data = {
            "source_id": SOURCE_ID,
            "url": URL,
            "last_sync_status": "success",
            "files": {
                "../escape.md": {"remote_hash": "x", "local_hash": "y", "size": 1},
                "/abs/path.md": {"remote_hash": "x", "local_hash": "y", "size": 1},
                "safe.md": {"remote_hash": "x", "local_hash": "y", "size": 1},
            },
        }
        path.write_text(json.dumps(data), encoding="utf-8")
        loaded = Manifest.load(str(path), SOURCE_ID, URL)
        assert list(loaded.files.keys()) == ["safe.md"]
