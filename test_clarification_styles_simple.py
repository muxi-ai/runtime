"""Test clarification with different styles."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.muxi import Formation


async def main():
    """Test all three styles."""
    try:
        print("Loading formation...")
        formation_path = Path(__file__).parent / "test-formations" / "formation-clarification"
        
        for style in ["conversational", "formal", "brief"]:
            print(f"\n=== Testing {style.upper()} style ===")
            
            # Load fresh formation each time
            formation = Formation()
            await formation.load(str(formation_path))
            
            overlord = await formation.start_overlord()
            
            # Override the style
            overlord.clarification_config.style = style
            
            # Test with vague scraper request
            response = await overlord.chat(
                message="I need help with a scraper",
                user_id=f"test_user_{style}",
                session_id=f"test_session_{style}",
                stream=False
            )
            
            print(f"Response: {response.content}")
        
        print("\n=== Style Comparison Complete ===")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())