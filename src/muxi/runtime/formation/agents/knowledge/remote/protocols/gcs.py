# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        GCS Handler - Remote Knowledge Sources
# Description:  Syncs knowledge files from Google Cloud Storage buckets
# Role:         Protocol handler for gs:// sources (PRD Phase 4)
# Usage:        Created by the protocol registry for gs:// source URLs
# Author:       Muxi Framework Team
#
# Uses google-cloud-storage (a transitive dependency of the core
# google-cloud-aiplatform requirement, and available standalone via the
# `muxi-runtime[gcs]` extra) dispatched to worker threads - the SDK is
# synchronous and must never block the event loop. Change detection uses
# the blob's Content-MD5.
#
# Auth: optional ``auth: {type: gcp, credentials_json: <service account
# JSON>}`` block (already secret-interpolated). Without it, Google's
# Application Default Credentials chain applies (env var, metadata
# server, gcloud login).
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
    from google.cloud import storage as gcs_storage

    GCS_AVAILABLE = True
except ImportError:  # pragma: no cover
    gcs_storage = None
    GCS_AVAILABLE = False


class GCSHandler(ProtocolHandler):
    """Protocol handler for gs:// knowledge sources."""

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        if not GCS_AVAILABLE:
            raise RemoteSyncError(
                "gs:// knowledge sources require the google-cloud-storage library. "
                "Install it with: pip install 'muxi-runtime[gcs]' "
                "(or pip install google-cloud-storage)"
            )
        self._client: Optional[Any] = None

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        bucket, prefix = _parse_gs_url(url)
        return await asyncio.to_thread(self._list_files_sync, bucket, prefix, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        bucket, key = _parse_gs_url(url)
        return await asyncio.to_thread(self._download_sync, bucket, key, dest)

    async def get_file_hash(self, url: str) -> str:
        bucket, key = _parse_gs_url(url)
        return await asyncio.to_thread(self._head_hash_sync, bucket, key)

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            auth = self.config.auth or {}
            credentials_json = auth.get("credentials_json")
            if (auth.get("type") or "").lower() == "gcp" and credentials_json:
                import json

                from google.oauth2 import service_account

                info = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(info)
                self._client = gcs_storage.Client(
                    credentials=credentials, project=info.get("project_id")
                )
            else:
                # Application Default Credentials chain
                self._client = gcs_storage.Client()
        return self._client

    def _list_files_sync(
        self, bucket: str, prefix: str, pattern: Optional[str]
    ) -> List[RemoteFile]:
        client = self._get_client()
        results: List[RemoteFile] = []
        try:
            for blob in client.list_blobs(bucket, prefix=prefix or None):
                name = blob.name
                if name.endswith("/"):
                    continue  # zero-byte "directory" marker
                rel_path = name.removeprefix(prefix).lstrip("/") if prefix else name
                if not rel_path:
                    rel_path = posixpath.basename(name)
                if pattern and not matches_pattern(rel_path, pattern):
                    continue
                results.append(
                    RemoteFile(
                        path=rel_path,
                        url=f"gs://{bucket}/{name}",
                        size=int(blob.size or 0),
                        remote_hash=_md5_token(blob.md5_hash) or _etag_token(blob.etag),
                    )
                )
        except Exception as e:
            raise RemoteSyncError(f"Failed to list gs://{bucket}/{prefix}: {e}") from e
        return results

    def _download_sync(self, bucket: str, key: str, dest: Path) -> DownloadResult:
        client = self._get_client()
        # Download into a temp file and atomically swap it in on success:
        # a mid-transfer failure must never truncate a previously synced
        # good copy (see atomic_download in handler.py).
        with atomic_download(dest) as tmp_path:
            try:
                blob = client.bucket(bucket).blob(key)
                blob.reload()
                size = int(blob.size or 0)
                if size > self.config.max_file_size:
                    raise RemoteSyncError(
                        f"Remote file exceeds max_file_size "
                        f"({size} > {self.config.max_file_size}): gs://{bucket}/{key}"
                    )
                blob.download_to_filename(str(tmp_path))
            except RemoteSyncError:
                raise
            except Exception as e:
                raise RemoteSyncError(f"Failed to download gs://{bucket}/{key}: {e}") from e
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=size,
            local_hash=hash_file_sha256(dest),
        )

    def _head_hash_sync(self, bucket: str, key: str) -> str:
        client = self._get_client()
        try:
            blob = client.bucket(bucket).blob(key)
            blob.reload()
        except Exception:
            return ""
        return _md5_token(blob.md5_hash) or _etag_token(blob.etag) or ""


def _parse_gs_url(url: str) -> tuple:
    """Split gs://bucket/key-or-prefix into (bucket, key)."""
    parsed = urlparse(url)
    bucket = parsed.netloc
    if not bucket:
        raise RemoteSyncError(f"gs:// knowledge source URL is missing a bucket: {url}")
    return bucket, parsed.path.lstrip("/")


def _md5_token(md5_hash: Optional[str]) -> Optional[str]:
    return f"md5:{md5_hash}" if md5_hash else None


def _etag_token(etag: Optional[str]) -> Optional[str]:
    return f"etag:{etag.strip(chr(34))}" if etag else None
