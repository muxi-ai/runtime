#!/usr/bin/env python3
"""
Test 25B1: Response Envelope UI - mcp_resource passthrough (P2)

A fixture stdio MCP server returns an embedded ui:// resource in its
tool result (the MCP Apps convention). Verifies the gateway contract:
1. The envelope carries an mcp_resource widget with the resource URI,
   mime type, and data relayed VERBATIM (no rendering, no rewriting)
2. Provenance is recorded on the widget (producing server + tool)
3. The text fallback stays complete on its own AND the untrusted UI
   resource content never passes through the LLM
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fixture_ui_server import (  # noqa: E402
    DASHBOARD_HTML,
    DASHBOARD_MIME,
    DASHBOARD_URI,
)
from mcp_resource_common import (  # noqa: E402
    TEST_USER,
    build_formation,
    content_of,
    load_formation,
    mcp_resource_widgets,
    teardown,
)


async def main() -> int:
    print("MUXI Runtime - Test 25B1: mcp_resource passthrough")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="muxi-e2e-25b1-") as tmp:
        formation_dir = build_formation(Path(tmp))
        formation, overlord = await load_formation(formation_dir)
        await asyncio.sleep(2)  # Give the MCP server time to initialize

        try:
            print("\n[1] Asking for the sales dashboard...")
            response = await overlord.chat(
                message="Show me the sales dashboard",
                user_id=TEST_USER,
                session_id="sess-25b1",
                stream=False,
            )
            content = content_of(response)
            print(f"    Response: {content[:200]}")

            # ---------------------------------------------------------
            # Verbatim passthrough
            # ---------------------------------------------------------
            widgets = mcp_resource_widgets(response)
            assert (
                widgets
            ), f"Expected an mcp_resource widget, got ui={getattr(response, 'ui', None)}"
            widget = widgets[0]
            assert widget["resource"] == DASHBOARD_URI, widget
            assert widget["mime_type"] == DASHBOARD_MIME, widget
            assert widget["data"] == DASHBOARD_HTML, (
                "UI resource data was not relayed verbatim "
                f"(len={len(widget['data'])} vs {len(DASHBOARD_HTML)})"
            )
            assert "encoding" not in widget, widget  # text resource: default encoding
            assert widget["id"].startswith("ui_"), widget
            print(
                f"    Widget relayed verbatim: {widget['resource']} "
                f"({len(widget['data'])} bytes)"
            )

            # ---------------------------------------------------------
            # Provenance: producing server + tool on the widget
            # ---------------------------------------------------------
            assert widget["server"] == "dashboard-server", widget
            assert widget["tool"] == "show_dashboard", widget
            print(f"    Provenance recorded: {widget['server']}.{widget['tool']}")

            # ---------------------------------------------------------
            # Text fallback duty + untrusted-content posture
            # ---------------------------------------------------------
            assert content and len(content.strip()) > 0, "text fallback must be complete alone"
            assert (
                "FIXTURE-CHART-7f3a" not in content
            ), "UI resource content leaked into the LLM-generated text"
            assert "ui://" not in content, "resource URI leaked into the text"
            print("    Text complete on its own; resource content stayed out of the LLM")

            print("\n" + "=" * 70)
            print("SUCCESS: ui:// resource relayed verbatim as an mcp_resource")
            print("         widget with server+tool provenance; text intact")
            return 0

        finally:
            await teardown(formation)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
