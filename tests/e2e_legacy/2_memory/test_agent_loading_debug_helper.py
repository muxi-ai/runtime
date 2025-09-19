#!/usr/bin/env python3
"""Debug agent loading for memory formation."""
from pathlib import Path

import logging
from concurrent.futures import ThreadPoolExecutor
from muxi.formation import Formation

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_agent_loading():
    """Test agent loading from formation."""

    async def run_test():
        formation_path = (
            str(Path(__file__).parent / "formations" / "formation-memory" / "formation-postgres-and-faissx-with-auth.yaml")
        )
        logger.info(f"Loading formation from: {formation_path}")

        formation = Formation()
        await formation.load(formation_path)
        logger.info("Formation loaded")

        overlord = await formation.start_overlord()
        logger.info("Overlord started")

        # Check what agents are available
        logger.info(f"Active agents tracker: {overlord.active_agent_tracker}")
        logger.info(
            f"Active agents: {overlord.active_agent_tracker.active_agents if hasattr(overlord.active_agent_tracker, 'active_agents') else 'N/A'}"  # noqa: E501
        )

        # Try to list agents
        try:
            agents_list = overlord.get_agents()
            logger.info(f"Agents list: {agents_list}")
        except Exception as e:
            logger.error(f"Failed to get agents list: {e}")

        # Check agent router
        if hasattr(overlord, "agent_router"):
            logger.info(
                f"Agent router available agents: {getattr(overlord.agent_router, '_agents', 'N/A')}"
            )

        await formation.stop_overlord()
        logger.info("Test completed")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_test)
        future.result()


if __name__ == "__main__":
    test_agent_loading()
