"""Unit tests for the Phase 4 remote knowledge protocol handlers.

GCS/Azure/FTP/SFTP handlers are exercised against mocked SDK clients (no
cloud/FTP/SSH infrastructure required), plus scheme auto-detection and
the clear config-time errors for missing optional dependencies.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from muxi.runtime.formation.agents.knowledge.remote.handler import (
    RemoteSyncError,
    SourceConfig,
)
from muxi.runtime.formation.agents.knowledge.remote.protocols import (
    SUPPORTED_SCHEMES,
    azure as azure_module,
    create_handler,
    gcs as gcs_module,
    sftp as sftp_module,
)
from muxi.runtime.formation.agents.knowledge.remote.protocols.azure import AzureHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.ftp import FTPHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.gcs import GCSHandler
from muxi.runtime.formation.agents.knowledge.remote.protocols.sftp import SFTPHandler

AZURE_AUTH = {"type": "azure", "connection_string": "UseDevelopmentStorage=true"}


def make_config(url, **overrides):
    return SourceConfig.from_dict({"url": url, **overrides})


class TestAutoDetection:
    def test_phase4_schemes_supported(self):
        assert {"gs", "az", "ftp", "sftp"} <= SUPPORTED_SCHEMES

    def test_ftp_dispatch(self):
        assert isinstance(create_handler(make_config("ftp://host/docs/")), FTPHandler)

    @pytest.mark.skipif(not gcs_module.GCS_AVAILABLE, reason="google-cloud-storage not installed")
    def test_gs_dispatch(self):
        assert isinstance(create_handler(make_config("gs://bucket/docs/*")), GCSHandler)

    @pytest.mark.skipif(not azure_module.AZURE_AVAILABLE, reason="azure-storage-blob not installed")
    def test_az_dispatch(self):
        assert isinstance(
            create_handler(make_config("az://container/docs/*", auth=AZURE_AUTH)), AzureHandler
        )

    @pytest.mark.skipif(not sftp_module.PARAMIKO_AVAILABLE, reason="paramiko not installed")
    def test_sftp_dispatch(self):
        assert isinstance(create_handler(make_config("sftp://user@host/docs/")), SFTPHandler)


class TestOptionalDependencyErrors:
    """Missing optional SDKs must fail with a clear, actionable error."""

    def test_gcs_missing_dependency_error(self):
        with mock.patch.object(gcs_module, "GCS_AVAILABLE", False):
            with pytest.raises(RemoteSyncError, match=r"muxi-runtime\[gcs\]"):
                GCSHandler(make_config("gs://bucket/x"))

    def test_azure_missing_dependency_error(self):
        with mock.patch.object(azure_module, "AZURE_AVAILABLE", False):
            with pytest.raises(RemoteSyncError, match=r"muxi-runtime\[azure\]"):
                AzureHandler(make_config("az://container/x", auth=AZURE_AUTH))

    def test_sftp_missing_dependency_error(self):
        with mock.patch.object(sftp_module, "PARAMIKO_AVAILABLE", False):
            with pytest.raises(RemoteSyncError, match=r"muxi-runtime\[sftp\]"):
                SFTPHandler(make_config("sftp://user@host/x"))


@pytest.mark.skipif(not gcs_module.GCS_AVAILABLE, reason="google-cloud-storage not installed")
class TestGCSHandler:
    def _handler_with_client(self, url, client, **overrides):
        handler = GCSHandler(make_config(url, **overrides))
        handler._client = client
        return handler

    def _blob(self, name, size=0, md5="bWQ1", etag='"e"'):
        return SimpleNamespace(name=name, size=size, md5_hash=md5, etag=etag)

    async def test_list_files_with_pattern(self):
        client = mock.Mock()
        client.list_blobs.return_value = [
            self._blob("docs/a.md", 10, md5="aaa"),
            self._blob("docs/skip.txt", 5),
            self._blob("docs/nested/b.md", 20, md5="bbb"),
            self._blob("docs/dir/", 0),
        ]
        handler = self._handler_with_client("gs://bucket/docs/*.md", client)
        files = await handler.list_files("gs://bucket/docs/", "*.md")
        assert sorted(f.path for f in files) == ["a.md", "nested/b.md"]
        by_path = {f.path: f for f in files}
        assert by_path["a.md"].remote_hash == "md5:aaa"
        assert by_path["a.md"].url == "gs://bucket/docs/a.md"
        client.list_blobs.assert_called_once_with("bucket", prefix="docs/")

    async def test_download_file(self, tmp_path):
        blob = mock.Mock()
        blob.size = 5

        def fake_download(dest):
            Path(dest).write_bytes(b"hello")

        blob.download_to_filename.side_effect = fake_download
        blob.reload.return_value = None
        client = mock.Mock()
        client.bucket.return_value.blob.return_value = blob

        handler = self._handler_with_client("gs://bucket/docs/a.md", client)
        result = await handler.download_file("gs://bucket/docs/a.md", tmp_path / "a.md")
        assert result.size == 5
        assert (tmp_path / "a.md").read_bytes() == b"hello"
        assert result.local_hash == hashlib.sha256(b"hello").hexdigest()

    async def test_download_size_limit(self, tmp_path):
        blob = mock.Mock()
        blob.size = 999999
        blob.reload.return_value = None
        client = mock.Mock()
        client.bucket.return_value.blob.return_value = blob
        handler = self._handler_with_client("gs://bucket/a.md", client, max_file_size=10)
        with pytest.raises(RemoteSyncError, match="max_file_size"):
            await handler.download_file("gs://bucket/a.md", tmp_path / "a.md")

    async def test_mid_transfer_failure_leaves_previous_file_intact(self, tmp_path):
        dest = tmp_path / "a.md"
        dest.write_bytes(b"previous good content")

        blob = mock.Mock()
        blob.size = 5
        blob.reload.return_value = None

        def partial_then_fail(path):
            Path(path).write_bytes(b"trunc")
            raise IOError("connection reset")

        blob.download_to_filename.side_effect = partial_then_fail
        client = mock.Mock()
        client.bucket.return_value.blob.return_value = blob
        handler = self._handler_with_client("gs://bucket/a.md", client)
        with pytest.raises(RemoteSyncError):
            await handler.download_file("gs://bucket/a.md", dest)
        assert dest.read_bytes() == b"previous good content"
        assert not list(tmp_path.glob("*.part")), "temp download file leaked"

    async def test_missing_bucket_raises(self):
        handler = GCSHandler(make_config("gs://bucket/x"))
        with pytest.raises(RemoteSyncError, match="bucket"):
            await handler.list_files("gs:///prefix/")


@pytest.mark.skipif(not azure_module.AZURE_AVAILABLE, reason="azure-storage-blob not installed")
class TestAzureHandler:
    def _handler_with_client(self, url, service_client, **overrides):
        handler = AzureHandler(make_config(url, auth=AZURE_AUTH, **overrides))
        handler._service_client = service_client
        return handler

    def _blob(self, name, size=0, content_md5=b"\x01\x02", etag='"e1"'):
        return SimpleNamespace(
            name=name,
            size=size,
            etag=etag,
            content_settings=SimpleNamespace(content_md5=content_md5),
        )

    async def test_list_files_with_pattern(self):
        container_client = mock.Mock()
        container_client.list_blobs.return_value = [
            self._blob("docs/a.md", 10),
            self._blob("docs/skip.txt", 5),
        ]
        service_client = mock.Mock()
        service_client.get_container_client.return_value = container_client
        handler = self._handler_with_client("az://container/docs/*.md", service_client)
        files = await handler.list_files("az://container/docs/", "*.md")
        assert [f.path for f in files] == ["a.md"]
        assert files[0].remote_hash == "md5:0102"
        assert files[0].url == "az://container/docs/a.md"
        container_client.list_blobs.assert_called_once_with(name_starts_with="docs/")

    async def test_download_file_streams_chunks(self, tmp_path):
        blob_client = mock.Mock()
        blob_client.get_blob_properties.return_value = SimpleNamespace(
            size=10, etag='"e"', content_settings=None
        )
        downloader = mock.Mock()
        downloader.chunks.return_value = iter([b"hello", b"world"])
        blob_client.download_blob.return_value = downloader
        service_client = mock.Mock()
        service_client.get_blob_client.return_value = blob_client

        handler = self._handler_with_client("az://container/a.md", service_client)
        result = await handler.download_file("az://container/a.md", tmp_path / "a.md")
        assert result.size == 10
        assert (tmp_path / "a.md").read_bytes() == b"helloworld"

    async def test_download_size_limit_mid_stream(self, tmp_path):
        blob_client = mock.Mock()
        blob_client.get_blob_properties.return_value = SimpleNamespace(
            size=5, etag='"e"', content_settings=None
        )
        downloader = mock.Mock()
        downloader.chunks.return_value = iter([b"x" * 64, b"y" * 64])
        blob_client.download_blob.return_value = downloader
        service_client = mock.Mock()
        service_client.get_blob_client.return_value = blob_client

        dest = tmp_path / "a.md"
        dest.write_bytes(b"previous good content")
        handler = self._handler_with_client(
            "az://container/a.md", service_client, max_file_size=100
        )
        with pytest.raises(RemoteSyncError, match="max_file_size"):
            await handler.download_file("az://container/a.md", dest)
        assert dest.read_bytes() == b"previous good content"
        assert not list(tmp_path.glob("*.part")), "temp download file leaked"

    async def test_missing_container_raises(self):
        handler = AzureHandler(make_config("az://container/x", auth=AZURE_AUTH))
        with pytest.raises(RemoteSyncError, match="container"):
            await handler.list_files("az:///prefix/")


class TestFTPHandler:
    def _handler(self, url="ftp://files.corp/docs/", **overrides):
        return FTPHandler(make_config(url, **overrides))

    def _mock_ftp(self, mlsd_tree, files):
        """mlsd_tree: dir -> [(name, facts)], files: path -> bytes."""
        ftp = mock.Mock()

        def mlsd(directory, facts=None):
            if directory in mlsd_tree:
                return list(mlsd_tree[directory])
            import ftplib

            raise ftplib.error_perm("550 not a directory")

        def size(path):
            if path in files:
                return len(files[path])
            import ftplib

            raise ftplib.error_perm("550 not a file")

        def retrbinary(cmd, callback):
            path = cmd.removeprefix("RETR ")
            callback(files[path])

        ftp.mlsd.side_effect = mlsd
        ftp.size.side_effect = size
        ftp.retrbinary.side_effect = retrbinary
        ftp.voidcmd.return_value = "213 20260709100000"
        return ftp

    async def test_list_directory_recursive_with_pattern(self):
        tree = {
            "/docs": [
                ("a.md", {"type": "file", "size": "5", "modify": "20260709100000"}),
                ("skip.txt", {"type": "file", "size": "4", "modify": "20260709100000"}),
                ("nested", {"type": "dir"}),
                (".", {"type": "cdir"}),
            ],
            "/docs/nested": [
                ("b.md", {"type": "file", "size": "4", "modify": "20260709110000"}),
            ],
        }
        ftp = self._mock_ftp(tree, {})
        handler = self._handler()
        with mock.patch.object(handler, "_connect", return_value=ftp):
            files = await handler.list_files("ftp://files.corp/docs/", "*.md")
        assert sorted(f.path for f in files) == ["a.md", "nested/b.md"]
        by_path = {f.path: f for f in files}
        assert by_path["a.md"].size == 5
        assert by_path["a.md"].remote_hash == "stat:5:20260709100000"
        assert by_path["nested/b.md"].url == "ftp://files.corp/docs/nested/b.md"

    async def test_single_file_source(self):
        ftp = self._mock_ftp({}, {"/docs/guide.md": b"hello"})
        handler = self._handler("ftp://files.corp/docs/guide.md")
        with mock.patch.object(handler, "_connect", return_value=ftp):
            files = await handler.list_files("ftp://files.corp/docs/guide.md")
        assert [f.path for f in files] == ["guide.md"]
        assert files[0].size == 5

    async def test_download_file(self, tmp_path):
        ftp = self._mock_ftp({}, {"/docs/a.md": b"hello"})
        handler = self._handler()
        with mock.patch.object(handler, "_connect", return_value=ftp):
            result = await handler.download_file("ftp://files.corp/docs/a.md", tmp_path / "a.md")
        assert result.size == 5
        assert (tmp_path / "a.md").read_bytes() == b"hello"
        assert result.local_hash == hashlib.sha256(b"hello").hexdigest()

    async def test_download_size_limit_mid_stream(self, tmp_path):
        ftp = self._mock_ftp({}, {"/docs/big.md": b"x" * 4096})
        handler = self._handler(max_file_size=64)
        dest = tmp_path / "big.md"
        dest.write_bytes(b"previous good content")
        with mock.patch.object(handler, "_connect", return_value=ftp):
            with pytest.raises(RemoteSyncError, match="max_file_size"):
                await handler.download_file("ftp://files.corp/docs/big.md", dest)
        assert dest.read_bytes() == b"previous good content"
        assert not list(tmp_path.glob("*.part")), "temp download file leaked"

    async def test_missing_host_raises(self):
        handler = self._handler()
        with pytest.raises(RemoteSyncError, match="host"):
            await handler.list_files("ftp:///docs/")

    async def test_auth_credentials_used_for_login(self):
        handler = self._handler(auth={"type": "basic", "username": "u", "password": "p"})
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.ftp.ftplib.FTP"
        ) as ftp_class:
            handler._connect(
                __import__("urllib.parse", fromlist=["urlparse"]).urlparse("ftp://files.corp/docs/")
            )
            ftp_class.return_value.login.assert_called_once_with("u", "p")


@pytest.mark.skipif(not sftp_module.PARAMIKO_AVAILABLE, reason="paramiko not installed")
class TestSFTPHandler:
    def _handler(self, url="sftp://user@host/docs/", **overrides):
        return SFTPHandler(make_config(url, **overrides))

    @staticmethod
    def _attrs(filename, mode, size=0, mtime=1751970000):
        return SimpleNamespace(filename=filename, st_mode=mode, st_size=size, st_mtime=mtime)

    def _mock_sftp(self, listings, stats, files=None):
        sftp = mock.Mock()
        sftp.listdir_attr.side_effect = lambda d: listings[d]
        sftp.stat.side_effect = lambda p: stats[p]

        def get(path, dest):
            Path(dest).write_bytes((files or {})[path])

        sftp.get.side_effect = get
        return sftp

    async def test_list_directory_skips_symlinks(self):
        import stat as stat_module

        listings = {
            "/docs": [
                self._attrs("a.md", stat_module.S_IFREG | 0o644, size=5),
                self._attrs("link.md", stat_module.S_IFLNK | 0o777, size=5),
                self._attrs("nested", stat_module.S_IFDIR | 0o755),
            ],
            "/docs/nested": [
                self._attrs("b.md", stat_module.S_IFREG | 0o644, size=4),
            ],
        }
        stats = {"/docs": self._attrs("docs", stat_module.S_IFDIR | 0o755)}
        sftp = self._mock_sftp(listings, stats)
        handler = self._handler()
        with mock.patch.object(handler, "_connect", return_value=(mock.Mock(), sftp)):
            files = await handler.list_files("sftp://user@host/docs/")
        assert sorted(f.path for f in files) == ["a.md", "nested/b.md"]
        by_path = {f.path: f for f in files}
        assert by_path["a.md"].remote_hash == "stat:5:1751970000"
        assert by_path["nested/b.md"].url == "sftp://user@host/docs/nested/b.md"

    async def test_download_file(self, tmp_path):
        import stat as stat_module

        stats = {"/docs/a.md": self._attrs("a.md", stat_module.S_IFREG | 0o644, size=5)}
        sftp = self._mock_sftp({}, stats, files={"/docs/a.md": b"hello"})
        handler = self._handler()
        with mock.patch.object(handler, "_connect", return_value=(mock.Mock(), sftp)):
            result = await handler.download_file("sftp://user@host/docs/a.md", tmp_path / "a.md")
        assert result.size == 5
        assert (tmp_path / "a.md").read_bytes() == b"hello"

    async def test_download_size_limit(self, tmp_path):
        import stat as stat_module

        stats = {"/docs/big.md": self._attrs("big.md", stat_module.S_IFREG | 0o644, size=9999)}
        sftp = self._mock_sftp({}, stats)
        handler = self._handler(max_file_size=10)
        with mock.patch.object(handler, "_connect", return_value=(mock.Mock(), sftp)):
            with pytest.raises(RemoteSyncError, match="max_file_size"):
                await handler.download_file("sftp://user@host/docs/big.md", tmp_path / "big.md")

    def test_host_key_policy_strict_by_default(self):
        import paramiko

        handler = self._handler()
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.sftp.paramiko.SSHClient"
        ) as client_class:
            client = client_class.return_value
            client.connect.side_effect = paramiko.SSHException("stop here")
            from urllib.parse import urlparse

            with pytest.raises(RemoteSyncError):
                handler._connect(urlparse("sftp://user@host/docs/"))
            policy = client.set_missing_host_key_policy.call_args[0][0]
            assert isinstance(policy, paramiko.RejectPolicy)

    def test_host_key_tofu_requires_explicit_opt_in(self):
        import paramiko

        handler = self._handler(accept_new_host_keys=True)
        with mock.patch(
            "muxi.runtime.formation.agents.knowledge.remote.protocols.sftp.paramiko.SSHClient"
        ) as client_class:
            client = client_class.return_value
            client.connect.side_effect = paramiko.SSHException("stop here")
            from urllib.parse import urlparse

            with pytest.raises(RemoteSyncError):
                handler._connect(urlparse("sftp://user@host/docs/"))
            policy = client.set_missing_host_key_policy.call_args[0][0]
            assert isinstance(policy, paramiko.AutoAddPolicy)
