"""
Per-trigger auth for webhook providers that cannot send the client key.

A trigger file may declare ``auth: <script path | http(s) URL>`` in its
frontmatter. The formation scans ``triggers/*.md`` once at load and keeps
``{trigger name: target}``; :class:`TriggerAuthMiddleware` sits in front of
the route stack and acts only on ``POST /v1/triggers/{name}`` for a name in
that map:

  - It reads the raw body and runs the trigger's check on it
    (:func:`call_trigger_auth`).
  - On pass it rewrites the request into what the existing route already
    accepts: the formation's client key, the body wrapped as
    ``{"data": ...}``, and no caller-sent ``X-Muxi-User-Id``.
  - On fail it changes nothing, so the unchanged client-key dependency
    rejects the request (no key) or admits it (the caller's own key).

A caller that already sends the real client key skips the check and keeps
today's path untouched (its ``{"data": ...}`` body, session and user).

The middleware never builds a response itself. Formations with no ``auth``
line never get the middleware at all.
"""

import asyncio
import base64
import json
import os
import secrets
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml
from starlette._utils import get_route_path
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ...services import observability
from ..background.transformers import _FRONTMATTER_PATTERN, _NAME_PATTERN

# Fixed: the check runs inline on the provider's request.
TRIGGER_AUTH_TIMEOUT_SECONDS = 2.0

# The trigger route as the router resolves it: the client routers' "/v1"
# prefix plus "/triggers/{trigger_name}" (a single path segment).
_TRIGGER_PATH_PREFIX = "/v1/triggers/"

# Replaced on a passed check; content-type/length/transfer-encoding describe
# the original body, which the wrapped JSON body replaces.
_REPLACED_HEADERS = {
    b"x-muxi-client-key",
    b"x-muxi-user-id",
    b"content-type",
    b"content-length",
    b"transfer-encoding",
}

_NOT_DECLARED = object()


class TriggerAuthConfigError(ValueError):
    """A trigger's ``auth`` value is unusable; the formation must not load."""


# ---------------------------------------------------------------------------
# Startup map
# ---------------------------------------------------------------------------


def _declared_auth(md_file: Path) -> Any:
    """
    Return the trigger's frontmatter ``auth`` value, or ``_NOT_DECLARED``.

    Reads only ``auth``: an unreadable file, invalid YAML, a non-mapping or
    any other frontmatter problem returns ``_NOT_DECLARED`` and stays a
    call-time error in the trigger route, exactly as before.
    """
    try:
        content = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _NOT_DECLARED
    if not content.startswith("---"):
        return _NOT_DECLARED
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        return _NOT_DECLARED
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return _NOT_DECLARED
    if not isinstance(meta, dict) or "auth" not in meta:
        return _NOT_DECLARED
    return meta["auth"]


