"""Unit tests for the remote knowledge protocol handlers.

Handlers are exercised against local fixtures (temp dirs, an in-process
aiohttp server) and mocked SDK clients (boto3) — no real S3/rsync
infrastructure is required.
"""

import hashlib
import os
import stat as stat_module
from pathlib import Path
from unittest import mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from muxi.runtime.formation.agents.knowledge.remote.handler import (
    RemoteSyncError,
    SourceConfig,
    derive_source_id,
    matches_pattern,
    split_url_pattern,
)
from muxi.runtime.formation.agents.knowledge.remote.protocols import (
    PLANNED_SCHEMES,
    SUPPORTED_SCHEMES,
    create_handler,
)
from muxi.runtime.formation.agents.knowledge.remote.protocols.file import FileHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.http import HTTPHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.rsync import RsyncHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.s3 import S3Handler


def make_config(url, **overrides):
    return SourceConfig.from_dict({"url": url, **overrides})


class TestUrlHelpers:
    def test_split_url_pattern(self):
        assert split_url_pattern("https://host/notes.md") == ("https://host/notes.md", None)
        assert split_url_pattern("s3://bucket/docs/*.md") == ("s3://bucket/docs/", "*.md")
        assert split_url_pattern("s3://bucket/docs/**/*.pdf") == ("s3://bucket/docs/", "**/*.pdf")
        assert split_url_pattern("s3://bucket/prefix/*") == ("s3://bucket/prefix/", "*")

    def test_matches_pattern_basename_fallback(self):
        assert matches_pattern("nested/dir/file.md", "*.md")
        assert matches_pattern("file.md", "*.md")
        assert not matches_pattern("file.txt", "*.md")
        assert matches_pattern("nested/dir/file.md", "nested/*/*.md")
        assert not matches_pattern("other/file.md", "nested/*")

    def test_derive_source_id_stable_and_safe(self):
        a = derive_source_id("https://example.com/docs/a.md")
        b = derive_source_id("https://example.com/docs/b.md")
        assert a == derive_source_id("https://example.com/docs/a.md")
        assert a != b
        assert "/" not in a and ":" not in a

    def test_registry_scheme_sets_are_disjoint(self):
        assert not (SUPPORTED_SCHEMES & PLANNED_SCHEMES)

    def test_create_handler_dispatch(self):
        assert isinstance(create_handler(make_config("https://h/x.md")), HTTPHandler)
        assert isinstance(create_handler(make_config("file:///tmp/x")), FileHandler)
        assert isinstance(create_handler(make_config("rsync://h/mod/x/")), RsyncHandler)
        with pytest.raises(RemoteSyncError):
            create_handler(make_config("ftp://h/x"))


class TestFileHandler:
    async def test_list_and_download_directory(self, tmp_path):
        src = tmp_path / "mount"
        (src / "sub").mkdir(parents=True)
        (src / "a.md").write_text("alpha", encoding="utf-8")
        (src / "sub" / "b.md").write_text("beta", encoding="utf-8")
        (src / "c.txt").write_text("gamma", encoding="utf-8")

        handler = FileHandler(make_config(src.as_uri()))
        files = await handler.list_files(src.as_uri(), "*.md")
        assert sorted(f.path for f in files) == ["a.md", "sub/b.md"]
        assert all(f.remote_hash.startswith("stat:") for f in files)

        dest = tmp_path / "mirror" / "a.md"
        result = await handler.download_file(files[0].url, dest)
        assert dest.read_text(encoding="utf-8") == "alpha"
        assert result.size == 5
        assert result.local_hash == hashlib.sha256(b"alpha").hexdigest()

    async def test_single_file_source(self, tmp_path):
        src = tmp_path / "single.md"
        src.write_text("solo", encoding="utf-8")
        handler = FileHandler(make_config(src.as_uri()))
        files = await handler.list_files(src.as_uri())
        assert [f.path for f in files] == ["single.md"]
        assert files[0].size == 4

    async def test_missing_path_raises(self, tmp_path):
        url = (tmp_path / "nope").as_uri()
        handler = FileHandler(make_config(url))
        with pytest.raises(RemoteSyncError):
            await handler.list_files(url)

    async def test_max_file_size_enforced(self, tmp_path):
        src = tmp_path / "big.md"
        src.write_text("x" * 100, encoding="utf-8")
        handler = FileHandler(make_config(src.as_uri(), max_file_size=10))
        with pytest.raises(RemoteSyncError, match="max_file_size"):
            await handler.download_file(src.as_uri(), tmp_path / "out.md")

    async def test_relative_file_url_rejected(self):
        handler = FileHandler(make_config("file://remote-host/path"))
        with pytest.raises(RemoteSyncError):
            await handler.list_files("file://remote-host/path")

    async def test_symlinked_files_skipped(self, tmp_path):
        src = tmp_path / "mount"
        src.mkdir()
        (src / "real.md").write_text("real", encoding="utf-8")
        (tmp_path / "outside.md").write_text("outside", encoding="utf-8")
        (src / "link.md").symlink_to(tmp_path / "outside.md")
        handler = FileHandler(make_config(src.as_uri()))
        files = await handler.list_files(src.as_uri())
        assert [f.path for f in files] == ["real.md"]


