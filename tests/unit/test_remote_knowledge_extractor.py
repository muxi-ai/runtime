"""Unit tests for the remote knowledge ArchiveExtractor (Phase 2).

Covers format support (zip/tar/tar.gz), extract_pattern filtering, and the
security posture: path-traversal member names, symlink members, and
decompression-bomb bounds (total size + file count).
"""

import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from muxi.runtime.formation.agents.knowledge.remote.extractor import (
    ArchiveExtractor,
    is_archive_filename,
)
from muxi.runtime.formation.agents.knowledge.remote.handler import RemoteSyncError


def make_zip(path: Path, files: dict) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


def make_tar(path: Path, files: dict, mode: str = "w") -> Path:
    with tarfile.open(path, mode) as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return path


def tree(root: Path) -> dict:
    found = {}
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            full = Path(dirpath) / filename
            found[str(full.relative_to(root))] = full.read_bytes()
    return found


class TestFormats:
    def test_is_archive_filename(self):
        for name in ("a.zip", "a.tar", "a.tar.gz", "a.tgz", "a.tar.bz2", "a.tar.xz", "A.ZIP"):
            assert is_archive_filename(name), name
        for name in ("a.md", "a.gz", "a.pdf", "archive", ".."):
            assert not is_archive_filename(name), name

    def test_extract_zip(self, tmp_path):
        archive = make_zip(tmp_path / "kb.zip", {"a.md": b"alpha", "docs/b.md": b"beta"})
        result = ArchiveExtractor().extract(archive, tmp_path / "out")
        assert sorted(result.files) == ["a.md", "docs/b.md"]
        assert tree(tmp_path / "out") == {"a.md": b"alpha", os.path.join("docs", "b.md"): b"beta"}
        assert result.total_size == 9

    def test_extract_tar(self, tmp_path):
        archive = make_tar(tmp_path / "kb.tar", {"a.md": b"alpha", "docs/b.md": b"beta"})
        result = ArchiveExtractor().extract(archive, tmp_path / "out")
        assert sorted(result.files) == ["a.md", "docs/b.md"]

    def test_extract_tar_gz(self, tmp_path):
        archive = make_tar(tmp_path / "kb.tar.gz", {"nested/deep/c.md": b"gamma"}, mode="w:gz")
        result = ArchiveExtractor().extract(archive, tmp_path / "out")
        assert result.files == ["nested/deep/c.md"]
        assert (tmp_path / "out" / "nested" / "deep" / "c.md").read_bytes() == b"gamma"

    def test_unsupported_format_raises(self, tmp_path):
        bogus = tmp_path / "kb.rar"
        bogus.write_bytes(b"not an archive")
        with pytest.raises(RemoteSyncError, match="Unsupported archive format"):
            ArchiveExtractor().extract(bogus, tmp_path / "out")

    def test_corrupt_zip_raises(self, tmp_path):
        corrupt = tmp_path / "kb.zip"
        corrupt.write_bytes(b"definitely not a zip")
        with pytest.raises(RemoteSyncError, match="Failed to extract"):
            ArchiveExtractor().extract(corrupt, tmp_path / "out")


class TestPatternFiltering:
    def test_extract_pattern_keeps_only_matches(self, tmp_path):
        archive = make_zip(
            tmp_path / "kb.zip",
            {"a.md": b"alpha", "b.txt": b"skip", "docs/c.md": b"keep", "docs/d.log": b"skip"},
        )
        result = ArchiveExtractor(pattern="*.md").extract(archive, tmp_path / "out")
        assert sorted(result.files) == ["a.md", "docs/c.md"]
        assert sorted(result.skipped) == ["b.txt", "docs/d.log"]
        assert not (tmp_path / "out" / "b.txt").exists()

    def test_skipped_members_never_decompressed_into_bounds(self, tmp_path):
        """Filtered-out members must not count against the size bound."""
        archive = make_zip(tmp_path / "kb.zip", {"big.bin": b"x" * 1000, "small.md": b"keep"})
        extractor = ArchiveExtractor(pattern="*.md", max_total_size=100)
        result = extractor.extract(archive, tmp_path / "out")
        assert result.files == ["small.md"]


