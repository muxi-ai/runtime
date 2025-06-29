#!/usr/bin/env python3
"""Test with real API keys from secrets - one test at a time with full visibility."""

import asyncio
import sys
import tempfile
import os

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation
from src.muxi.runtime.services.observability import observe
from src.muxi.runtime.services.observability.context import set_event_logger
from src.muxi.runtime.services.observability.logger import EventLogger
from src.muxi.runtime.datatypes.observability import EventLevel


# Custom event logger that prints all events
class PrintingEventLogger(EventLogger):
    def __init__(self):
        super().__init__(level=EventLevel.DEBUG, output="stdout")
    
    async def emit_event(self, event_type, level, data=None, request_context=None, parent_event_id=None, description=None):
        # Print the event
        print(f"\n[OBSERVABILITY EVENT] {event_type.value if hasattr(event_type, 'value') else event_type}")
        if description:
            print(f"  Description: {description}")
        if data:
            print(f"  Data: {data}")
        if request_context:
            print(f"  Request Context: id={request_context.id}, formation={request_context.formation_id}")
        print()
        
        # Call parent to maintain normal logging
        return await super().emit_event(event_type, level, data, request_context, parent_event_id, description)


async def test_1_basic_chat():
    """Test 1: Basic chat functionality with real LLM."""
    print("="*80)
    print("TEST 1: Basic Chat Functionality")
    print("="*80)
    print("\nI am testing basic chat functionality - sending a simple message to the overlord")
    print("and verifying that it responds correctly using the real LLM.\n")
    
    # Use existing test formation with secrets
    formation_path = "test-formations/formation-basic"
    
    try:
        # Set up custom event logger
        logger = PrintingEventLogger()
        set_event_logger(logger)
        
        # Load formation
        print("Loading formation from:", formation_path)
        formation = Formation()
        formation.load(formation_path)
        
        print("\nStarting overlord...")
        overlord = formation.start_overlord()
        
        # Wait for agents to be loaded
        import time
        max_wait = 10  # seconds
        wait_time = 0
        while len(overlord.agents) == 0 and wait_time < max_wait:
            time.sleep(0.5)
            wait_time += 0.5
        
        print(f"\nAgents loaded: {list(overlord.agents.keys())}")
        if not overlord.agents:
            print("❌ No agents loaded!")
            return
        
        # The test message
        test_message = "Hello! Can you tell me what 2 + 2 equals?"
        
        print("\n" + "-"*60)
        print("Prompt sent to overlord.chat:")
        print("-"*60)
        print(test_message)
        print("-"*60 + "\n")
        
        # Make the chat request
        response = await overlord.chat(
            message=test_message,
            user_id="test_user",
            session_id="test_session_1"
        )
        
        print("\n" + "-"*60)
        print("overlord.chat response:")
        print("-"*60)
        print(response)
        print("-"*60 + "\n")
        
        print("Summary:")
        print("-"*60)
        print("✅ Successfully sent a message to the overlord")
        print("✅ Received a response from the LLM")
        print(f"✅ Response type: {type(response)}")
        print(f"✅ Response length: {len(response) if isinstance(response, str) else 'N/A'}")
        
        # Stop overlord
        formation.stop_overlord()
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        raise
    
    # Say "I'm done"
    os.system('say "I\'m done"')
    
    print("\n" + "="*80)
    print("TEST 1 COMPLETE - Waiting for confirmation to continue...")
    print("="*80)


async def main():
    """Run tests one by one."""
    # Test 1
    await test_1_basic_chat()
    
    # Wait for user confirmation
    input("\nPress Enter to continue to the next test...")
    
    # TODO: Add more tests here
    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(main())