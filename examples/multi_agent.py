#!/usr/bin/env python3
"""
Multi-agent system with the MUXI Framework.

This example demonstrates how to create multiple agents with
specialized roles and message routing capabilities.
"""

import asyncio
import os

from dotenv import load_dotenv

from src.muxi.overlord import Overlord
from src.muxi.llm import LLM, set_llm_api_key
from src.muxi.memory.working import WorkingMemory

# Load environment variables
load_dotenv()

# Set API key for OpenAI provider
set_llm_api_key(os.getenv("OPENAI_API_KEY", ""), "openai")


async def main():
    # Create models
    model = LLM(model="openai/gpt-4o", temperature=0.7)

    # Create a routing model
    routing_model = LLM(model="openai/gpt-4o-mini", temperature=0.2)

    # Create memory systems
    buffer_memory = WorkingMemory(
        max_size=10,               # Context window size
        buffer_multiplier=10,      # Total capacity = 10 × 10 = 100 messages
    )

    # Create an overlord
    overlord = Overlord(buffer_memory=buffer_memory)

    # Set the routing model manually
    overlord.routing_model = routing_model

    # Create specialized agents
    overlord.create_agent(
        agent_id="general",
        model=model,
        system_message="You are a helpful general assistant.",
        description="General-purpose assistant for everyday questions and conversation",
        set_as_default=True
    )

    overlord.create_agent(
        agent_id="code",
        model=model,
        system_message="You are a coding expert specializing in software development.",
        description="Expert in programming, algorithms, and software engineering"
    )

    overlord.create_agent(
        agent_id="math",
        model=model,
        system_message="You are a mathematics expert.",
        description="Expert in mathematics, statistics, and numerical problem-solving"
    )

    # Test with different message types
    questions = [
        "How's the weather today?",
        "What's the best way to implement quicksort in Python?",
        "Solve the equation 3x^2 + 2x - 5 = 0"
    ]

    for question in questions:
        print(f"\nQuestion: {question}")

        # Let the overlord choose the best agent
        try:
            selected_agent_id = await overlord.select_agent_for_message(question)
            print(f"Selected agent: {selected_agent_id}")
        except Exception as e:
            print(f"Error selecting agent: {str(e)}")
            selected_agent_id = "general"  # Fallback to general agent
            print(f"Falling back to agent: {selected_agent_id}")

        # Process with the selected agent
        response = await overlord.run_agent(
            input_text=question,
            agent_id=selected_agent_id
        )
        print(f"Response: {response}")


if __name__ == "__main__":
    asyncio.run(main())
