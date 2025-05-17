"""
Basic usage example of the MUXI Framework.

This example demonstrates the simplest way to use the MUXI Framework.
"""

import asyncio
import os

from dotenv import load_dotenv

from muxi.core.overlord import Overlord
from muxi.core.llm import LLM, set_llm_api_key


# Load environment variables
load_dotenv()

# Set API key for OpenAI provider
set_llm_api_key(os.getenv("OPENAI_API_KEY", ""), "openai")


async def main():
    # Create a language model
    model = LLM(
        model="openai/gpt-4o",
        temperature=0.7,
    )

    # Create an overlord
    overlord = Overlord()

    # Add a basic agent with default memory and no tools
    overlord.create_agent(
        agent_id="basic_agent",
        model=model,
        system_message="You are a helpful AI assistant.",
        set_as_default=True
    )

    # Process a message with the agent
    response = await overlord.run_agent(
        input_text="Hello, what capabilities does the MUXI Framework have?",
        agent_id="basic_agent"
    )

    # Print the response
    print(f"Agent response: {response}")


# Run the example
if __name__ == "__main__":
    asyncio.run(main())
