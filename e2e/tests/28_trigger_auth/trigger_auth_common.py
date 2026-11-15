"""
Shared helpers for the 28_trigger_auth e2e area (per-trigger auth).

Every test generates its formation at runtime into a temp directory (the
27_tuning pattern): triggers declare ``auth:`` against small stdlib auth
scripts written next to them, or against a local auth service the test
starts before the formation loads (the load checks the URL is reachable).

NOTE: the filename deliberately matches the runners' skip patterns
("common.py") so it is never collected as a test.
"""

import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from aiohttp import web  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402

AREA_DIR = Path(__file__).parent
ASSETS_DIR = AREA_DIR.parent.parent / "assets"

PORT = 18274
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
AUTH_SERVICE_PORT = 18298
ADMIN_KEY = "trigger-auth-admin-key-28"
CLIENT_KEY = "trigger-auth-client-key-28"

# The HMAC test script reads its signing secret from the runtime's
# environment, the way a real provider check gets its secret.
SIGNING_SECRET_ENV = "TRIGGER_AUTH_E2E_SECRET"

FORMATION_TEMPLATE = """\
schema: "1.0.0"
id: {formation_id}
description: E2E formation for per-trigger auth

llm:
  api_keys:
    openai: "${{{{ secrets.OPENAI_API_KEY }}}}"
  models:
    - text: "openai/gpt-4o-mini"

runtime:
  built_in_mcps: false

agents:
  - id: assistant
    name: Assistant
    description: Concise assistant for trigger testing
    system_message: |
      You are a test agent. Reply in one short sentence.
    default: true

overlord:
  workflow:
    auto_decomposition: false
  response:
    streaming: false
    widgets: false

logging:
  system:
    level: "warning"
    destination: "{system_log}"
  conversation:
    enabled: false

server:
  enabled: true
  port: {port}
  api_keys:
    admin_key: {admin_key}
    client_key: {client_key}
"""

ALLOW = "import sys\nsys.exit(0)\n"
DENY = "import sys\nsys.exit(1)\n"
SLOW = "import time\ntime.sleep(10)\n"
HMAC_CHECK = f"""\
import base64, hashlib, hmac, json, os, sys

request = json.load(sys.stdin)
body = base64.b64decode(request["body"])
expected = hmac.new(os.environ["{SIGNING_SECRET_ENV}"].encode(), body, hashlib.sha256).hexdigest()
received = request["headers"].get("x-test-signature", "")
sys.exit(0 if hmac.compare_digest(expected, received) else 1)
"""


def unique_formation_id(tag: str) -> str:
    return f"trigger-auth-e2e-{tag}-{uuid.uuid4().hex[:8]}"


def build_formation(
    base_dir: Path,
    formation_id: str,
    triggers: Dict[str, str],
    scripts: Optional[Dict[str, Tuple[str, bool]]] = None,
) -> Path:
    """
    Generate a formation under ``base_dir`` and return its path.

    ``triggers`` maps trigger name to file content; ``scripts`` maps a
    path under ``auth/`` to ``(python source, executable)``.
    """
    formation_dir = base_dir / "formation"
    (formation_dir / "triggers").mkdir(parents=True)
    (formation_dir / "formation.yaml").write_text(
        FORMATION_TEMPLATE.format(
            formation_id=formation_id,
            system_log=str(base_dir / "system.jsonl"),
            port=PORT,
            admin_key=ADMIN_KEY,
            client_key=CLIENT_KEY,
        )
    )
    for name, content in triggers.items():
        (formation_dir / "triggers" / f"{name}.md").write_text(content)
    for name, (source, executable) in (scripts or {}).items():
        path = formation_dir / "auth" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"#!{sys.executable}\n{source}")
        path.chmod(0o755 if executable else 0o644)

    # Shared e2e secrets: BOTH the blob and its key must resolve, or the
    # SecretsManager mints a fresh key that cannot decrypt the blob.
    os.symlink(ASSETS_DIR / "secrets.enc", formation_dir / "secrets.enc")
    os.symlink(ASSETS_DIR / ".key", formation_dir / ".key")
    return formation_dir


async def start_formation(formation_dir: Path):
    """Load the formation and start its HTTP server."""
    formation = Formation()
    await formation.load(str(formation_dir))
    server = await formation.start_server(block=False)
    await asyncio.sleep(2)
    return formation, server


async def teardown(formation, server, formation_id: str, tmp: Path) -> None:
    if server is not None:
        try:
            await server.stop()
        except Exception:
            pass
    if formation is not None:
        try:
            await formation.stop_overlord()
        except Exception:
            pass
    await asyncio.sleep(1)
    shutil.rmtree(Path.home() / ".muxi" / formation_id, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)


async def wait_for_completion(client, request_id: str, timeout: float = 60) -> dict:
    """Poll the request status (admin key) until the trigger run finishes."""
    deadline = time.time() + timeout
    data = {}
    while time.time() < deadline:
        response = await client.get(
            f"{BASE_URL}/requests/{request_id}", headers={"X-Muxi-Admin-Key": ADMIN_KEY}
        )
        if response.status_code == 200:
            data = response.json()["data"]
            if data["status"] in ("completed", "failed", "cancelled"):
                return data
        await asyncio.sleep(1)
    raise AssertionError(f"request {request_id} did not finish within {timeout}s: {data}")


def auth_failures(system_log: Path, trigger: str, timeout: float = 10) -> list:
    """The trigger-auth failure events written to the formation's system log."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = []
        if system_log.exists():
            for line in system_log.read_text().splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("event") == "error.authentication.failed" and (
                    event.get("data", {}).get("trigger") == trigger
                ):
                    events.append(event)
        if events:
            return events
        time.sleep(0.5)
    return []


class AuthService:
    """A local auth URL target: answers the status named in x-test-status."""

    def __init__(self):
        self.requests = []
        self.runner = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{AUTH_SERVICE_PORT}/check"

    async def _handle(self, request: web.Request) -> web.Response:
        if request.method != "POST":
            return web.Response(status=405)
        payload = await request.json()
        self.requests.append(payload)
        return web.Response(status=int(payload["headers"].get("x-test-status", "200")))

    async def start(self):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", AUTH_SERVICE_PORT).start()

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()


def print_result(summary: str, checks: list, transcript: list) -> None:
    print("\n" + "=" * 40)
    print("\n### Test Result:")
    print(f"  SUCCESS: {summary}")
    for check in checks:
        print(f"  - {check}")
    print("\n" + "=" * 40)
    print("\n### Chat transcript:")
    for request, reply in transcript:
        print(f"\nUser: {request}")
        print(f"System: {reply}")
