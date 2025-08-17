#!/usr/bin/env python
"""Debug test for 8a3 credential clarification."""

import asyncio
from pathlib import Path
import sys
import signal

sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi import Formation


def timeout_handler(signum, frame):
    print("\n❌ Test timed out after 10 seconds")
    print("The overlord.chat() call is not returning")
    sys.exit(1)


async def test():
    """Test credential clarification with timeout."""
    formation_path = Path(__file__).parent / "e2e/8_clarification/formations/formation-clarification"
    formation = Formation()
    await formation.load(str(formation_path))
    
    overlord = await formation.start_overlord()
    
    # Set a 10 second timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(10)
    
    print("Sending request: 'List my github repositories'")
    print("User: user1 (has multiple GitHub credentials)")
    
    try:
        response = await overlord.chat(
            message="List my github repositories",
            user_id="user1",
            session_id="test_debug",
            stream=False,
        )
        
        # Cancel the timeout
        signal.alarm(0)
        
        if isinstance(response, str):
            content = response
        else:
            content = response.content
            
        print(f"\nResponse received!")
        print(f"Content: {content}")
        
    except Exception as e:
        signal.alarm(0)
        print(f"\n❌ Exception during chat: {e}")
        import traceback
        traceback.print_exc()
    
    await formation.stop_overlord()
    formation.shutdown()


if __name__ == "__main__":
    asyncio.run(test())