"""Unit tests for per-trigger auth (trigger frontmatter ``auth:``).

Covers:
  - The startup map: what is mapped, what fails the load, and that any
    other frontmatter problem stays a call-time error
  - call_trigger_auth: script exit codes, URL statuses, the fixed timeout,
    the exact body bytes, and a fail log without header or body content
  - TriggerAuthMiddleware: path resolution, the rewrite on pass, the
    untouched request on fail
  - The production app: the client-key dependency rejects (401) before body
    validation (422), and a mapped trigger keeps today's 401 on a failed check
"""

import base64
import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import psutil
import pytest

from muxi.runtime.formation.background.transformers import parse_trigger_frontmatter
from muxi.runtime.formation.server.server import FormationServer
from muxi.runtime.formation.server.trigger_auth import (
    TriggerAuthConfigError,
    TriggerAuthMiddleware,
    call_trigger_auth,
    load_triggers_with_own_auth,
)
from muxi.runtime.services import observability

CLIENT_KEY = "client-key"
SECRET = "whsec_unit_test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _script(path: Path, body: str, executable: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o755 if executable else 0o644)
    return path


@pytest.fixture
def scripts(tmp_path):
    """Executable auth scripts: allow, deny, slow, and an HMAC check over the body."""
    return {
        "allow": str(_script(tmp_path / "auth" / "allow.py", "import sys; sys.exit(0)")),
        "deny": str(_script(tmp_path / "auth" / "deny.py", "import sys; sys.exit(1)")),
        "slow": str(_script(tmp_path / "auth" / "slow.py", "import time; time.sleep(10)")),
        "hmac": str(
            _script(
                tmp_path / "auth" / "hmac_check.py",
                "import base64, hashlib, hmac, json, os, sys\n"
                "req = json.load(sys.stdin)\n"
                "body = base64.b64decode(req['body'])\n"
                "want = hmac.new(os.environ['TRIGGER_AUTH_UNIT_SECRET'].encode(), body,"
                " hashlib.sha256).hexdigest()\n"
                "got = req['headers'].get('x-signature', '')\n"
                "sys.exit(0 if hmac.compare_digest(want, got) else 1)",
            )
        ),
    }