class TestHTTPHandler:
    @pytest.fixture
    async def http_server(self, tmp_path):
        content = b"# Remote doc\nThe capital of Zephyria is Windmere.\n"

        async def doc(request):
            return web.Response(
                body=content,
                headers={"Content-Type": "text/markdown", "ETag": '"v1"'},
            )

        async def flaky_head(request):
            if request.method == "HEAD":
                return web.Response(status=405)
            return web.Response(body=b"no-head body", headers={"Content-Type": "text/plain"})

        async def huge(request):
            return web.Response(body=b"y" * 4096, headers={"Content-Type": "text/plain"})

        app = web.Application()
        app.router.add_route("*", "/docs/guide.md", doc)
        app.router.add_route("*", "/no-head", flaky_head)
        app.router.add_route("*", "/huge.txt", huge)
        server = TestServer(app)
        await server.start_server()
        yield server, content
        await server.close()

    async def test_list_single_file(self, http_server):
        server, content = http_server
        url = str(server.make_url("/docs/guide.md"))
        handler = HTTPHandler(make_config(url))
        files = await handler.list_files(url)
        assert len(files) == 1
        assert files[0].path == "guide.md"
        assert files[0].size == len(content)
        assert files[0].remote_hash == "etag:v1"

    async def test_download_file(self, http_server, tmp_path):
        server, content = http_server
        url = str(server.make_url("/docs/guide.md"))
        handler = HTTPHandler(make_config(url))
        dest = tmp_path / "guide.md"
        result = await handler.download_file(url, dest)
        assert dest.read_bytes() == content
        assert result.local_hash == hashlib.sha256(content).hexdigest()

    async def test_head_unsupported_falls_back(self, http_server):
        server, _ = http_server
        url = str(server.make_url("/no-head"))
        handler = HTTPHandler(make_config(url))
        files = await handler.list_files(url)
        assert len(files) == 1
        # No extension in the URL: extension inferred from Content-Type
        assert files[0].path == "no-head.txt"
        assert files[0].remote_hash is None

    async def test_glob_pattern_rejected(self):
        handler = HTTPHandler(make_config("https://host/docs/"))
        with pytest.raises(RemoteSyncError, match="glob"):
            await handler.list_files("https://host/docs/", "*.md")

    async def test_404_raises(self, http_server):
        server, _ = http_server
        url = str(server.make_url("/missing.md"))
        handler = HTTPHandler(make_config(url))
        with pytest.raises(RemoteSyncError, match="404"):
            await handler.list_files(url)
        with pytest.raises(RemoteSyncError, match="404"):
            await handler.download_file(url, Path("/tmp/never-written.md"))

    async def test_max_file_size_enforced_mid_stream(self, http_server, tmp_path):
        server, _ = http_server
        url = str(server.make_url("/huge.txt"))
        handler = HTTPHandler(make_config(url, max_file_size=64))
        with pytest.raises(RemoteSyncError, match="max_file_size"):
            await handler.download_file(url, tmp_path / "huge.txt")

    async def test_unreachable_host_raises(self, tmp_path):
        url = "http://127.0.0.1:59991/nope.md"
        handler = HTTPHandler(make_config(url, timeout=2))
        with pytest.raises(RemoteSyncError):
            await handler.list_files(url)


class TestS3Handler:
    def _handler_with_client(self, url, client, **overrides):
        handler = S3Handler(make_config(url, **overrides))
        handler._client = client
        return handler

    def _paginator(self, pages):
        paginator = mock.Mock()
        paginator.paginate.return_value = pages
        return paginator

    async def test_list_files_with_pattern(self):
        client = mock.Mock()
        client.get_paginator.return_value = self._paginator(
            [
                {
                    "Contents": [
                        {"Key": "docs/a.md", "Size": 10, "ETag": '"e1"'},
                        {"Key": "docs/skip.txt", "Size": 5, "ETag": '"e2"'},
                        {"Key": "docs/nested/b.md", "Size": 20, "ETag": '"e3"'},
                        {"Key": "docs/dir/", "Size": 0, "ETag": '"e4"'},
                    ]
                }
            ]
        )
        handler = self._handler_with_client("s3://bucket/docs/*.md", client)
        files = await handler.list_files("s3://bucket/docs/", "*.md")
        assert sorted(f.path for f in files) == ["a.md", "nested/b.md"]
        by_path = {f.path: f for f in files}
        assert by_path["a.md"].remote_hash == "etag:e1"
        assert by_path["a.md"].url == "s3://bucket/docs/a.md"
        client.get_paginator.return_value.paginate.assert_called_once_with(
            Bucket="bucket", Prefix="docs/"
        )

    async def test_download_file(self, tmp_path):
        client = mock.Mock()
        client.head_object.return_value = {"ContentLength": 5}

        def fake_download(bucket, key, dest):
            Path(dest).write_bytes(b"hello")

        client.download_file.side_effect = fake_download
        handler = self._handler_with_client("s3://bucket/docs/a.md", client)
        result = await handler.download_file("s3://bucket/docs/a.md", tmp_path / "a.md")
        assert result.size == 5
        assert (tmp_path / "a.md").read_bytes() == b"hello"

    async def test_download_size_limit(self, tmp_path):
        client = mock.Mock()
        client.head_object.return_value = {"ContentLength": 999999}
        handler = self._handler_with_client("s3://bucket/a.md", client, max_file_size=10)
        with pytest.raises(RemoteSyncError, match="max_file_size"):
            await handler.download_file("s3://bucket/a.md", tmp_path / "a.md")

    async def test_missing_bucket_raises(self):
        handler = S3Handler(make_config("s3://bucket/x"))
        with pytest.raises(RemoteSyncError, match="bucket"):
            await handler.list_files("s3:///prefix/")

    async def test_explicit_credentials_passed_to_client(self):
        config = make_config(
            "s3://bucket/docs/",
            auth={
                "type": "aws",
                "access_key": "AKIA123",
                "secret_key": "shhh",
                "region": "eu-west-1",
            },
        )
        handler = S3Handler(config)
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.s3.boto3"
        ) as boto3_mock:
            handler._get_client()
            boto3_mock.client.assert_called_once_with(
                "s3",
                aws_access_key_id="AKIA123",
                aws_secret_access_key="shhh",
                region_name="eu-west-1",
            )


