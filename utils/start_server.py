#!/usr/bin/env python3
"""
Start a test server for API testing.

Usage:
    python utils/start_test_server.py [formation_path]

If no formation path is provided, uses test-formations/formation-multi-agent
"""


import asyncio
import sys
from pathlib import Path
import signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    formation_path = Path(__file__).parent.parent / "test-formations" / "formation-multi-agent"
    # await formation.load("../../test-formations/formation-knowledge/formation.yaml")

    formation = None
    shutdown_event = asyncio.Event()
    shutdown_count = 0

    def signal_handler(sig_num):
        nonlocal shutdown_count
        shutdown_count += 1

        if shutdown_count == 1:
            print("\n📢 Graceful shutdown initiated... Press Ctrl+C again to force kill")
            shutdown_event.set()
        elif shutdown_count == 2:
            print("\n🔥 Force killing everything NOW!")
            if formation:
                formation.kill(1)
            else:
                sys.exit(1)
        else:
            # Third time, just exit
            sys.exit(1)

    # Install signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        print("\n1️⃣ Loading formation...")
        formation = Formation()
        await formation.load(str(formation_path))
        print("   ✅ Formation loaded successfully")

        # Get server info
        server_config = formation.config.get("server", {})
        print("================================================")
        print(f"   ✅ Server config: {server_config}")
        print("================================================")

        # Start server
        print("\n2️⃣ Starting API server...")
        # Start server in non-blocking mode to avoid signal handler conflicts
        server = await formation.start_server(block=False)
        print(f"   ✅ Server started: {server}")

        # Wait a bit to ensure server is fully started
        print("   ⏳ Waiting for server to be fully ready...")
        await asyncio.sleep(2)

        # Test if server is actually listening
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://{server_config.get('host', '0.0.0.0')}:{server_config.get('port', 8271)}/health"
                )
                print(f"   ✅ Server health check: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Server health check failed: {e}")

        # Keep the server running until interrupted
        print("\nPress Ctrl+C to stop the server")

        # Wait for shutdown signal
        await shutdown_event.wait()

        # Perform graceful shutdown
        print("\n🛑 Shutting down gracefully...")
        formation.shutdown()
        print("   ✅ Graceful shutdown complete!")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        raise e
    finally:
        # Remove signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


if __name__ == "__main__":
    asyncio.run(main())