@pytest.fixture
def auth_url():
    """A real local auth service: answers the status named in x-test-status."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["content-length"])))
            received.append(payload)
            self.send_response(int(payload["headers"].get("x-test-status", "200")))
            self.send_header("content-length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(url=f"http://127.0.0.1:{server.server_port}/check", received=received)
    finally:
        server.shutdown()
        server.server_close()


def _closed_port_url() -> str:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}/check"


def _scope(path="/v1/triggers/stripe", method="POST", headers=None, root_path=""):
    return {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": root_path,
        "query_string": b"",
        "scheme": "http",
        "server": ("muxi", 80),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }


async def _through_middleware(target, scope, body, chunks=None):
    """Run a request through the middleware; return what the next app saw (or None)."""
    seen = {}

    async def next_app(scope, receive, send):
        seen["headers"] = {k.decode(): v.decode() for k, v in scope["headers"]}
        message = await receive()
        seen["body"] = message["body"]

    chunks = chunks or [body]
    pending = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive():
        return pending.pop(0)

    async def send(message):
        pass

    middleware = TriggerAuthMiddleware(next_app, {"stripe": target}, CLIENT_KEY)
    await middleware(scope, receive, send)
    return seen


class _CapturingLogger:
    """Minimal event sink capturing what observe() emits."""

    def __init__(self):
        self.events = []
        self._lock = threading.Lock()

    def should_emit(self, event_type, level):
        return True

    def emit_event(self, event_type=None, level=None, data=None, description=None, **kwargs):
        with self._lock:
            self.events.append(
                {
                    "event": getattr(event_type, "value", str(event_type)),
                    "data": data,
                    "description": description,
                }
            )
        return ""


@pytest.fixture
def captured_events():
    capturing = _CapturingLogger()
    previous = observability.get_runtime_event_logger()
    observability.set_runtime_event_logger(capturing)
    observability.enable()
    try:
        yield capturing
    finally:
        observability.disable()
        observability.set_runtime_event_logger(previous)


def _auth_failures(capturing, trigger):
    deadline = time.time() + 5
    while time.time() < deadline:
        with capturing._lock:
            found = [
                e
                for e in capturing.events
                if e["event"] == "error.authentication.failed"
                and (e["data"] or {}).get("trigger") == trigger
            ]
        if found:
            return found
        time.sleep(0.05)
    return []


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def test_auth_is_an_allowed_frontmatter_key():
    meta, body = parse_trigger_frontmatter("---\nauth: ./auth/stripe.py\n---\nHello")
    assert meta == {"auth": "./auth/stripe.py"}
    assert body == "Hello"


# ---------------------------------------------------------------------------
# Startup map
# ---------------------------------------------------------------------------


def _trigger(formation_dir: Path, name: str, content: str) -> None:
    (formation_dir / "triggers").mkdir(parents=True, exist_ok=True)
    (formation_dir / "triggers" / f"{name}.md").write_text(content)


async def test_no_triggers_dir_maps_nothing(tmp_path):
    assert await load_triggers_with_own_auth(tmp_path) == {}


async def test_map_holds_only_triggers_that_declare_auth(tmp_path, scripts, auth_url):
    _trigger(tmp_path, "plain", "Hello ${{ data.x }}")
    _trigger(tmp_path, "routed", "---\nmodel: openai/gpt-4o-mini\n---\nHello")
    _trigger(tmp_path, "stripe", "---\nauth: ./auth/allow.py\n---\nHello")
    _trigger(tmp_path, "remote", f"---\nauth: {auth_url.url}\n---\nHello")

    mapped = await load_triggers_with_own_auth(tmp_path)

    assert mapped == {"stripe": scripts["allow"], "remote": auth_url.url}


async def test_any_http_status_counts_as_reachable(tmp_path, auth_url):
    # The fixture answers HEAD with 404: still an HTTP response.
    _trigger(tmp_path, "remote", f"---\nauth: {auth_url.url}\n---\nHello")
    assert await load_triggers_with_own_auth(tmp_path) == {"remote": auth_url.url}


@pytest.mark.parametrize(
    "value, reason",
    [
        ("./auth/missing.py", "does not exist"),
        ("./auth/noexec.py", "not executable"),
        ("ftp://example.com/check", "neither a script path nor an http(s) URL"),
        ("42", "neither a script path nor an http(s) URL"),
        ('""', "neither a script path nor an http(s) URL"),
    ],
)
async def test_bad_auth_value_fails_the_load_naming_trigger_and_target(tmp_path, value, reason):
    _script(tmp_path / "auth" / "noexec.py", "pass", executable=False)
    _trigger(tmp_path, "stripe", f"---\nauth: {value}\n---\nHello")

    with pytest.raises(TriggerAuthConfigError) as exc:
        await load_triggers_with_own_auth(tmp_path)

    assert "trigger 'stripe'" in str(exc.value)
    assert reason in str(exc.value)


async def test_unreachable_url_fails_the_load_naming_trigger_and_target(tmp_path):
    url = _closed_port_url()
    _trigger(tmp_path, "remote", f"---\nauth: {url}\n---\nHello")

    with pytest.raises(TriggerAuthConfigError) as exc:
        await load_triggers_with_own_auth(tmp_path)

    assert "trigger 'remote'" in str(exc.value)
    assert url in str(exc.value)
    assert "not reachable" in str(exc.value)


@pytest.mark.parametrize(
    "content",
    [
        "---\nauth: [unclosed\n---\nHello",  # invalid YAML
        "---\nbogus: 1\n---\nHello",  # unknown key
        "---\n- a list\n---\nHello",  # not a mapping
    ],
)
async def test_other_frontmatter_problems_stay_call_time_errors(tmp_path, content):
    _trigger(tmp_path, "broken", content)

    assert await load_triggers_with_own_auth(tmp_path) == {}
    with pytest.raises(ValueError):
        parse_trigger_frontmatter(content)


async def test_scan_reads_only_auth_beside_an_unknown_key(tmp_path, scripts):
    _trigger(tmp_path, "stripe", "---\nauth: ./auth/allow.py\nbogus: 1\n---\nHello")
    assert await load_triggers_with_own_auth(tmp_path) == {"stripe": scripts["allow"]}


# ---------------------------------------------------------------------------
# call_trigger_auth
# ---------------------------------------------------------------------------


async def test_script_exit_zero_passes(scripts):
    assert await call_trigger_auth("stripe", scripts["allow"], _scope(), b"{}")


async def test_script_nonzero_exit_fails(scripts):
    assert not await call_trigger_auth("stripe", scripts["deny"], _scope(), b"{}")


async def test_script_over_two_seconds_fails(scripts):
    started = time.monotonic()
    assert not await call_trigger_auth("stripe", scripts["slow"], _scope(), b"{}")
    assert time.monotonic() - started < 4


async def test_timeout_stops_the_scripts_helpers_too(tmp_path):
    pid_file = tmp_path / "helper.pid"
    script = _script(
        tmp_path / "auth" / "spawns.py",
        "import subprocess, sys, time\n"
        f"helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(helper.pid))\n"
        "time.sleep(30)",
    )

    assert not await call_trigger_auth("stripe", str(script), _scope(), b"{}")

    # Running, not merely present: an unreaped zombie still has a pid.
    helper_pid = int(pid_file.read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            if psutil.Process(helper_pid).status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(0.1)
    else:
        psutil.Process(helper_pid).kill()
        pytest.fail("the timed-out script's helper process was left running")


async def test_script_receives_exact_body_bytes(scripts, monkeypatch):
    monkeypatch.setenv("TRIGGER_AUTH_UNIT_SECRET", SECRET)
    body = b'{"id": "evt_1",  "amount":\t100}\n'
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    assert await call_trigger_auth(
        "stripe", scripts["hmac"], _scope(headers={"X-Signature": signature}), body
    )
    assert not await call_trigger_auth(
        "stripe", scripts["hmac"], _scope(headers={"X-Signature": signature}), body + b" "
    )


async def test_url_input_is_the_documented_json(auth_url):
    body = b"a=1&b=2"
    scope = _scope(headers={"Content-Type": "application/x-www-form-urlencoded"})

    assert await call_trigger_auth("stripe", auth_url.url, scope, body)

    (received,) = auth_url.received
    assert received == {
        "trigger": "stripe",
        "method": "POST",
        "url": "http://muxi/v1/triggers/stripe",
        "headers": {"content-type": "application/x-www-form-urlencoded"},
        "body": base64.b64encode(body).decode(),
    }


@pytest.mark.parametrize("status, passed", [(200, True), (204, True), (403, False), (500, False)])
async def test_url_2xx_passes_anything_else_fails(auth_url, status, passed):
    scope = _scope(headers={"X-Test-Status": str(status)})
    assert await call_trigger_auth("stripe", auth_url.url, scope, b"{}") is passed


async def test_unreachable_url_fails():
    assert not await call_trigger_auth("stripe", _closed_port_url(), _scope(), b"{}")


async def test_fail_log_names_trigger_and_kind_without_headers_or_body(scripts, captured_events):
    scope = _scope(headers={"Stripe-Signature": "t=1,v1=SIGNATURE_VALUE"})
    assert not await call_trigger_auth("stripe", scripts["deny"], scope, b'{"BODY_VALUE": 1}')

    (event,) = _auth_failures(captured_events, "stripe")
    assert event["data"]["failure"] == "exit_code"
    assert event["data"]["exit_code"] == 1
    logged = json.dumps(event)
    for secret in ("SIGNATURE_VALUE", "stripe-signature", "BODY_VALUE"):
        assert secret not in logged


async def test_timeout_and_status_fail_kinds_are_logged(scripts, auth_url, captured_events):
    assert not await call_trigger_auth("slow-one", scripts["slow"], _scope(), b"{}")
    scope = _scope(headers={"X-Test-Status": "403"})
    assert not await call_trigger_auth("remote-one", auth_url.url, scope, b"{}")

    (timeout_event,) = _auth_failures(captured_events, "slow-one")
    (status_event,) = _auth_failures(captured_events, "remote-one")
    assert timeout_event["data"]["failure"] == "timeout"
    assert status_event["data"]["failure"] == "http_status"
    assert status_event["data"]["status_code"] == 403


STRIPE_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "contributing" / "templates" / "stripe_auth.py"
)


async def test_shipped_stripe_example_verifies_a_stripe_signature(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    body = b'{"id": "evt_1", "type": "charge.succeeded"}'
    timestamp = str(int(time.time()))
    signed = hmac.new(SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    header = f"t={timestamp},v1={signed.hexdigest()}"
    stale = f"t={int(timestamp) - 600},v1={signed.hexdigest()}"

    def check(signature):
        scope = _scope(headers={"Stripe-Signature": signature})
        return call_trigger_auth("stripe", str(STRIPE_TEMPLATE), scope, body)

    assert await check(header)
    assert not await check(stale)
    assert not await check(f"t={timestamp},v1={'0' * 64}")


# ---------------------------------------------------------------------------
# TriggerAuthMiddleware
# ---------------------------------------------------------------------------


async def test_pass_sets_key_wraps_json_and_drops_user_id(scripts):
    scope = _scope(
        headers={
            "Content-Type": "application/json",
            "X-Muxi-User-Id": "spoofed",
            "Stripe-Signature": "sig",
        }
    )
    seen = await _through_middleware(scripts["allow"], scope, b'{"type": "charge.succeeded"}')

    assert seen["headers"]["x-muxi-client-key"] == CLIENT_KEY
    assert "x-muxi-user-id" not in seen["headers"]
    assert seen["headers"]["stripe-signature"] == "sig"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["headers"]["content-length"] == str(len(seen["body"]))
    assert json.loads(seen["body"]) == {"data": {"type": "charge.succeeded"}}


@pytest.mark.parametrize(
    "body, data",
    [
        (b"payload=%7B%22a%22%3A1%7D&token=x", {"body": "payload=%7B%22a%22%3A1%7D&token=x"}),
        (b"", {"body": ""}),
        (b"[1, 2]", {"body": "[1, 2]"}),
    ],
)
async def test_pass_wraps_any_other_body_as_text(scripts, body, data):
    seen = await _through_middleware(scripts["allow"], _scope(), body)
    assert json.loads(seen["body"]) == {"data": data}


async def test_pass_reads_a_chunked_body_whole(scripts):
    seen = await _through_middleware(scripts["allow"], _scope(), None, chunks=[b'{"a": ', b"1}"])
    assert json.loads(seen["body"]) == {"data": {"a": 1}}


async def test_real_client_key_skips_the_check_and_keeps_todays_request(scripts):
    # Both checks would pass: the caller's own keyed request must not be rewrapped.
    headers = {"X-Muxi-Client-Key": CLIENT_KEY, "X-Muxi-User-Id": "u1"}
    body = b'{"data": {"message": "replayed"}, "session_id": "s1", "use_async": false}'
    seen = await _through_middleware(scripts["allow"], _scope(headers=headers), body)

    assert seen["headers"] == {"x-muxi-client-key": CLIENT_KEY, "x-muxi-user-id": "u1"}
    assert seen["body"] == body


async def test_fail_changes_nothing(scripts):
    headers = {"Content-Type": "application/json", "X-Muxi-User-Id": "u1"}
    body = b'{"type": "charge.succeeded"}'
    seen = await _through_middleware(scripts["deny"], _scope(headers=headers), body)

    assert seen["headers"] == {"content-type": "application/json", "x-muxi-user-id": "u1"}
    assert seen["body"] == body


@pytest.mark.parametrize(
    "scope",
    [
        _scope(method="GET"),
        _scope(path="/v1/triggers/stripe/"),  # the router redirects, never dispatches
        _scope(path="/v1/triggers/other"),
        _scope(path="/v1/triggers/stripe/extra"),
        _scope(path="/triggers/stripe"),
        _scope(path="/v1/chat"),
    ],
)
async def test_other_requests_pass_through_untouched(scripts, scope):
    seen = await _through_middleware(scripts["allow"], scope, b'{"x": 1}')
    assert "x-muxi-client-key" not in seen["headers"]
    assert seen["body"] == b'{"x": 1}'


async def test_path_resolves_as_the_router_does(scripts):
    # The server decodes percent-escapes into scope["path"]; root_path is stripped.
    seen = await _through_middleware(
        scripts["allow"], _scope(path="/base/v1/triggers/stripe", root_path="/base"), b"{}"
    )
    assert seen["headers"]["x-muxi-client-key"] == CLIENT_KEY


# ---------------------------------------------------------------------------
# The production app
# ---------------------------------------------------------------------------


def _formation(triggers_with_own_auth=None):
    formation = SimpleNamespace(formation_id="trigger-auth-test", is_overlord_running=lambda: False)
    if triggers_with_own_auth is not None:
        formation.triggers_with_own_auth = triggers_with_own_auth
    return formation


@pytest.fixture
def production_client():
    def start(formation):
        formation._api_keys = {"admin": "admin-key", "client": CLIENT_KEY}
        app = FormationServer(formation)._create_app()
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://muxi")

    return start


def _without_volatile(envelope):
    envelope = dict(envelope)
    envelope.pop("timestamp")
    envelope["request"] = {**envelope["request"], "id": None}
    return envelope


async def test_client_key_is_checked_before_body_validation(production_client):
    # The PRD's assumption: an unwrapped provider body with no key gets the
    # 401, not the 422 for the missing 'data' field.
    async with production_client(_formation()) as client:
        no_key = await client.post("/v1/triggers/stripe", json={"type": "charge.succeeded"})
        with_key = await client.post(
            "/v1/triggers/stripe",
            json={"type": "charge.succeeded"},
            headers={"X-Muxi-Client-Key": CLIENT_KEY},
        )

    assert no_key.status_code == 401
    assert with_key.status_code == 422


async def test_failed_check_returns_todays_401_envelope(production_client, scripts):
    async with production_client(_formation()) as client:
        today = await client.post("/v1/triggers/stripe", json={"type": "charge.succeeded"})
    async with production_client(_formation({"stripe": scripts["deny"]})) as client:
        mapped = await client.post("/v1/triggers/stripe", json={"type": "charge.succeeded"})

    assert mapped.status_code == today.status_code == 401
    assert mapped.headers.get("www-authenticate") == today.headers.get("www-authenticate")
    assert _without_volatile(mapped.json()) == _without_volatile(today.json())


async def test_passed_check_reaches_the_handler(production_client, scripts):
    # The stand-in formation has no overlord: reaching the handler's 503 means
    # the request passed the client-key dependency and body validation.
    async with production_client(_formation({"stripe": scripts["allow"]})) as client:
        response = await client.post("/v1/triggers/stripe", json={"type": "charge.succeeded"})
    assert response.status_code == 503


async def test_mapped_trigger_still_admits_the_real_key(production_client, scripts):
    async with production_client(_formation({"stripe": scripts["deny"]})) as client:
        response = await client.post(
            "/v1/triggers/stripe",
            json={"data": {"replayed": True}},
            headers={"X-Muxi-Client-Key": CLIENT_KEY},
        )
    assert response.status_code == 503


async def test_get_on_a_mapped_trigger_still_requires_the_key(production_client, scripts):
    async with production_client(_formation({"stripe": scripts["allow"]})) as client:
        response = await client.get("/v1/triggers/stripe")
    assert response.status_code == 401


async def test_no_auth_trigger_still_requires_the_key(production_client, scripts):
    async with production_client(_formation({"stripe": scripts["allow"]})) as client:
        response = await client.post("/v1/triggers/plain", json={"data": {}})
    assert response.status_code == 401


def test_formation_without_auth_gets_no_middleware():
    formation = _formation({})
    formation._api_keys = {"admin": "admin-key", "client": CLIENT_KEY}
    app = FormationServer(formation)._create_app()
    assert all(m.cls is not TriggerAuthMiddleware for m in app.user_middleware)
