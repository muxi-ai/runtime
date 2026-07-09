# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Azure Handler - Remote Knowledge Sources
# Description:  Syncs knowledge files from Azure Blob Storage containers
# Role:         Protocol handler for az:// sources (PRD Phase 4)
# Usage:        Created by the protocol registry for az:// source URLs
# Author:       Muxi Framework Team
#
# Uses azure-storage-blob (optional dependency, `muxi-runtime[azure]`
# extra) dispatched to worker threads - the sync SDK must never block the
# event loop. Change detection uses the blob's Content-MD5 (ETag
# fallback).
#
# URL shape: az://<container>/<prefix-or-blob>. The storage ACCOUNT is
# not part of the URL - it comes from the required ``auth`` block
# (validated at config load time):
#   auth: {type: azure, connection_string: $AZ_CONN}
#   auth: {type: azure, account_name: acme, account_key: $AZ_KEY}
# =============================================================================

import asyncio
import posixpath
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse

from ..handler import (
    DownloadResult,
    ProtocolHandler,
    RemoteFile,
    RemoteSyncError,
    SourceConfig,
    atomic_download,
    hash_file_sha256,
    matches_pattern,
)

try:  # pragma: no cover - import guard mirrors the boto3 optional-dep pattern
    from azure.storage.blob import BlobServiceClient

    AZURE_AVAILABLE = True
except ImportError:  # pragma: no cover
    BlobServiceClient = None
    AZURE_AVAILABLE = False

_COPY_CHUNK = 65536


class AzureHandler(ProtocolHandler):
    """Protocol handler for az:// knowledge sources (Azure Blob Storage)."""

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        if not AZURE_AVAILABLE:
            raise RemoteSyncError(
                "az:// knowledge sources require the azure-storage-blob library. "
                "Install it with: pip install 'muxi-runtime[azure]' "
                "(or pip install azure-storage-blob)"
            )
        self._service_client: Optional[Any] = None

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        container, prefix = _parse_az_url(url)
        return await asyncio.to_thread(self._list_files_sync, container, prefix, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        container, blob_name = _parse_az_url(url)
        return await asyncio.to_thread(self._download_sync, container, blob_name, dest)

    async def get_file_hash(self, url: str) -> str:
        container, blob_name = _parse_az_url(url)
        return await asyncio.to_thread(self._head_hash_sync, container, blob_name)

    async def close(self) -> None:
        client, self._service_client = self._service_client, None
        if client is not None:
            try:
                await asyncio.to_thread(client.close)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _get_service_client(self) -> Any:
        if self._service_client is None:
            auth = self.config.auth or {}
            connection_string = auth.get("connection_string")
            if connection_string:
                self._service_client = BlobServiceClient.from_connection_string(connection_string)
            elif auth.get("account_name") and auth.get("account_key"):
                account_url = f"https://{auth['account_name']}.blob.core.windows.net"
                self._service_client = BlobServiceClient(
                    account_url=account_url, credential=auth["account_key"]
                )
            else:
                # Config validation requires the auth block, so this is a
                # defensive guard for programmatic misuse only.
                raise RemoteSyncError(
                    "az:// knowledge sources require auth with a connection_string "
                    "or account_name + account_key"
                )
        return self._service_client

    def _list_files_sync(
        self, container: str, prefix: str, pattern: Optional[str]
    ) -> List[RemoteFile]:
        client = self._get_service_client().get_container_client(container)
        results: List[RemoteFile] = []
        try:
            for blob in client.list_blobs(name_starts_with=prefix or None):
                name = blob.name
                if name.endswith("/"):
                    continue
                rel_path = name.removeprefix(prefix).lstrip("/") if prefix else name
                if not rel_path:
                    rel_path = posixpath.basename(name)
                if pattern and not matches_pattern(rel_path, pattern):
                    continue
                results.append(
                    RemoteFile(
                        path=rel_path,
                        url=f"az://{container}/{name}",
                        size=int(blob.size or 0),
                        remote_hash=_change_token(blob),
                    )
                )
        except Exception as e:
            raise RemoteSyncError(f"Failed to list az://{container}/{prefix}: {e}") from e
        return results

    def _download_sync(self, container: str, blob_name: str, dest: Path) -> DownloadResult:
        client = self._get_service_client().get_blob_client(container, blob_name)
        max_size = self.config.max_file_size
        # Stream into a temp file and atomically swap it in on success: a
        # mid-transfer failure must never truncate a previously synced
        # good copy (see atomic_download in handler.py).
        with atomic_download(dest) as tmp_path:
            try:
                properties = client.get_blob_properties()
                size = int(properties.size or 0)
                if size > max_size:
                    raise RemoteSyncError(
                        f"Remote file exceeds max_file_size "
                        f"({size} > {max_size}): az://{container}/{blob_name}"
                    )
                downloader = client.download_blob()
                written = 0
                with open(tmp_path, "wb") as f:
                    for chunk in downloader.chunks():
                        written += len(chunk)
                        if written > max_size:
                            raise RemoteSyncError(
                                f"Remote file exceeds max_file_size "
                                f"({written} > {max_size}): az://{container}/{blob_name}"
                            )
                        f.write(chunk)
            except RemoteSyncError:
                raise
            except Exception as e:
                raise RemoteSyncError(
                    f"Failed to download az://{container}/{blob_name}: {e}"
                ) from e
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=written,
            local_hash=hash_file_sha256(dest),
        )

    def _head_hash_sync(self, container: str, blob_name: str) -> str:
        client = self._get_service_client().get_blob_client(container, blob_name)
        try:
            properties = client.get_blob_properties()
        except Exception:
            return ""
        return _change_token(properties) or ""


def _parse_az_url(url: str) -> tuple:
    """Split az://container/blob-or-prefix into (container, blob)."""
    parsed = urlparse(url)
    container = parsed.netloc
    if not container:
        raise RemoteSyncError(f"az:// knowledge source URL is missing a container: {url}")
    return container, parsed.path.lstrip("/")


def _change_token(blob: Any) -> Optional[str]:
    """Content-MD5 change token with ETag fallback."""
    settings = getattr(blob, "content_settings", None)
    content_md5 = getattr(settings, "content_md5", None) if settings else None
    if content_md5:
        return f"md5:{bytes(content_md5).hex()}"
    etag = getattr(blob, "etag", None)
    if etag:
        return f"etag:{str(etag).strip(chr(34))}"
    return None
