"""
Simple agent example with the MUXI Framework.

This example demonstrates how to create a simple agent with memory and a language model
that connects to MCP servers for specialized capabilities.
"""

import asyncio
import os

from dotenv import load_dotenv

from muxi.engine.overlord import Overlord
from muxi.engine.memory.buffer import BufferMemory
from muxi.engine.llm import LLM, set_llm_api_key

# Load environment variables from .env file
load_dotenv()

# Set API key for OpenAI provider
set_llm_api_key(os.getenv("OPENAI_API_KEY", ""), "openai")


async def main():
    # Create an LLM model instance
    model = LLM(
        model="openai/gpt-4o",
        temperature=0.7,
    )

    # Create a memory system for the overlord
    buffer_memory = BufferMemory(
        max_size=10,               # Context window size
        buffer_multiplier=10,      # Total capacity = 10 × 10 = 100 messages
    )

    # Create an overlord with the memory system
    overlord = Overlord(buffer_memory=buffer_memory)

    # Add an agent
    agent = overlord.create_agent(
        agent_id="assistant",
        system_message="You are a helpful assistant.",
        model=model,
    )

    # Connect to MCP servers (commented out for testing)
    # Uncomment these lines when you have MCP servers running
    """
    await agent.connect_mcp_server(
        name="calculator",
        url="http://localhost:5001",
        credentials={"api_key": os.getenv("CALCULATOR_API_KEY")}
    )

    await agent.connect_mcp_server(
        name="web_search",
        url="http://localhost:5002",
        credentials={"api_key": os.getenv("SEARCH_API_KEY")}
    )
    """

    # Chat with the agent
    weather_message = "What is the weather like in New York City today?"
    response = await agent.process_message(weather_message)
    print(f"Agent: {response.content}")

    # Demonstrate conversation memory
    followup_message = "What about tomorrow?"
    response = await agent.process_message(followup_message)
    print(f"Agent: {response.content}")

    # Demonstrate model capabilities without MCP servers
    math_message = "What is the square root of 144?"
    response = await agent.process_message(math_message)
    print(f"Agent: {response.content}")

if __name__ == "__main__":
    asyncio.run(main())
