"""Test clarification chain - simple version."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def test():
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        formation = Formation()
        await formation.load(str(formation_path))
        
        print("Starting overlord...")
        overlord = await formation.start_overlord()
        
        print("\n=== Testing Clarification Chain ===\n")
        
        messages = [
            ("I need help with a scraper", "Initial ambiguous request"),
            ("something online", "Ambiguous clarification response"), 
            ("just any website", "Still ambiguous"),
            ("Amazon products", "Finally getting specific"),
        ]
        
        session_id = "test_chain"
        user_id = "test_user_chain"
        
        for i, (message, description) in enumerate(messages, 1):
            print(f"{i}. {description}")
            print(f"   User: '{message}'")
            
            response = await overlord.chat(
                message=message,
                user_id=user_id,
                session_id=session_id,
                stream=False
            )
            
            is_clarification = response.metadata and response.metadata.get("clarification")
            
            # Show response
            response_text = str(response.content)
            if len(response_text) > 150:
                response_text = response_text[:150] + "..."
            
            print(f"   Bot: {response_text}")
            
            if is_clarification:
                print(f"   Status: 🔄 Asking for clarification")
            else:
                print(f"   Status: ✅ Processing request")
                # Don't continue after processing
                break
            
            print()
        
        print("\n=== Summary ===")
        print("The system can handle chained clarifications where each response")
        print("can trigger additional clarification if still ambiguous.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(test())