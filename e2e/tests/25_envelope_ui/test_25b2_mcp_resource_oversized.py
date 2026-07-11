#!/usr/bin/env python3
"""
Test 25B2: Response Envelope UI - oversized mcp_resource clamped away

The fixture server pads its ui:// resource beyond the per-widget cap
(UI_MCP_RESOURCE_MAX_BYTES). Verifies the clamp discipline:
1. No mcp_resource widget ships (dropped whole, never truncated)
2. No error surfaces — the turn completes normally
3. The text fallback stays complete on its own
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from mcp_resource_common import (  # noqa: E402
    TEST_USER,
    build_formation,
    content_of,
    load_formation,
    mcp_resource_widgets,
    teardown,
)

from muxi.runtime.datatypes.ui import UI_MCP_RESOURCE_MAX_BYTES  # noqa: E402


async def main() -> int:
    print("MUXI Runtime - Test 25B2: oversized mcp_resource clamped")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="muxi-e2e-25b2-") as tmp:
        # Pad well past the per-widget cap so the serialized widget
        # (data + envelope fields) is unambiguously oversized.
        formation_dir = build_formation(Path(tmp), resource_bytes=UI_MCP_RESOURCE_MAX_BYTES + 4096)
        formation, overlord = await load_formation(formation_dir)
        await asyncio.sleep(2)  # Give the MCP server time to initialize

        try:
            print("\n[1] Asking for the dashboard (fixture returns an oversized resource)...")
            response = await overlord.chat(
                message="Show me the sales dashboard",
                user_id=TEST_USER,
                session_id="sess-25b2",
                stream=False,
            )
            content = content_of(response)
            print(f"    Response: {content[:200]}")

            widgets = mcp_resource_widgets(response)
            assert (
                widgets == []
            ), f"Oversized resource must be clamped away, got {len(widgets)} widget(s)"
            print("    No mcp_resource widget shipped (clamped whole, not truncated)")

            assert content and len(content.strip()) > 0, "text fallback must be complete alone"
            lowered = content.lower()
            assert (
                "error" not in lowered or "no error" in lowered
            ), f"clamping must be silent, but the response reads as an error: {content[:300]}"
            print("    Turn completed cleanly; text intact")

            print("\n" + "=" * 70)
            print("SUCCESS: oversized ui:// resource dropped cleanly (no widget,")
            print("         no error) and the text fallback stayed complete")
            return 0

        finally:
            await teardown(formation)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    os._exit(exit_code)
