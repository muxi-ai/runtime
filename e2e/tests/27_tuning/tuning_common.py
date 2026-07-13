"""
Shared helpers for the 27_tuning e2e area (Self-Improving Formation).

Every test generates its formation at runtime into a temp directory (the
watch-area standalone pattern) with a UNIQUE formation id: the event
spool lives under ~/.muxi/{formation_id}/observability/spool, so a fresh
id per test run is the isolation mechanism. Helpers cover the spool
directory surface, digest triggering through the overlord's tuning
service, and seeded multi-user traffic.

NOTE: the filename deliberately matches the runners' skip patterns
("common.py") so it is never collected as a test.
"""

import asyncio
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

# The benchmark observation is opt-in via $MUXI_BENCH_ROOT; a globally
# exported value must not make every area-27 pass spend minutes (and
# tokens) on real benchmark suites. 27A8 sets it back explicitly.
os.environ.pop("MUXI_BENCH_ROOT", None)

from muxi.runtime.formation import Formation  # noqa: E402

AREA_DIR = Path(__file__).parent
ASSETS_DIR = AREA_DIR.parent.parent / "assets"
REPO_ROOT = AREA_DIR.parent.parent.parent

FORMATION_TEMPLATE = """\
schema: "1.0.0"
id: {formation_id}
description: E2E formation for the self-improvement tuning loop

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
    description: Concise assistant for tuning-loop testing
    system_message: |
      You are a helpful assistant. Keep every response under 30 words.
    default: true

overlord:
  workflow:
    auto_decomposition: false
  response:
    streaming: false
    widgets: false
"""

FILE_LOGGING_BLOCK = """
logging:
  system:
    level: "error"
    destination: "{destination}"
  conversation:
    enabled: false
"""

MANUAL_TUNING_BLOCK = """
tuning:
  auto_apply: false
"""

COMMANDS_BLOCK = """
commands:
  enabled: true
"""

PROACTIVE_BLOCK = """
proactive:
  channels:
    report-chan:
      transformer: report-t
  default_channel: report-chan
"""

REPORT_TRANSFORMER = """\
name: report-t
endpoint:
  url: {url}
body:
  text: "${{{{ response.content }}}}"
  reply_markup: "${{{{ ui.telegram.reply_markup }}}}"
"""

SERVER_BLOCK = """
server:
  enabled: true
  port: {port}
  api_keys:
    admin_key: {admin_key}
    client_key: {client_key}
"""

ADMIN_KEY = "tuning-admin-key-27"
CLIENT_KEY = "tuning-client-key-27"


def unique_formation_id(tag: str) -> str:
    return f"tuning-e2e-{tag}-{uuid.uuid4().hex[:8]}"


def spool_dir_for(formation_id: str) -> Path:
    """Where the always-on spool writes for this formation id."""
    return Path.home() / ".muxi" / formation_id / "observability" / "spool"


def build_formation(
    base_dir: Path,
    formation_id: str,
    *,
    file_logging: bool = False,
    server_port: Optional[int] = None,
    muxi_md: Optional[str] = None,
    manual_tuning: bool = False,
    commands: bool = False,
    proactive_url: Optional[str] = None,
) -> Path:
    """Generate a tuning e2e formation under ``base_dir`` and return its path."""
    formation_dir = base_dir / "formation"
    formation_dir.mkdir(parents=True)

    content = FORMATION_TEMPLATE.format(formation_id=formation_id)
    if file_logging:
        content += FILE_LOGGING_BLOCK.format(destination=str(base_dir / "system.jsonl"))
    if server_port is not None:
        content += SERVER_BLOCK.format(port=server_port, admin_key=ADMIN_KEY, client_key=CLIENT_KEY)
    if manual_tuning:
        content += MANUAL_TUNING_BLOCK
    if commands:
        content += COMMANDS_BLOCK
    if proactive_url is not None:
        content += PROACTIVE_BLOCK
        transformers_dir = formation_dir / "transformers"
        transformers_dir.mkdir()
        (transformers_dir / "report-t.yaml").write_text(
            REPORT_TRANSFORMER.format(url=proactive_url)
        )
    (formation_dir / "formation.yaml").write_text(content)
    if muxi_md is not None:
        (formation_dir / "MUXI.md").write_text(muxi_md)

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
    return formation, overlord


def content_of(response) -> str:
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


async def chat(overlord, message: str, user: str, session: str) -> str:
    response = await overlord.chat(
        message=message,
        user_id=user,
        session_id=session,
        use_async=False,
        stream=False,
    )
    return content_of(response)


def wait_for_segments(spool_dir: Path, timeout: float = 20) -> list:
    """Poll until at least one spool segment file exists."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        segments = sorted(spool_dir.glob("events-*.jsonl"))
        if segments:
            return segments
        time.sleep(0.5)
    raise AssertionError(f"no spool segments appeared under {spool_dir} within {timeout}s")


def digest_model(overlord):
    """The model the scheduled loop would use for the digest step."""
    model = getattr(overlord, "extraction_model", None) or getattr(overlord, "default_model", None)
    assert model is not None, "overlord has no text model for the digest step"
    return model


async def run_tuning_pass(overlord) -> dict:
    """Trigger one tuning loop pass (the POST /tuning/run path)."""
    assert (
        overlord.tuning_service is not None
    ), "tuning service was not initialized (it is on by default)"
    return await overlord.tuning_service.run_once(digest_model(overlord), trigger="manual")


def experiments_path_for(formation_id: str) -> Path:
    """Where the tuner's experiment memories live for this formation id."""
    return Path.home() / ".muxi" / formation_id / "observability" / "tuner" / "experiments.json"


def tuner_dir_for(formation_id: str) -> Path:
    """The tuner sidecar directory (experiments, benchmark scores/reports)."""
    return Path.home() / ".muxi" / formation_id / "observability" / "tuner"


def plant_tool_failures(count: int = 30, tool: str = "jira") -> None:
    """Write a planted flaky-tool pattern straight into the event spool.

    The PRD's tuner fixture: a tool failing 14:00-16:00. The spool is an
    internal JSONL buffer, so the fixture writes the same shape the
    logger tee produces.
    """
    import json as json_module

    from muxi.runtime.services.observability.spool import get_event_spool

    base_ts = 1783864800000  # 14:00 UTC
    # Distinct descriptions: the report keeps a few deduplicated samples
    # per cluster, so variety keeps the tool name salient in all of them.
    problems = [
        f"{tool} MCP request timed out after 30s",
        f"{tool} MCP returned 429 (rate limited)",
        f"{tool} MCP connection reset by peer",
    ]
    events = []
    for index in range(count):
        events.append(
            json_module.dumps(
                {
                    "event": "mcp.tool.failed",
                    "level": "warning",
                    "timestamp": base_ts + index * 240_000,  # spread across 2h
                    "data": {
                        "description": problems[index % len(problems)],
                        "tool": tool,
                    },
                }
            )
        )
    get_event_spool().write_lines(events)


async def teardown(formation, formation_id: Optional[str] = None) -> None:
    try:
        await formation.stop_overlord()
    except Exception:
        pass
    await asyncio.sleep(1)
    if formation_id:
        shutil.rmtree(Path.home() / ".muxi" / formation_id, ignore_errors=True)
