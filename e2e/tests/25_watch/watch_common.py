"""
Shared helpers for the 25_watch e2e area (remote async tools).

Every test generates its formation at runtime into a temp directory
(the scheduler-area standalone pattern): the fixture MCP job server
needs absolute paths and a per-test state file, so a static committed
formation cannot express it. The generator writes formation.yaml plus
mcp/job-server.yaml and symlinks the shared e2e secrets.

NOTE: the filename deliberately matches the runners' skip patterns
("common.py") so it is never collected as a test.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

AREA_DIR = Path(__file__).parent
ASSETS_DIR = AREA_DIR.parent.parent / "assets"
FIXTURE_SERVER = AREA_DIR / "fixture_job_server.py"

TEST_USER = "watch-user"
TEST_SESSION = "watch-session-1"

AGENT_SYSTEM_MESSAGE = """\
You are a render assistant. When the user asks you to render or generate
an image, call the submit tool exactly once, passing their description as
the prompt. Follow your instructions for asynchronous jobs. Keep every
response under 40 words.
"""

FORMATION_TEMPLATE = """\
schema: "1.0.0"
id: {formation_id}
description: E2E formation for watch_job (remote async tools)

llm:
  api_keys:
    openai: "${{{{ secrets.OPENAI_API_KEY }}}}"
  models:
    - text: "openai/gpt-4o-mini"

runtime:
  built_in_mcps: false

mcp:
  watch:
    interval: {interval}
    timeout: {timeout}
  servers:
    - job-server

agents:
  - id: assistant
    name: Assistant
    description: Render assistant for watch testing
    system_message: |
{system_message}
    default: true

overlord:
  workflow:
    auto_decomposition: false
  response:
    streaming: false
    widgets: false

logging:
  system:
    level: "error"
    destination: "stdout"
  conversation:
    enabled: false
"""

MCP_SERVER_TEMPLATE = """\
schema: "1.0.0"
id: "job-server"
description: "Fixture async job service (submit + check_status)"

type: "command"
command: "{python}"
args: {args}
timeout_seconds: 30
"""

SINK_TRANSFORMER_TEMPLATE = """\
name: {name}
endpoint:
  url: http://127.0.0.1:{port}{path}
  method: POST
headers:
  Content-Type: application/json
body:
  text: "${{{{ response.content }}}}"
  user: "${{{{ request.user_id }}}}"