class TestRsyncHandler:
    def test_supports_incremental(self):
        handler = RsyncHandler(make_config("rsync://server/docs/"))
        assert handler.supports_incremental()

    async def test_enumerating_methods_not_implemented(self):
        handler = RsyncHandler(make_config("rsync://server/docs/"))
        with pytest.raises(NotImplementedError):
            await handler.list_files("rsync://server/docs/")
        with pytest.raises(NotImplementedError):
            await handler.download_file("rsync://server/docs/a.md", Path("/tmp/a.md"))

    def test_build_command_daemon_url(self, tmp_path):
        handler = RsyncHandler(
            make_config("rsync://server/docs", include=["*.md"], exclude=["drafts/*"], timeout=30)
        )
        command, key_file = handler._build_command(
            "/usr/bin/rsync", "rsync://server/docs", tmp_path
        )
        assert key_file is None
        assert command[0] == "/usr/bin/rsync"
        assert "--delete" in command
        assert "--safe-links" in command
        assert "--timeout=30" in command
        assert "--include=*.md" in command
        assert "--exclude=*" in command  # include-mode drops everything else
        assert "--exclude=drafts/*" in command
        assert command[-2] == "rsync://server/docs/"
        assert command[-1] == str(tmp_path) + os.sep

    def test_build_command_ssh_with_key(self, tmp_path):
        handler = RsyncHandler(
            make_config(
                "rsync+ssh://deploy@server.example.com/knowledge/",
                auth={"type": "ssh_key", "key": "PRIVATE KEY MATERIAL"},
            )
        )
        command, key_file = handler._build_command(
            "/usr/bin/rsync", "rsync+ssh://deploy@server.example.com/knowledge/", tmp_path
        )
        try:
            assert key_file is not None
            mode = stat_module.S_IMODE(os.stat(key_file).st_mode)
            assert mode == 0o600
            assert Path(key_file).read_text(encoding="utf-8").startswith("PRIVATE KEY MATERIAL")
            ssh_index = command.index("-e")
            assert f"-i {key_file}" in command[ssh_index + 1]
            assert command[-2] == "deploy@server.example.com:/knowledge/"
        finally:
            os.remove(key_file)

    async def test_sync_tree_success_with_fake_rsync(self, tmp_path):
        fake_rsync = tmp_path / "fake-rsync"
        fake_rsync.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_rsync.chmod(0o755)
        handler = RsyncHandler(make_config("rsync://server/docs/"))
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.rsync.shutil.which",
            return_value=str(fake_rsync),
        ):
            await handler.sync_tree("rsync://server/docs/", tmp_path / "mirror")
        assert (tmp_path / "mirror").is_dir()

    async def test_sync_tree_failure_raises(self, tmp_path):
        fake_rsync = tmp_path / "fake-rsync"
        fake_rsync.write_text('#!/bin/sh\necho "connection refused" >&2\nexit 10\n', "utf-8")
        fake_rsync.chmod(0o755)
        handler = RsyncHandler(make_config("rsync://server/docs/"))
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.rsync.shutil.which",
            return_value=str(fake_rsync),
        ):
            with pytest.raises(RemoteSyncError, match="code 10"):
                await handler.sync_tree("rsync://server/docs/", tmp_path / "mirror")

    async def test_missing_rsync_binary(self, tmp_path):
        handler = RsyncHandler(make_config("rsync://server/docs/"))
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.rsync.shutil.which",
            return_value=None,
        ):
            with pytest.raises(RemoteSyncError, match="rsync binary"):
                await handler.sync_tree("rsync://server/docs/", tmp_path / "mirror")
