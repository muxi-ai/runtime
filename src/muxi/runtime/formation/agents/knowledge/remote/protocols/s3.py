# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        S3 Handler - Remote Knowledge Sources
# Description:  Syncs knowledge files from AWS S3 buckets
# Role:         Protocol handler for s3:// sources
# Usage:        Created by the protocol registry for s3:// source URLs
# Author:       Muxi Framework Team
#
# Uses boto3 (already a core runtime dependency for the OneLLM Bedrock
# provider) dispatched to worker threads — boto3 is synchronous and must
# never block the event loop. Change detection uses S3 ETags.
#
# Auth: optional ``auth: {type: aws, access_key, secret_key, region}``
# block (values already secret-interpolated). Without it, boto3's default
# credential chain applies (env vars, instance profile, ...).
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

try:  # pragma: no cover - import guard mirrors the kafka optional-dep pattern
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover
    boto3 = None
    BotoCoreError = ClientError = Exception
    BOTO3_AVAILABLE = False


class S3Handler(ProtocolHandler):
    """Protocol handler for s3:// knowledge sources."""

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        if not BOTO3_AVAILABLE:
            raise RemoteSyncError(
                "s3:// knowledge sources require the boto3 library. "
                "Install it with: pip install boto3"
            )
        self._client: Optional[Any] = None

    async def list_files(self, url: str, pattern: Optional[str] = None) -> List[RemoteFile]:
        bucket, prefix = _parse_s3_url(url)
        return await asyncio.to_thread(self._list_files_sync, bucket, prefix, pattern)

    async def download_file(self, url: str, dest: Path) -> DownloadResult:
        bucket, key = _parse_s3_url(url)
        return await asyncio.to_thread(self._download_sync, bucket, key, dest)

    async def get_file_hash(self, url: str) -> str:
        bucket, key = _parse_s3_url(url)
        return await asyncio.to_thread(self._head_hash_sync, bucket, key)

    # ------------------------------------------------------------------
    # Internals (run in a worker thread)
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            auth = self.config.auth or {}
            kwargs = {}
            if (auth.get("type") or "").lower() == "aws":
                if auth.get("access_key") and auth.get("secret_key"):
                    kwargs["aws_access_key_id"] = auth["access_key"]
                    kwargs["aws_secret_access_key"] = auth["secret_key"]
                if auth.get("region"):
                    kwargs["region_name"] = auth["region"]
            self._client = boto3.client("s3", **kwargs)
        return self._client

    def _list_files_sync(
        self, bucket: str, prefix: str, pattern: Optional[str]
    ) -> List[RemoteFile]:
        client = self._get_client()
        results: List[RemoteFile] = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue  # zero-byte "directory" marker
                    rel_path = key.removeprefix(prefix).lstrip("/") if prefix else key
                    if not rel_path:
                        rel_path = posixpath.basename(key)
                    if pattern and not matches_pattern(rel_path, pattern):
                        continue
                    results.append(
                        RemoteFile(
                            path=rel_path,
                            url=f"s3://{bucket}/{key}",
                            size=int(obj.get("Size", 0)),
                            remote_hash=_etag_token(obj.get("ETag")),
                        )
                    )
        except (BotoCoreError, ClientError) as e:
            raise RemoteSyncError(f"Failed to list s3://{bucket}/{prefix}: {e}") from e
        return results

    def _download_sync(self, bucket: str, key: str, dest: Path) -> DownloadResult:
        client = self._get_client()
        # Download into a temp file and atomically swap it in on success:
        # a mid-transfer failure must never truncate a previously synced
        # good copy (see atomic_download in handler.py).
        with atomic_download(dest) as tmp_path:
            try:
                head = client.head_object(Bucket=bucket, Key=key)
                size = int(head.get("ContentLength", 0))
                if size > self.config.max_file_size:
                    raise RemoteSyncError(
                        f"Remote file exceeds max_file_size "
                        f"({size} > {self.config.max_file_size}): s3://{bucket}/{key}"
                    )
                client.download_file(bucket, key, str(tmp_path))
            except (BotoCoreError, ClientError) as e:
                raise RemoteSyncError(f"Failed to download s3://{bucket}/{key}: {e}") from e
        return DownloadResult(
            path=dest.name,
            local_path=dest,
            size=size,
            local_hash=hash_file_sha256(dest),
        )

    def _head_hash_sync(self, bucket: str, key: str) -> str:
        client = self._get_client()
        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError):
            return ""
        return _etag_token(head.get("ETag")) or ""


def _parse_s3_url(url: str) -> tuple:
    """Split s3://bucket/key-or-prefix into (bucket, key)."""
    parsed = urlparse(url)
    bucket = parsed.netloc
    if not bucket:
        raise RemoteSyncError(f"s3:// knowledge source URL is missing a bucket: {url}")
    return bucket, parsed.path.lstrip("/")


def _etag_token(etag: Optional[str]) -> Optional[str]:
    if not etag:
        return None
    return f"etag:{etag.strip(chr(34))}"