class TestPathSafety:
    def test_traversal_member_names_rejected(self, tmp_path):
        # Zip member names with traversal / absolute paths must never
        # escape the extraction root.
        archive = make_zip(
            tmp_path / "evil.zip",
            {
                "../escape.md": b"evil",
                "/abs/escape.md": b"evil",
                "nested/../../escape2.md": b"evil",
                "safe.md": b"ok",
            },
        )
        out = tmp_path / "quarantine" / "out"
        result = ArchiveExtractor().extract(archive, out)
        assert result.files == ["safe.md"]
        assert len(result.skipped) == 3
        assert not (tmp_path / "escape.md").exists()
        assert not (tmp_path / "escape2.md").exists()
        assert not (tmp_path / "quarantine" / "escape.md").exists()
        assert not Path("/abs/escape.md").exists()
        assert tree(out) == {"safe.md": b"ok"}

    def test_tar_symlink_members_rejected(self, tmp_path):
        target = tmp_path / "outside.md"
        target.write_text("outside", encoding="utf-8")
        archive_path = tmp_path / "links.tar"
        with tarfile.open(archive_path, "w") as archive:
            link = tarfile.TarInfo("link.md")
            link.type = tarfile.SYMTYPE
            link.linkname = str(target)
            archive.addfile(link)
            hard = tarfile.TarInfo("hard.md")
            hard.type = tarfile.LNKTYPE
            hard.linkname = str(target)
            archive.addfile(hard)
            regular = tarfile.TarInfo("ok.md")
            regular.size = 2
            archive.addfile(regular, io.BytesIO(b"ok"))
        result = ArchiveExtractor().extract(archive_path, tmp_path / "out")
        assert result.files == ["ok.md"]
        assert sorted(result.skipped) == ["hard.md", "link.md"]
        assert not (tmp_path / "out" / "link.md").exists()

    def test_zip_symlink_members_rejected(self, tmp_path):
        archive_path = tmp_path / "links.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            info = zipfile.ZipInfo("link.md")
            # S_IFLNK | 0755 in the high 16 bits marks a symlink member
            info.external_attr = 0o120755 << 16
            archive.writestr(info, "/etc/passwd")
            archive.writestr("ok.md", "ok")
        result = ArchiveExtractor().extract(archive_path, tmp_path / "out")
        assert result.files == ["ok.md"]
        assert result.skipped == ["link.md"]
        assert not (tmp_path / "out" / "link.md").exists()


class TestBombBounds:
    def test_total_size_bound_aborts(self, tmp_path):
        # Highly compressible payload: small archive, big decompressed size
        archive = make_zip(tmp_path / "bomb.zip", {"bomb.md": b"0" * 100_000})
        with pytest.raises(RemoteSyncError, match="max_extracted_size"):
            ArchiveExtractor(max_total_size=1024).extract(archive, tmp_path / "out")
        # Nothing partial left behind for the caller to ingest
        assert not (tmp_path / "out" / "bomb.md").exists()

    def test_total_size_bound_is_cumulative(self, tmp_path):
        archive = make_zip(tmp_path / "bomb.zip", {f"f{i}.md": b"x" * 600 for i in range(4)})
        with pytest.raises(RemoteSyncError, match="max_extracted_size"):
            ArchiveExtractor(max_total_size=1500).extract(archive, tmp_path / "out")

    def test_file_count_bound_aborts(self, tmp_path):
        archive = make_zip(tmp_path / "many.zip", {f"f{i}.md": b"x" for i in range(20)})
        with pytest.raises(RemoteSyncError, match="max_extracted_files"):
            ArchiveExtractor(max_files=10).extract(archive, tmp_path / "out")

    def test_tar_lying_header_still_bounded(self, tmp_path):
        """Bytes are counted as decompressed - header sizes are not trusted."""
        archive = make_tar(tmp_path / "big.tar.gz", {"big.md": b"y" * 50_000}, mode="w:gz")
        with pytest.raises(RemoteSyncError, match="max_extracted_size"):
            ArchiveExtractor(max_total_size=100).extract(archive, tmp_path / "out")

    def test_within_bounds_succeeds(self, tmp_path):
        archive = make_zip(tmp_path / "ok.zip", {"a.md": b"x" * 100, "b.md": b"y" * 100})
        result = ArchiveExtractor(max_files=2, max_total_size=200).extract(
            archive, tmp_path / "out"
        )
        assert sorted(result.files) == ["a.md", "b.md"]
        assert result.total_size == 200
