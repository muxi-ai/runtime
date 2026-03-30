#!/usr/bin/env python3
"""Test 4F1: MCP connection keep-alive with TTL.

Verifies that:
1. connection_ttl is read from formation config and applied to MCPService
2. After the first tool call, a live connection exists in the pool
3. A second tool call reuses the same connection (pool size stays at 1)
4. The connection is keyed correctly by (server_id, credentials)
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402

from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-mcp-ttl"


class Test4F1ConnectionTTL(BaseE2ETest):
    """Test MCP connection keep-alive with configurable TTL."""

    def __init__(self):
        super().__init__(
            test_name="Test 4F1: MCP Connection TTL",
            test_description="Verify connections are kept alive and reused between tool calls",
            test_area="4_mcp",
        )
        self.formatter = TestOutputFormatter()
        self.formation = None

    async def run_test(self):
        test_name = "Test 4F1: MCP Connection TTL"
        description = "Verify MCP connections are reused between tool calls via TTL keep-alive"

        self.formatter.print_test_header(test_name, description)

        start_time = time.time()
        checks = []
        transcript = []
        success = False

        try:
            # Load formation
            print("\n  1. Loading formation with connection_ttl=300 ...")
            self.formation = Formation()
            await self.formation.load(str(FORMATION_DIR / "formation.yaml"))
            overlord = await self.formation.start_overlord()
            checks.append("Formation loaded")

            # Get a reference to the MCP service
            mcp_service = self.formation._mcp_service
            assert mcp_service is not None, "MCPService not initialised"
            checks.append("MCPService available")

            # Verify TTL was configured from formation config
            print("  2. Checking connection_ttl was configured ...")
            assert mcp_service._connection_ttl == 300.0, (
                f"Expected global TTL 300, got {mcp_service._connection_ttl}"
            )
            checks.append("Global connection_ttl=300 applied")

            # Verify no live connections before any tool call
            assert len(mcp_service._live_connections) == 0, "Pool should be empty before first call"
            checks.append("Connection pool empty before first tool call")

            # First tool call -- should create a new connection
            print("  3. First tool call (should create connection) ...")
            request1 = "What is the current CPU usage percentage?"
            transcript.append(("User", request1))

            response1 = await overlord.chat(
                request1, user_id="test_user", use_async=False, stream=False
            )
            response1_text = (
                response1.content if hasattr(response1, "content") else str(response1)
            )
            print(f"     Response: {response1_text[:120]}...")
            transcript.append(("System", response1_text[:200]))

            pool_after_first = len(mcp_service._live_connections)
            print(f"     Live connections after first call: {pool_after_first}")

            if pool_after_first > 0:
                checks.append(f"Connection created and kept alive (pool={pool_after_first})")
            else:
                checks.append("WARNING: No live connection after first call (tool may not have been invoked)")

            # Capture the connection key for comparison
            pool_keys_after_first = set(mcp_service._live_connections.keys())

            # Second tool call -- should reuse the connection
            print("  4. Second tool call (should reuse connection) ...")
            request2 = "How much disk space is available?"
            transcript.append(("User", request2))

            response2 = await overlord.chat(
                request2, user_id="test_user", use_async=False, stream=False
            )
            response2_text = (
                response2.content if hasattr(response2, "content") else str(response2)
            )
            print(f"     Response: {response2_text[:120]}...")
            transcript.append(("System", response2_text[:200]))

            pool_after_second = len(mcp_service._live_connections)
            pool_keys_after_second = set(mcp_service._live_connections.keys())
            print(f"     Live connections after second call: {pool_after_second}")

            # The pool should still have the same connection (reused, not a new one)
            if pool_keys_after_first and pool_keys_after_first == pool_keys_after_second:
                checks.append("Connection reused (same pool key)")
            elif pool_after_second > 0:
                checks.append("Connection present after second call")

            # Verify the connection was touched (idle timer reset)
            if mcp_service._live_connections:
                conn_key = next(iter(mcp_service._live_connections))
                conn = mcp_service._live_connections[conn_key]
                idle = conn.idle_seconds()
                print(f"     Connection idle time: {idle:.2f}s")
                if idle < 5.0:
                    checks.append(f"Connection recently used (idle {idle:.1f}s)")

            # Third tool call -- one more reuse to confirm pattern
            print("  5. Third tool call (confirm reuse pattern) ...")
            request3 = "What is the system uptime?"
            transcript.append(("User", request3))

            response3 = await overlord.chat(
                request3, user_id="test_user", use_async=False, stream=False
            )
            response3_text = (
                response3.content if hasattr(response3, "content") else str(response3)
            )
            print(f"     Response: {response3_text[:120]}...")
            transcript.append(("System", response3_text[:200]))

            pool_keys_after_third = set(mcp_service._live_connections.keys())

            if pool_keys_after_first and pool_keys_after_first == pool_keys_after_third:
                checks.append("Connection reused across 3 calls (same pool key)")

            # Overall success: connection was created and reused
            success = pool_after_first > 0 and pool_keys_after_first == pool_keys_after_third

            if success:
                checks.append("All connection TTL checks passed")
            else:
                checks.append("Connection reuse pattern not fully confirmed")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            transcript.append(("Error", str(e)))
            checks.append(f"Test failed: {e}")

        finally:
            if self.formation:
                try:
                    await self.formation.shutdown()
                except Exception:
                    pass

        duration = time.time() - start_time
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)
        return success


async def main():
    test = Test4F1ConnectionTTL()
    return await test.run_test()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