"""


def build_formation(
    base_dir: Path,
    *,
    interval: int = 1,
    timeout: int = 120,
    polls_to_done: int = 2,
    commands: bool = False,
    sink_port: Optional[int] = None,
    default_channel: str = "chan-a",
    groups: Optional[Dict[str, str]] = None,
    rbac_fallback: Optional[str] = None,
    formation_id: str = "formation-watch-test",
) -> Path:
    """Generate a watch e2e formation under ``base_dir`` and return its path."""
    formation_dir = base_dir / "formation"
    (formation_dir / "mcp").mkdir(parents=True)

    state_file = base_dir / "job-state.json"
    system_message = "".join(
        f"      {line}\n" for line in AGENT_SYSTEM_MESSAGE.strip().splitlines()
    )
    content = FORMATION_TEMPLATE.format(
        formation_id=formation_id,
        interval=interval,
        timeout=timeout,
        system_message=system_message.rstrip("\n"),
    )
    if commands:
        content += "\ncommands: {}\n"
    if sink_port is not None:
        content += (
            "\nproactive:\n"
            "  channels:\n"
            "    chan-a:\n"
            "      transformer: sink-a\n"
            "    chan-b:\n"
            "      transformer: sink-b\n"
            f"  default_channel: {default_channel}\n"
        )
        transformers = formation_dir / "transformers"
        transformers.mkdir()
        for name, path in (("sink-a", "/a"), ("sink-b", "/b")):
            (transformers / f"{name}.yaml").write_text(
                SINK_TRANSFORMER_TEMPLATE.format(name=name, port=sink_port, path=path)
            )
    if groups:
        groups_dir = formation_dir / "groups"
        groups_dir.mkdir()
        for name, body in groups.items():
            (groups_dir / f"{name}.yaml").write_text(body)
        if rbac_fallback:
            content += f"\nrbac:\n  fallback: {rbac_fallback}\n"

    (formation_dir / "formation.yaml").write_text(content)

    args = [
        str(FIXTURE_SERVER),
        "--state",
        str(state_file),
        "--polls-to-done",
        str(polls_to_done),
    ]
    (formation_dir / "mcp" / "job-server.yaml").write_text(
        MCP_SERVER_TEMPLATE.format(python=sys.executable, args=json.dumps(args))
    )

    # Shared e2e secrets: BOTH the blob and its key must resolve, or the
    # SecretsManager mints a fresh key that cannot decrypt the blob.
    os.symlink(ASSETS_DIR / "secrets.enc", formation_dir / "secrets.enc")
    os.symlink(ASSETS_DIR / ".key", formation_dir / ".key")

    return formation_dir


async def load_formation(formation_dir: Path):
    """Load a generated formation and start its overlord."""
    formation = Formation()
    await formation.load(str(formation_dir))
    overlord = await formation.start_overlord()
    if overlord.watch_service is None:
        raise AssertionError("watch service was not initialized (mcp servers declared)")
    return formation, overlord


def content_of(response) -> str:
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


async def find_new_watch(overlord, before: set) -> tuple:
    """Locate the watch created this turn under whichever user id tracked it."""
    for candidate in (TEST_USER, "0"):
        for entry in await overlord.watch_service.list_user_jobs(candidate):
            if entry["id"] not in before:
                return entry, candidate
    return None, None


async def snapshot_watch_ids(overlord) -> set:
    before = set()
    for candidate in (TEST_USER, "0"):
        for entry in await overlord.watch_service.list_user_jobs(candidate):
            before.add(entry["id"])
    return before


async def wait_for_terminal(overlord, job_id: str, user: str, timeout: float = 120):
    """Poll the tracked watch until it reaches a terminal state."""
    service = overlord.watch_service
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = service.get_job(job_id, user)
        assert job is not None, f"watch {job_id} vanished from the tracked surface"
        if job.status != "watching":
            print(f"Watch {job_id} reached terminal state: {job.status} ({job.polls} polls)")
            return job
        await asyncio.sleep(0.5)
    raise AssertionError(f"watch {job_id} did not finish within {timeout}s")


async def wait_for_reentry(overlord, job_id: str, user: str, timeout: float = 120):
    """Wait for the completion re-entry turn (route_class: watch)."""
    service = overlord.watch_service
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = service.get_job(job_id, user)
        if job is not None and job.reentry_at is not None:
            print(f"Completion re-entry recorded at {job.reentry_at.isoformat()}")
            return job
        await asyncio.sleep(1)
    raise AssertionError(f"completion re-entry did not happen for watch {job_id}")


async def teardown(formation) -> None:
    try:
        await formation.stop_overlord()
    except Exception:
        pass
    await asyncio.sleep(1)


DONE_WHEN = {"path": "$.status", "in": ["succeeded", "failed"]}


async def start_watch_directly(
    overlord,
    *,
    user: str,
    args: Optional[Dict[str, Any]] = None,
    label: str = "fixture watch",
) -> Dict[str, Any]:
    """Register a watch through the service surface (deterministic tests).

    Submits a job through the fixture first so check_status has a real
    job id to poll.
    """
    submit = await overlord.mcp_service.invoke_tool("job-server", "submit", {"prompt": "fox"})
    body = submit["result"]["structured_content"]
    assert body.get("job_id"), f"fixture submit failed: {submit}"
    result = await overlord.watch_service.watch(
        agent_id="assistant",
        user_id=user,
        tool="job-server.check_status",
        args=args or {"job_id": body["job_id"]},
        done_when=dict(DONE_WHEN),
        result="$.output",
        label=label,
    )
    assert result.get("success"), f"watch registration failed: {result}"
    return result
