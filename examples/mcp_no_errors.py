#!/usr/bin/env python3
"""Example: Using MCP servers without async generator errors"""

import asyncio
from src.muxi.runtime.formation import Formation


async def main():
    """Example of using Formation with MCP servers - NO ERRORS!"""

    # Create formation
    formation = Formation()

    # Load configuration
    await formation.load("test-formations/formation-mcp")

    # Start overlord
    overlord = await formation.start_overlord()

    # Use MCP tools
    response_gen = await overlord.chat(
        "How many MCP tools are available?",
        user_id="user1",
        use_async=False
    )

    # Collect response
    response = ""
    async for chunk in response_gen:
        response += chunk

    print(f"Response: {response}")

    # Proper shutdown - NO ERRORS!
    # Option 1: Immediate shutdown (recommended for scripts)
    formation.shutdown()

    # Option 2: Graceful async shutdown (for services)
    # await formation.ashutdown()

    # Option 3: Register exit handler at startup
    # formation.suppress_mcp_errors_on_exit()

if __name__ == "__main__":
    asyncio.run(main())
