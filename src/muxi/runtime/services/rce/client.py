"""Async client for the Skills RCE (Remote Code Execution) service.

Wraps the Skills RCE HTTP API for uploading skill directories, running ad-hoc
code, and executing commands against cached skills. Designed to be created once
during formation init and shared across the runtime.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class RCEStatus:
    """Snapshot of the RCE server's capabilities, fetched once at init."""

    version: str
    languages: List[str]
    runtimes: List[Dict[str, Any]]
    resources: Dict[str, int]
    packages: Dict[str, List[Dict[str, str]]]
    cached_skills: List[str]
    uptime_seconds: int
    raw: Dict[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RCEStatus":
        return cls(
            version=data["version"],
            languages=data.get("languages", []),
            runtimes=data.get("runtimes", []),
            resources=data.get("resources", {}),
            packages=data.get("packages", {}),
            cached_skills=data.get("cached_skills", []),
            uptime_seconds=data.get("uptime_seconds", 0),
            raw=data,
        )


@dataclass
class ExecResult:
    """Result of a code execution or skill run."""

    id: str
    status: str  # "success", "error", "timeout"
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    artifacts: List[Dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.status == "success"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecResult":
        return cls(
            id=data.get("id", ""),
            status=data["status"],
            exit_code=data.get("exit_code", -1),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            duration_ms=data.get("duration_ms", 0),
            artifacts=data.get("artifacts") or [],
        )


class RCEError(Exception):
    """Raised when the RCE server returns an error."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class RCEClient:
    """Async HTTP client for the Skills RCE service.

    Usage::

        client = RCEClient(url="http://localhost:7891", token="optional")
        await client.connect()  # health check + status fetch
        result = await client.run("python", "print('hi')")
        await client.close()
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        timeout: float = 60.0,
        connect_timeout: float = 5.0,
    ):
        self._base_url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._status: Optional[RCEStatus] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def status(self) -> Optional[RCEStatus]:
        return self._status

    @property
    def languages(self) -> List[str]:
        return self._status.languages if self._status else []

    @property
    def url(self) -> str:
        return self._base_url

    def _build_client(self) -> httpx.AsyncClient:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=httpx.Timeout(self._timeout, connect=self._connect_timeout),
        )

    async def connect(self) -> RCEStatus:
        """Health check + fetch server status. Raises on failure."""
        self._client = self._build_client()
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            await self.close()
            raise RCEError(
                f"RCE server unreachable at {self._base_url}: {e}",
                status_code=getattr(e, "response", None) and e.response.status_code or 0,
            ) from e

        resp = await self._client.get("/status")
        resp.raise_for_status()
        self._status = RCEStatus.from_dict(resp.json())
        return self._status

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Ad-hoc execution
    # ------------------------------------------------------------------

    async def run(
        self,
        language: str,
        code: str,
        *,
        job_id: Optional[str] = None,
        files: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Run ad-hoc code (no skill context)."""
        payload: Dict[str, Any] = {
            "id": job_id or _generate_job_id(),
            "language": language,
            "code": code,
            "timeout": timeout,
        }
        if files:
            payload["files"] = files
        if env:
            payload["env"] = env

        data = await self._post("/run", payload)
        return ExecResult.from_dict(data)

    # ------------------------------------------------------------------
    # Skill cache management
    # ------------------------------------------------------------------

    async def check_skill(self, skill_id: str) -> Dict[str, Any]:
        """Check whether a skill is cached. Returns {name, cached, hash?, file_count?}."""
        resp = await self._get(f"/skill/{skill_id}")
        return resp

    async def upload_skill_zip(
        self, skill_id: str, skill_dir: Path, content_hash: str
    ) -> Dict[str, Any]:
        """Zip a skill directory and upload it."""
        buf = _zip_directory(skill_dir)
        self._ensure_connected()
        resp = await self._client.post(
            f"/skill/{skill_id}",
            params={"hash": content_hash},
            content=buf.getvalue(),
            headers={"Content-Type": "application/zip"},
        )
        if resp.status_code >= 400:
            raise RCEError(resp.json().get("error", resp.text), resp.status_code)
        return resp.json()

    async def delete_skill(self, skill_id: str) -> Dict[str, Any]:
        """Delete a cached skill."""
        self._ensure_connected()
        resp = await self._client.delete(f"/skill/{skill_id}")
        if resp.status_code == 404:
            raise RCEError(resp.json().get("error", "not cached"), 404)
        resp.raise_for_status()
        return resp.json()

    async def ensure_cached(
        self, skill_id: str, skill_dir: Path, content_hash: str
    ) -> bool:
        """Check cache, upload if stale. Returns True if upload was needed."""
        cache_status = await self.check_skill(skill_id)
        if cache_status.get("cached") and cache_status.get("hash") == content_hash:
            return False
        await self.upload_skill_zip(skill_id, skill_dir, content_hash)
        return True

    # ------------------------------------------------------------------
    # Skill execution
    # ------------------------------------------------------------------

    async def run_skill(
        self,
        skill_id: str,
        command: str,
        *,
        job_id: Optional[str] = None,
        input_files: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Run a command inside a cached skill directory."""
        payload: Dict[str, Any] = {
            "id": job_id or _generate_job_id(),
            "command": command,
            "timeout": timeout,
        }
        if input_files:
            import base64

            payload["input_files"] = {
                name: base64.b64encode(content.encode()).decode()
                if isinstance(content, str)
                else base64.b64encode(content).decode()
                for name, content in input_files.items()
            }
        if env:
            payload["env"] = env

        data = await self._post(f"/skill/{skill_id}/run", payload)
        return ExecResult.from_dict(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> Dict[str, Any]:
        self._ensure_connected()
        resp = await self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_connected()
        resp = await self._client.post(path, json=payload)
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise RCEError(
                body.get("error", f"HTTP {resp.status_code}"),
                resp.status_code,
            )
        return resp.json()

    def _ensure_connected(self) -> None:
        if not self._client:
            raise RCEError("RCE client not connected. Call connect() first.")


def _zip_directory(directory: Path) -> io.BytesIO:
    """Zip a directory into an in-memory buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(directory))
                zf.write(file_path, arcname)
    buf.seek(0)
    return buf


def _generate_job_id() -> str:
    from ...utils.id_generator import generate_nanoid
    return f"rce_{generate_nanoid()}"
