#!/usr/bin/env python3
"""
Test Formation 2 - Provider
This formation provides services (like IT Support) that Formation 1 can call via A2A.
"""

import asyncio
import sys
from pathlib import Path
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from muxi.formation import Formation  # noqa: E402


async def run_provider():
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-a2a/formation2/formation.yaml"))
    overlord = await formation.start_overlord()

    print("Formation 2 running and ready to accept A2A requests...")

    # Show available agents
    print("\nAvailable agents:")
    for agent_id in overlord.agents.keys():
        print(f"  - {agent_id}")

    print(f"\nA2A Server listening on port: {formation._a2a_config.get('inbound', {}).get('port', 8181)}")
    print("\nPress Ctrl+C to stop...")

    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await formation.stop_overlord()


asyncio.run(run_provider())