def _resolve_target(value: Any, formation_dir: Path) -> str:
    """Return the script path or URL for an ``auth`` value, or raise ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("is neither a script path nor an http(s) URL")
    if value.startswith(("http://", "https://")):
        try:
            host = httpx.URL(value).host
        except Exception:
            host = ""
        if not host:
            raise ValueError("is not a valid http(s) URL")
        return value
    if "://" in value:
        raise ValueError("is neither a script path nor an http(s) URL")
    path = Path(value)
    if not path.is_absolute():
        path = formation_dir / path
    if not path.is_file():
        raise ValueError(f"script does not exist ({path})")
    if not os.access(path, os.X_OK):
        raise ValueError(f"script is not executable ({path})")
    return os.path.abspath(path)


async def _unreachable(url: str) -> Optional[str]:
    """Return why ``url`` gave no HTTP response, or None (any status is reachable)."""
    try:
        async with httpx.AsyncClient(timeout=TRIGGER_AUTH_TIMEOUT_SECONDS) as client:
            await asyncio.wait_for(client.head(url), TRIGGER_AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return "timeout"
    except Exception as e:
        return type(e).__name__
    return None


async def load_triggers_with_own_auth(formation_dir: Path) -> Dict[str, str]:
    """
    Build ``{trigger name: script path or URL}`` from ``triggers/*.md``.

    Raises:
        TriggerAuthConfigError: Naming each trigger and target whose script
            is missing or not executable, whose URL gives no HTTP response,
            or whose value is neither a path nor an http(s) URL.
    """
    triggers_dir = formation_dir / "triggers"
    if not triggers_dir.is_dir():
        return {}

    targets: Dict[str, str] = {}
    errors: List[str] = []
    for md_file in sorted(triggers_dir.glob("*.md")):
        value = _declared_auth(md_file)
        if value is _NOT_DECLARED:
            continue
        try:
            targets[md_file.stem] = _resolve_target(value, formation_dir)
        except ValueError as e:
            errors.append(f"trigger '{md_file.stem}' auth {value!r}: {e}")

    urls = {name: t for name, t in targets.items() if t.startswith(("http://", "https://"))}
    reasons = await asyncio.gather(*(_unreachable(url) for url in urls.values()))
    for (name, url), reason in zip(urls.items(), reasons):
        if reason is not None:
            errors.append(f"trigger '{name}' auth {url!r}: URL is not reachable ({reason})")

    if errors:
        raise TriggerAuthConfigError("; ".join(errors))
    return targets


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


def _auth_input(trigger: str, scope: Scope, body: bytes) -> bytes:
    """The JSON both target kinds receive."""
    headers: Dict[str, str] = {}
    for raw_name, raw_value in scope["headers"]:
        name, value = raw_name.decode("latin-1"), raw_value.decode("latin-1")
        headers[name] = f"{headers[name]}, {value}" if name in headers else value
    return json.dumps(
        {
            "trigger": trigger,
            "method": scope["method"],
            "url": str(Request(scope).url),
            "headers": headers,
            "body": base64.b64encode(body).decode("ascii"),
        }
    ).encode("utf-8")


async def _run_script(path: str, auth_input: bytes) -> Optional[Dict[str, Any]]:
    """Exec the script with the input on stdin; exit 0 passes."""
    # Its own process group, so a timeout also stops any helpers it started.
    process = await asyncio.create_subprocess_exec(
        path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        await process.communicate(auth_input)
    finally:
        if process.returncode is None:  # cancelled by the timeout
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
    if process.returncode == 0:
        return None
    return {"failure": "exit_code", "exit_code": process.returncode}


async def _post_url(url: str, auth_input: bytes) -> Optional[Dict[str, Any]]:
    """POST the input to the URL; a 2xx response passes."""
    async with httpx.AsyncClient(timeout=TRIGGER_AUTH_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url, content=auth_input, headers={"content-type": "application/json"}
        )
    if 200 <= response.status_code < 300:
        return None
    return {"failure": "http_status", "status_code": response.status_code}


async def call_trigger_auth(trigger: str, target: str, scope: Scope, body: bytes) -> bool:
    """
    Run the trigger's auth check on the request; True means pass.

    Fails closed: an error, the fixed timeout or an unreachable target is a
    fail. A fail is logged with the trigger name and the failure kind only,
    never headers or body.
    """
    is_url = target.startswith(("http://", "https://"))
    check = _post_url if is_url else _run_script
    try:
        failure = await asyncio.wait_for(
            check(target, _auth_input(trigger, scope, body)), TRIGGER_AUTH_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        failure = {"failure": "timeout"}
    except Exception as e:
        failure = {"failure": "error", "error_type": type(e).__name__}
    if failure is None:
        return True

    observability.observe(
        event_type=observability.ErrorEvents.AUTHENTICATION_FAILED,
        level=observability.EventLevel.WARNING,
        data={
            "service": "trigger_auth",
            "trigger": trigger,
            "target_kind": "url" if is_url else "script",
            **failure,
        },
        description=f"Trigger '{trigger}' auth check failed ({failure['failure']})",
    )
    return False


# ---------------------------------------------------------------------------
# The middleware
# ---------------------------------------------------------------------------


def _wrap_body(body: bytes) -> bytes:
    """A JSON object becomes ``data``; any other body becomes ``data.body`` text."""
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        data = {"body": body.decode("utf-8", errors="replace")}
    return json.dumps({"data": data}).encode("utf-8")


def _replay(message: Message, receive: Receive) -> Receive:
    """A receive that yields ``message`` once, then defers to the original."""
    pending = [message]

    async def replay() -> Message:
        if pending:
            return pending.pop()
        return await receive()

    return replay


class TriggerAuthMiddleware:
    """Run a mapped trigger's own auth check before the client-key check."""

    def __init__(self, app: ASGIApp, triggers_with_own_auth: Dict[str, str], client_key: str):
        self.app = app
        self.triggers_with_own_auth = triggers_with_own_auth
        self.client_key = client_key

    def _mapped_trigger(self, scope: Scope) -> Optional[str]:
        """The trigger name when this is POST /v1/triggers/{name} for a mapped name."""
        if scope["type"] != "http" or scope["method"] != "POST":
            return None
        path = get_route_path(scope)
        if not path.startswith(_TRIGGER_PATH_PREFIX):
            return None
        name = path[len(_TRIGGER_PATH_PREFIX) :]
        if not _NAME_PATTERN.fullmatch(name) or name not in self.triggers_with_own_auth:
            return None
        return name

    def _has_client_key(self, scope: Scope) -> bool:
        """Whether the caller already sends the formation's real client key."""
        # The first value, as the client-key dependency reads it.
        sent = next((v for k, v in scope["headers"] if k == b"x-muxi-client-key"), None)
        return (
            bool(self.client_key)
            and sent is not None
            and secrets.compare_digest(sent, self.client_key.encode("latin-1"))
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        name = self._mapped_trigger(scope)
        if name is None or self._has_client_key(scope):
            await self.app(scope, receive, send)
            return

        chunks: List[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away mid-body: hand the app the same message.
                await self.app(scope, _replay(message, receive), send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        if await call_trigger_auth(name, self.triggers_with_own_auth[name], scope, body):
            body = _wrap_body(body)
            headers = [(k, v) for k, v in scope["headers"] if k not in _REPLACED_HEADERS]
            headers += [
                (b"x-muxi-client-key", self.client_key.encode("latin-1")),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ]
            scope = {**scope, "headers": headers}

        request_message = {"type": "http.request", "body": body, "more_body": False}
        await self.app(scope, _replay(request_message, receive), send)
