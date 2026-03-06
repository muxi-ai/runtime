#!/usr/bin/env python3
"""Test 1a7: Explicit Component Declaration.

Verifies that the formation loader only loads agents and MCP servers that are
explicitly declared in the formation file by ID. Files in subdirectories that
are not declared should be ignored.
"""

import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import TestOutputFormatter, TestTimeouts  # noqa: E402
from muxi.runtime.formation import Formation  # noqa: E402


class TestExplicitComponentDeclaration:
    """Test explicit component declaration pattern."""

    async def run(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False
        checks = []

        formatter.print_test_header(
            test_name="test_1a7_explicit_component_declaration",
            description="Test explicit agent/MCP declaration in formation manifest",
        )

        formation = None
        try:
            formation_path = Path(__file__).parent / "formations" / "formation-explicit-declaration"

            # 1. Load formation
            print("\n1. Loading formation with explicit declarations...")
            formation = Formation()
            await formation.load(str(formation_path))
            print("   Formation loaded successfully")
            checks.append("Formation loaded")

            # 2. Verify only declared agent is in config
            print("\n2. Verifying agent resolution...")
            agents = formation.config.get("agents", [])
            agent_ids = [a["id"] for a in agents if isinstance(a, dict)]
            print(f"   Agents in config: {agent_ids}")

            assert "declared-agent" in agent_ids, "declared-agent should be loaded"
            assert "undeclared-agent" not in agent_ids, "undeclared-agent should NOT be loaded"
            assert len(agent_ids) == 1, f"Expected 1 agent, got {len(agent_ids)}"
            print("   declared-agent: loaded")
            print("   undeclared-agent: correctly ignored")
            checks.append("Only declared agent loaded")

            # 3. Verify only declared MCP is in config
            print("\n3. Verifying MCP server resolution...")
            mcp_servers = formation.config.get("mcp", {}).get("servers", [])
            mcp_ids = [s["id"] for s in mcp_servers if isinstance(s, dict)]
            print(f"   MCP servers in config: {mcp_ids}")

            assert "declared-mcp" in mcp_ids, "declared-mcp should be loaded"
            assert "undeclared-mcp" not in mcp_ids, "undeclared-mcp should NOT be loaded"
            assert len(mcp_ids) == 1, f"Expected 1 MCP server, got {len(mcp_ids)}"
            print("   declared-mcp: loaded")
            print("   undeclared-mcp: correctly ignored")
            checks.append("Only declared MCP loaded")

            # 4. Start overlord and verify agents are operational
            print("\n4. Starting overlord and verifying agents...")
            overlord = await formation.start_overlord()

            overlord_agent_ids = list(overlord.agents.keys())
            print(f"   Overlord agents: {overlord_agent_ids}")
            assert "declared-agent" in overlord_agent_ids
            assert "undeclared-agent" not in overlord_agent_ids
            checks.append("Overlord has correct agents")

            # 5. Chat works with the declared agent
            print("\n5. Testing chat with declared agent...")
            timeout = TestTimeouts.get_timeout("simple_chat")
            response = await asyncio.wait_for(
                overlord.chat("Hello, who are you?", user_id="test_user"),
                timeout=timeout,
            )
            assert response is not None
            response_text = response.content if hasattr(response, "content") else str(response)
            print(f"   Response: {response_text[:100]}...")
            checks.append("Chat works with declared agent")

            # 6. Clean up
            print("\n6. Stopping formation...")
            await formation.stop_overlord()
            print("   Stopped successfully")
            checks.append("Clean shutdown")

            success = True

        except Exception as e:
            checks.append(f"Failed: {str(e)}")
            import traceback
            traceback.print_exc()
            if formation:
                try:
                    await formation.stop_overlord()
                except Exception:
                    pass
            raise

        finally:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name="test_1a7_explicit_component_declaration",
                success=success,
                checks=checks,
                transcript=[],
                duration=duration,
            )
            return 0 if success else 1


def main():
    import os
    test = TestExplicitComponentDeclaration()
    exit_code = asyncio.run(test.run())
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)


if __name__ == "__main__":
    main()
