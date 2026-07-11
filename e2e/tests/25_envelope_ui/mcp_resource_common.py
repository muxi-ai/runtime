"""
Shared helpers for the mcp_resource passthrough e2e tests (Response
Envelope UI, P2).

The fixture MCP server needs absolute paths (python interpreter +
script + flags), so the formation is generated at runtime into a temp
directory — the same standalone pattern as the 26_watch area. The
generator writes formation.yaml plus mcp/dashboard-server.yaml and
symlinks the shared e2e secrets.

NOTE: the filename deliberately matches the runners' skip patterns
("common.py") so it is never collected as a test.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

AREA_DIR = Path(__file__).parent
ASSETS_DIR = AREA_DIR.parent.parent / "assets"
FIXTURE_SERVER = AREA_DIR / "fixture_ui_server.py"

TEST_USER = "envelope-ui-user"

AGENT_SYSTEM_MESSAGE = """\
You are a sales assistant. When the user asks about the sales dashboard
or sales figures, call the show_dashboard tool exactly once, then answer
using the summary it returns. Keep every response under 40 words.
"""

FORMATION_TEMPLATE = """\
schema: "1.0.0"
id: formation-envelope-mcp-resource
description: E2E formation for the mcp_resource passthrough widget

llm:
  api_keys:
    openai: "${{{{ secrets.OPENAI_API_KEY }}}}"
  models:
    - text: "openai/gpt-4o-mini"

runtime:
  built_in_mcps: false

mcp:
  servers:
    - dashboard-server
  max_tool_calls: 5
  max_tool_iterations: 3

agents:
  - id: assistant
    name: Assistant
    description: Sales assistant for mcp_resource testing
    system_message: |
{system_message}
    default: true

overlord:
  workflow:
    auto_decomposition: false

logging:
  system:
    level: "error"
    destination: "stdout"
  conversation:
    enabled: false
"""

MCP_SERVER_TEMPLATE = """\
schema: "1.0.0"
id: "dashboard-server"
description: "Fixture MCP Apps server (show_dashboard returns a ui:// resource)"

type: "command"
command: "{python}"
args: {args}
timeout_seconds: 30
"""


def build_formation(base_dir: Path, *, resource_bytes: int = 0) -> Path:
    """Generate the e2e formation under ``base_dir`` and return its path."""
    formation_dir = base_dir / "formation"
    (formation_dir / "mcp").mkdir(parents=True)

    system_message = "".join(
        f"      {line}\n" for line in AGENT_SYSTEM_MESSAGE.strip().splitlines()
    )
    (formation_dir / "formation.yaml").write_text(
        FORMATION_TEMPLATE.format(system_message=system_message.rstrip("\n"))
    )

    args = [str(FIXTURE_SERVER), "--resource-bytes", str(resource_bytes)]
    (formation_dir / "mcp" / "dashboard-server.yaml").write_text(
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
    return formation, overlord


def content_of(response) -> str:
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


def mcp_resource_widgets(response):
    return [w for w in (getattr(response, "ui", None) or []) if w.get("type") == "mcp_resource"]


async def teardown(formation) -> None:
    try:
        await formation.stop_overlord()
        formation.stop()
    except Exception:
        pass
